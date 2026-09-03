from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .memory_git_sync import MemorySyncError, sync_bank, sync_behavior_bundle, sync_lock
    from .memory_authority import (AUTHORITY_REGISTRY, ROLE_USER, annotate_memory, authority_curation_errors, behavioral_authority, behavioral_context, configure_authority_registry, curate_authority_registry_local, validate_authority_registry)
    from .memory_context import DEFAULT_CONTEXT_CHARS, build_context_pack, context_selectors, entry_context_labels, entry_matches_selectors, context_residual_query
    from .memory_lifecycle import is_expired, parse_expiry
    from .memory_classification import classify_entry, infer_single_project
    from .memory_timeline import build_behavior_bootstrap, build_orientation, build_recurrence_context, build_timeline
    from .memory_policy_changes import recent_memory_policy_changes
    from .repo_timeline import collect_repo_history, default_operator_live, discover_repo_specs, parse_repo_arg
    from .stack_atlas import build_bootstrap_atlas
    from .worker_report_history import summarize_history, worker_history_events
except ImportError:
    from memory_git_sync import MemorySyncError, sync_bank, sync_behavior_bundle, sync_lock
    from memory_authority import (AUTHORITY_REGISTRY, ROLE_USER, annotate_memory, authority_curation_errors, behavioral_authority, behavioral_context, configure_authority_registry, curate_authority_registry_local, validate_authority_registry)
    from memory_context import DEFAULT_CONTEXT_CHARS, build_context_pack, context_selectors, entry_context_labels, entry_matches_selectors, context_residual_query
    from memory_lifecycle import is_expired, parse_expiry
    from memory_classification import classify_entry, infer_single_project
    from memory_timeline import build_behavior_bootstrap, build_orientation, build_recurrence_context, build_timeline
    from memory_policy_changes import recent_memory_policy_changes
    from repo_timeline import collect_repo_history, default_operator_live, discover_repo_specs, parse_repo_arg
    from stack_atlas import build_bootstrap_atlas
    from worker_report_history import summarize_history, worker_history_events

KINDS = {"fact", "decision", "lesson", "preference", "status", "correction"}
STATES = {"PROVEN", "PROVISIONAL", "REJECTED"}
REQUIRED = {"id", "timestamp", "kind", "scope", "tags", "text", "state", "evidence", "supersedes"}
DEFAULT_BANK = Path(__file__).resolve().parents[1] / "memory" / "memory-bank.jsonl"
DEFAULT_SOURCES = Path(__file__).resolve().parents[1] / "memory" / "sources.json"
DEFAULT_WORKER_HISTORY = Path(__file__).resolve().parents[1] / "worker-reports" / "history"
DEFAULT_RECALL_LIMIT = 5
MAX_RECALL_LIMIT = 8
DEFAULT_HISTORY_LIMIT = 8
MAX_HISTORY_LIMIT = 20
DEFAULT_RECENT_TITLES_LIMIT = 10
MAX_RECENT_TITLES_LIMIT = 20
MAX_TITLE_CHARS = 100
MAX_DERIVED_TITLE_CHARS = 80
MAX_TEXT_CHARS = 2000
MAX_TAGS = 12
MAX_EVIDENCE = 16
MAX_SUPERSEDES = 16


class BankError(ValueError):
    pass


def _string_list(entry: dict[str, Any], field: str) -> None:
    value = entry.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise BankError(f"{field} must be an array of non-empty strings")


def validate_entry(entry: dict[str, Any]) -> None:
    if not isinstance(entry, dict):
        raise BankError("entry must be a JSON object")
    missing = sorted(REQUIRED - set(entry))
    if missing:
        raise BankError(f"missing required fields: {', '.join(missing)}")
    for field in ("id", "timestamp", "kind", "scope", "text", "state"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            raise BankError(f"{field} must be a non-empty string")
    if "title" in entry:
        if not isinstance(entry["title"], str) or not entry["title"].strip():
            raise BankError("title must be a non-empty string when present")
        if len(entry["title"]) > MAX_TITLE_CHARS:
            raise BankError(f"title exceeds {MAX_TITLE_CHARS} characters")
    if entry["kind"] not in KINDS:
        raise BankError(f"invalid kind: {entry['kind']}")
    if entry["state"] not in STATES:
        raise BankError(f"invalid state: {entry['state']}")
    if "behavior_rule" in entry:
        if not isinstance(entry["behavior_rule"], bool):
            raise BankError("behavior_rule must be a boolean when present")
        if entry["behavior_rule"] and entry["kind"] not in {"decision", "lesson", "preference", "correction"}:
            raise BankError("behavior_rule=true requires decision, lesson, preference, or correction kind")
        if entry["behavior_rule"] and not any(str(item).startswith("user-instruction:") for item in entry.get("evidence", [])):
            raise BankError("behavior_rule=true requires explicit user-instruction provenance")
    if "project" in entry and (not isinstance(entry["project"], str) or not entry["project"].strip()):
        raise BankError("project must be a non-empty string when present")
    if "thread" in entry and (not isinstance(entry["thread"], str) or not entry["thread"].strip()):
        raise BankError("thread must be a non-empty string when present")
    if "expires_at" in entry:
        if not isinstance(entry["expires_at"], str) or not entry["expires_at"].strip():
            raise BankError("expires_at must be a non-empty ISO-8601 string when present")
        try:
            parse_expiry(entry)
        except ValueError as exc:
            raise BankError(str(exc)) from exc
    if "event_at" in entry:
        if not isinstance(entry["event_at"], str) or not entry["event_at"].strip():
            raise BankError("event_at must be a non-empty ISO-8601 string when present")
        try:
            event_at = datetime.fromisoformat(entry["event_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise BankError("event_at must be ISO-8601") from exc
        if event_at.tzinfo is None:
            raise BankError("event_at must include a timezone offset")
    try:
        parsed = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise BankError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise BankError("timestamp must include a timezone offset")
    for field in ("tags", "evidence", "supersedes"):
        _string_list(entry, field)
    if "assistant-recorded" in entry["tags"]:
        _string_list(entry, "source_messages")
        source_messages = entry["source_messages"]
        if not source_messages:
            raise BankError("assistant-recorded memory requires at least one verbatim source_messages item")
        for field in ("interpretation", "confidence_reason"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise BankError(f"assistant-recorded memory requires non-empty {field}")
        confidence = entry.get("confidence")
        if not isinstance(confidence, int) or isinstance(confidence, bool) or not 0 <= confidence <= 100:
            raise BankError("assistant-recorded memory confidence must be an integer from 0 to 100")
        if "turn_task" in entry and (not isinstance(entry["turn_task"], str) or not entry["turn_task"].strip()):
            raise BankError("turn_task must be a non-empty string when present")
    elif any(field in entry for field in ("source_messages", "turn_task", "interpretation", "confidence", "confidence_reason")):
        raise BankError("structured recorder fields require the assistant-recorded tag")
    if len(entry["text"]) > MAX_TEXT_CHARS:
        raise BankError(f"text exceeds {MAX_TEXT_CHARS} characters")
    if len(entry["tags"]) > MAX_TAGS:
        raise BankError(f"tags exceeds {MAX_TAGS} items")
    if len(entry["evidence"]) > MAX_EVIDENCE:
        raise BankError(f"evidence exceeds {MAX_EVIDENCE} items")
    if len(entry["supersedes"]) > MAX_SUPERSEDES:
        raise BankError(f"supersedes exceeds {MAX_SUPERSEDES} items")


def _read_bank_file(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not path.exists():
        return entries
    for line_no, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BankError(f"line {line_no}: invalid JSON") from exc
        try:
            validate_entry(entry)
        except BankError as exc:
            raise BankError(f"line {line_no}: {exc}") from exc
        if entry["id"] in seen:
            raise BankError(f"line {line_no}: duplicate id {entry['id']}")
        seen.add(entry["id"])
        entries.append(entry)
    return entries


def _is_canonical_bank(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_BANK.resolve()
    except OSError:
        return False


def _sync_canonical_locked(path: Path, *, strict: bool) -> None:
    try:
        result = sync_bank(path, publish=True)
    except MemorySyncError as exc:
        message = f"canonical memory GitHub sync NOT_PROVEN: {exc}"
        if strict:
            raise BankError(f"local memory was saved; {message}; do not append a duplicate") from exc
        print(message, file=sys.stderr)
        return
    if result.get("pulled") or result.get("pushed"):
        print("MEMORY_SYNC " + json.dumps(result, ensure_ascii=False), file=sys.stderr)


def load_bank(path: Path = DEFAULT_BANK) -> list[dict[str, Any]]:
    # Reads are local and side-effect free. Canonical Git reconciliation belongs only
    # to explicit writes, where append_entry() syncs before and after mutation.
    return _read_bank_file(path)


def _append_entry_file(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    if any(existing["id"] == entry["id"] for existing in _read_bank_file(path)):
        raise BankError(f"duplicate id {entry['id']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return entry


def _prepare_entry(values: dict[str, Any]) -> dict[str, Any]:
    entry = dict(values)
    now = datetime.now().astimezone()
    entry.setdefault("id", f"mem-{now:%Y%m%d}-{secrets.token_hex(4)}")
    entry.setdefault("timestamp", now.isoformat(timespec="seconds"))
    if not entry.get("title"):
        entry.pop("title", None)
    if not entry.get("project"):
        inferred_project = infer_single_project(entry)
        if inferred_project:
            entry["project"] = inferred_project
    validate_entry(entry)
    if classify_entry(entry)["sensitivity"] == "EXCLUDE":
        raise BankError("sensitive memory content rejected before write")
    return entry


def append_entry(path: Path, values: dict[str, Any]) -> dict[str, Any]:
    entry = _prepare_entry(values)
    if _is_canonical_bank(path):
        with sync_lock(path):
            _sync_canonical_locked(path, strict=False)
            saved = _append_entry_file(path, entry)
            _sync_canonical_locked(path, strict=True)
            return saved
    return _append_entry_file(path, entry)


def _is_canonical_authority_registry(path: Path) -> bool:
    try:
        return path.resolve() == AUTHORITY_REGISTRY.resolve()
    except OSError:
        return False


def append_behavior_entry(path: Path, values: dict[str, Any], registry_path: Path) -> dict[str, Any]:
    """Trusted record path: persist a verbatim user rule and curate it in the same sync commit."""
    entry = _prepare_entry(values)
    errors = authority_curation_errors(entry, ROLE_USER)
    if errors:
        raise BankError("behavior authority curation rejected: " + "; ".join(errors))
    canonical = _is_canonical_bank(path) and _is_canonical_authority_registry(registry_path)
    if canonical:
        with sync_lock(path):
            _sync_canonical_locked(path, strict=False)
            saved = _append_entry_file(path, entry)
            try:
                result = sync_behavior_bundle(
                    path, registry_path, add_user_ids={entry["id"]}, publish=True
                )
            except MemorySyncError as exc:
                raise BankError(
                    "local behavior memory and authority curation were saved; canonical sync NOT_PROVEN: "
                    f"{exc}; do not append a duplicate"
                ) from exc
            configure_authority_registry(registry_path)
            if result.get("pushed"):
                print("MEMORY_BEHAVIOR_SYNC " + json.dumps(result, ensure_ascii=False), file=sys.stderr)
            if behavioral_authority(saved).get("role") != ROLE_USER:
                raise BankError("behavior rule persisted but USER_EXPLICIT authority was not established")
            return saved

    original_bank = path.read_bytes() if path.exists() else None
    original_registry = registry_path.read_bytes() if registry_path.exists() else None
    try:
        saved = _append_entry_file(path, entry)
        entries = _read_bank_file(path)
        curate_authority_registry_local(entries, entry["id"], ROLE_USER, path=registry_path)
        if behavioral_authority(saved).get("role") != ROLE_USER:
            raise BankError("behavior rule persisted but USER_EXPLICIT authority was not established")
        return saved
    except Exception:
        if original_bank is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(original_bank)
        if original_registry is None:
            registry_path.unlink(missing_ok=True)
        else:
            registry_path.write_bytes(original_registry)
        configure_authority_registry(registry_path if registry_path.exists() else AUTHORITY_REGISTRY)
        raise


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w-]+", value.casefold(), flags=re.UNICODE))


def derive_display_title(entry: dict[str, Any]) -> str:
    explicit = entry.get("title")
    if isinstance(explicit, str) and explicit.strip():
        return re.sub(r"\s+", " ", explicit).strip()
    text = re.sub(r"\s+", " ", str(entry.get("text", ""))).strip()
    if len(text) <= MAX_DERIVED_TITLE_CHARS:
        return text
    return text[: MAX_DERIVED_TITLE_CHARS - 1].rstrip() + "…"


def _ordinary_recall_eligible(entry: dict[str, Any], superseded: set[str]) -> bool:
    if entry.get("state") == "REJECTED" or entry.get("id") in superseded or is_expired(entry):
        return False
    classification = classify_entry(entry)
    if classification["sensitivity"] == "EXCLUDE":
        return False
    if classification["durability"] in {"EPHEMERAL", "HISTORICAL"}:
        return False
    return True


def recent_title_entries(entries: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    effective_limit = min(MAX_RECENT_TITLES_LIMIT, max(0, DEFAULT_RECENT_TITLES_LIMIT if limit is None else limit))
    if effective_limit == 0:
        return []
    superseded = {old for entry in entries for old in entry.get("supersedes", [])}
    current = [entry for entry in entries if _ordinary_recall_eligible(entry, superseded)]
    current.sort(
        key=lambda entry: (
            datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")),
            entry["id"],
        ),
        reverse=True,
    )
    return [
        {
            "id": entry["id"],
            "timestamp": entry["timestamp"],
            "title": derive_display_title(entry),
            "kind": entry["kind"],
            "scope": entry["scope"],
            "authority": behavioral_authority(entry)["role"],
        }
        for entry in current[:effective_limit]
    ]


def load_source_registry(path: Path = DEFAULT_SOURCES) -> dict[str, Any]:
    if not path.is_file():
        return {"classes": {}, "sources": []}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return {"classes": {}, "sources": []}


def source_relevance(entry: dict[str, Any], registry: dict[str, Any] | None = None) -> int:
    registry = registry or load_source_registry()
    classes = registry.get("classes") or {}
    best = 0
    for evidence in entry.get("evidence", []):
        for source in registry.get("sources", []):
            if any(evidence.startswith(prefix) for prefix in source.get("match_prefixes", [])):
                best = max(best, int(classes.get(source.get("class"), 0)))
    return best


def search_entries(entries: list[dict[str, Any]], query: str, *, scope: str | None = None,
                   tags: list[str] | None = None, limit: int | None = None, history: bool = False,
                   source_registry: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    tags = [tag.casefold() for tag in (tags or [])]
    query_tokens = _tokens(query)
    if not history and not query_tokens and not scope and not tags:
        return []
    default_limit = DEFAULT_HISTORY_LIMIT if history else DEFAULT_RECALL_LIMIT
    hard_cap = MAX_HISTORY_LIMIT if history else MAX_RECALL_LIMIT
    effective_limit = min(hard_cap, max(0, default_limit if limit is None else limit))
    if effective_limit == 0:
        return []
    superseded = {old for entry in entries for old in entry.get("supersedes", [])}
    ranked: list[tuple[float, int, datetime, dict[str, Any]]] = []
    registry = source_registry or load_source_registry()
    for entry in entries:
        if not history and not _ordinary_recall_eligible(entry, superseded):
            continue
        searchable_text = "\n".join([
            entry["text"],
            entry.get("title", ""),
            entry.get("turn_task", ""),
            entry.get("interpretation", ""),
            *entry.get("source_messages", []),
        ])
        text_tokens = _tokens(searchable_text)
        tag_tokens = {tag.casefold() for tag in entry["tags"]}
        relevance = 0.0
        if scope and entry["scope"].casefold() == scope.casefold():
            relevance += 4
        relevance += 4 * sum(tag in tag_tokens for tag in tags)
        relevance += sum(token in text_tokens or token in tag_tokens or token == entry["scope"].casefold() for token in query_tokens)
        if (query_tokens or scope or tags) and relevance == 0:
            continue
        source_score = source_relevance(entry, registry)
        stamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        ranked.append((relevance, source_score, stamp, entry))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [entry for _, _, _, entry in ranked[:effective_limit]]


def _conversation_excerpt(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"conversation:{hit.get('conversation_id')}:{hit.get('message_id')}",
        "timestamp": hit.get("created_at") or hit.get("conversation_update_time") or hit.get("conversation_create_time") or "1970-01-01T00:00:00Z",
        "kind": "conversation",
        "scope": "full-conversation-history",
        "tags": ["full-conversation", "historical-source"],
        "title": hit.get("title") or hit.get("conversation_id") or "Historical conversation",
        "text": hit.get("match") or "",
        "source_class": "HISTORICAL_CONTEXT",
        "retrieval_role": "EVIDENCE_EXCERPT",
        "evidence": list(hit.get("sources") or []),
        "conversation_id": hit.get("conversation_id"),
        "message_id": hit.get("message_id"),
        "role": hit.get("role"),
    }


def conversation_history_report(query: str, *, limit: int = DEFAULT_RECALL_LIMIT, db: Path | None = None) -> dict[str, Any]:
    if not query.strip():
        return {"summary": {}, "hits": []}
    try:
        try:
            from .conversation_search import DEFAULT_DB, search_report
        except ImportError:
            from conversation_search import DEFAULT_DB, search_report
        target = db or DEFAULT_DB
        if not target.is_file():
            return {"summary": {}, "hits": []}
        report = search_report(target, query, limit=min(MAX_RECALL_LIMIT, max(1, int(limit))))
    except (OSError, ValueError):
        return {"summary": {}, "hits": []}
    return {
        "summary": dict(report.get("summary") or {}),
        "hits": [_conversation_excerpt(hit) for hit in report.get("hits", [])],
    }


def conversation_history_hits(query: str, *, limit: int = DEFAULT_RECALL_LIMIT, db: Path | None = None) -> list[dict[str, Any]]:
    return list(conversation_history_report(query, limit=limit, db=db).get("hits", []))


def _conversation_summary_entry(query: str, summary: dict[str, Any]) -> dict[str, Any] | None:
    matching_messages = int(summary.get("matching_messages") or 0)
    if matching_messages <= 0:
        return None
    matching_conversations = int(summary.get("matching_conversations") or 0)
    first_match = summary.get("first_match")
    last_match = summary.get("last_match")
    date_text = f" from {first_match} to {last_match}" if first_match or last_match else ""
    top = []
    for item in list(summary.get("top_conversations") or [])[:3]:
        top.append({
            "conversation_id": item.get("conversation_id"),
            "title": item.get("title"),
            "matches": item.get("matches"),
            "first_match": item.get("first_match"),
            "last_match": item.get("last_match"),
        })
    return {
        "id": "conversation-corpus-summary",
        "kind": "corpus-summary",
        "scope": "full-conversation-history",
        "tags": ["full-conversation", "historical-source", "aggregate-signal"],
        "title": "Conversation corpus signal",
        "text": f"{matching_messages} matching messages across {matching_conversations} conversations{date_text}.",
        "source_class": "HISTORICAL_CONTEXT",
        "retrieval_role": "AGGREGATE_SIGNAL",
        "interpretation": "prevalence_signal_not_truth",
        "query": query,
        "matching_messages": matching_messages,
        "matching_conversations": matching_conversations,
        "first_match": first_match,
        "last_match": last_match,
        "non_wall_clock_messages": int(summary.get("non_wall_clock_messages") or 0),
        "roles": dict(summary.get("roles") or {}),
        "top_conversations": top,
        "sample_strategy": summary.get("sample_strategy"),
    }


def search_memory_entries(entries: list[dict[str, Any]], query: str, *, scope: str | None = None, tags: list[str] | None = None, limit: int = DEFAULT_RECALL_LIMIT, history: bool = False, strategy: str | None = None) -> list[dict[str, Any]]:
    selected_strategy = (strategy or os.environ.get("MEMORY_RETRIEVAL_STRATEGY", "hybrid")).strip().casefold()
    if selected_strategy == "legacy" or history:
        return search_entries(entries, query, scope=scope, tags=tags, limit=limit, history=history)
    if selected_strategy != "hybrid":
        raise BankError(f"unknown memory retrieval strategy: {selected_strategy}")
    try:
        from .memory_hybrid import search_entries_hybrid
    except ImportError:
        from memory_hybrid import search_entries_hybrid
    return search_entries_hybrid(entries, query, scope=scope, tags=tags, limit=limit, history=history)


def search_behavior_memory(
    entries: list[dict[str, Any]], query: str, *, limit: int = MAX_RECALL_LIMIT,
) -> list[dict[str, Any]]:
    """Search only current behavior-authority records; authority is decided before relevance."""
    effective_limit = min(MAX_RECALL_LIMIT, max(1, int(limit)))
    return search_memory_entries(behavioral_context(entries), query, limit=effective_limit, history=False)


def _merge_behavior_context(
    behavior_hits: list[dict[str, Any]], ordinary_hits: list[dict[str, Any]], limit: int
) -> list[dict[str, Any]]:
    """Reserve up to two relevant procedural slots before advisory context."""
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in behavior_hits[: min(2, limit)]:
        ident = str(entry.get("id") or "")
        if ident and ident not in seen:
            selected.append(entry)
            seen.add(ident)
    for entry in ordinary_hits:
        ident = str(entry.get("id") or "")
        if ident and ident not in seen:
            selected.append(entry)
            seen.add(ident)
        if len(selected) >= limit:
            break
    return selected[:limit]


def search_context_memory(
    entries: list[dict[str, Any]], query: str, *, scope: str | None = None,
    tags: list[str] | None = None, limit: int = MAX_RECALL_LIMIT,
) -> list[dict[str, Any]]:
    effective_limit = min(MAX_RECALL_LIMIT, max(1, int(limit)))
    selectors = context_selectors(query)
    filtered = [entry for entry in entries if entry_matches_selectors(entry, selectors)]
    projects = selectors.get("projects") or set()
    residual = context_residual_query(query)

    if not projects:
        residual_tokens = _tokens(residual)
        if not residual_tokens:
            return []
        if len(residual_tokens) < 2:
            # Single-token context queries remain closed to ordinary memory to avoid
            # broad accidental dumps, but an explicitly authorized behavioral rule
            # may be a deliberate trigger (for example, a user-defined stop word).
            behavior_entries = [
                entry for entry in filtered
                if behavioral_authority(entry).get("may_change_behavior")
            ]
            return search_memory_entries(
                behavior_entries, residual, scope=scope, tags=tags,
                limit=effective_limit, history=False,
            )
        behavior_entries = [
            entry for entry in filtered if behavioral_authority(entry).get("may_change_behavior")
        ]
        behavior_hits = search_memory_entries(
            behavior_entries, residual, scope=scope, tags=tags, limit=min(2, effective_limit), history=False
        )
        ordinary_hits = search_memory_entries(
            filtered, residual, scope=scope, tags=tags, limit=effective_limit, history=False
        )
        return _merge_behavior_context(behavior_hits, ordinary_hits, effective_limit)

    project_entries: list[dict[str, Any]] = []
    entity_project_entries: list[dict[str, Any]] = []
    ambient_entries: list[dict[str, Any]] = []
    for entry in filtered:
        labels = entry_context_labels(entry)
        if labels["projects"] & projects:
            project_entries.append(entry)
        elif not labels["projects"]:
            # Secondary entity labels may recover cross-project/global memories that
            # genuinely mention the requested project without re-scoping them as that
            # project's authority. They are fallback context, never primary metadata.
            entities = set(classify_entry(entry).get("entities") or [])
            if entities & projects:
                entity_project_entries.append(entry)
            else:
                ambient_entries.append(entry)

    project_target = max(1, (effective_limit * 3 + 3) // 4)
    if len(_tokens(residual)) >= 1:
        # The project selector is already established mechanically, so rank inside
        # the explicit project subset first, then use entity-linked cross-project
        # evidence to fill unused project slots.
        project_hits = search_memory_entries(project_entries, residual, scope=scope, tags=tags, limit=project_target, history=False)
        remaining_project = project_target - len(project_hits)
        if remaining_project > 0:
            project_hits.extend(search_memory_entries(entity_project_entries, residual, scope=scope, tags=tags, limit=remaining_project, history=False))
    else:
        # Generic 'work on <project>' needs durable orientation, not semantic noise.
        candidates = [*project_entries, *entity_project_entries]
        superseded = {old for entry in candidates for old in entry.get("supersedes", [])}
        project_hits = [
            entry for entry in candidates
            if entry.get("state") == "PROVEN"
            and entry.get("id") not in superseded
            and _ordinary_recall_eligible(entry, superseded)
            and entry.get("kind") not in {"status", "fact"}
            and bool(entry.get("evidence"))
        ]
        project_hits.sort(
            key=lambda entry: (
                1 if (entry_context_labels(entry)["projects"] & projects) else 0,
                datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "+00:00")),
            ),
            reverse=True,
        )
        project_hits = project_hits[:project_target]

    remaining = effective_limit - len(project_hits)
    ambient_hits: list[dict[str, Any]] = []
    if remaining > 0 and len(_tokens(residual)) >= 2:
        ambient_hits = search_memory_entries(ambient_entries, residual, scope=scope, tags=tags, limit=remaining, history=False)
    ordinary_hits = [*project_hits, *ambient_hits]
    if len(_tokens(residual)) >= 2:
        behavior_entries = [
            entry for entry in filtered if behavioral_authority(entry).get("may_change_behavior")
        ]
        behavior_hits = search_memory_entries(
            behavior_entries, residual, scope=scope, tags=tags, limit=min(2, effective_limit), history=False
        )
        return _merge_behavior_context(behavior_hits, ordinary_hits, effective_limit)
    return ordinary_hits[:effective_limit]


def search_all_memory(entries: list[dict[str, Any]], query: str, *, scope: str | None = None, tags: list[str] | None = None, limit: int = DEFAULT_RECALL_LIMIT, history: bool = False, conversation_db: Path | None = None) -> list[dict[str, Any]]:
    effective_limit = min(MAX_RECALL_LIMIT, max(0, int(limit)))
    manual = search_memory_entries(entries, query, scope=scope, tags=tags, limit=effective_limit, history=history)
    if history or not query.strip() or effective_limit == 0:
        return manual

    corpus = conversation_history_report(query, limit=effective_limit, db=conversation_db)
    summary_entry = _conversation_summary_entry(query, dict(corpus.get("summary") or {}))
    conversation_hits = list(corpus.get("hits") or [])
    if summary_entry is None:
        return manual

    if not manual:
        selected_manual: list[dict[str, Any]] = []
        selected_conversations = conversation_hits[:effective_limit]
    elif not conversation_hits or effective_limit == 1:
        selected_manual = manual[:effective_limit]
        selected_conversations = []
    else:
        conversation_slots = min(2, max(1, (effective_limit - 1) // 2))
        manual_slots = effective_limit - conversation_slots
        selected_manual = manual[:manual_slots]
        selected_conversations = conversation_hits[:conversation_slots]
        remaining = effective_limit - len(selected_manual) - len(selected_conversations)
        if remaining > 0:
            manual_extra = manual[manual_slots:manual_slots + remaining]
            selected_manual.extend(manual_extra)
            remaining -= len(manual_extra)
        if remaining > 0:
            selected_conversations.extend(conversation_hits[conversation_slots:conversation_slots + remaining])

    return selected_manual + [summary_entry] + selected_conversations


def _print_json(value: Any, *, compact: bool = False) -> None:
    separators = (",", ":") if compact else None
    payload = json.dumps(value, ensure_ascii=False, separators=separators) + "\n"
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        print(json.dumps(value, ensure_ascii=True))
        return
    stream.write(payload.encode("utf-8", "backslashreplace"))
    stream.flush()


def _main() -> int:
    parser = argparse.ArgumentParser(description="Shared memory bank")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--authority-registry", type=Path, default=AUTHORITY_REGISTRY)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("authority-validate", help="validate authority registry against the current bank")
    note = sub.add_parser("note", help="save a quick durable note")
    note.add_argument("text")
    note.add_argument("--scope", default="global")
    note.add_argument("--event-at")
    note.add_argument("--thread")

    append = sub.add_parser("append")
    append.add_argument("--kind", required=True, choices=sorted(KINDS))
    append.add_argument("--scope", required=True)
    append.add_argument("--tag", action="append", default=[])
    append.add_argument("--title")
    append.add_argument("--project")
    append.add_argument("--expires-at")
    append.add_argument("--event-at")
    append.add_argument("--thread")
    append.add_argument("--text", required=True)
    append.add_argument("--state", required=True, choices=sorted(STATES))
    append.add_argument("--evidence", action="append", default=[])
    append.add_argument("--supersedes", action="append", default=[])
    append.add_argument("--standalone-correction", action="store_true", help="allow a correction that intentionally does not replace an existing memory")

    record = sub.add_parser("record", help="save an assistant-authored memory with verbatim user provenance")
    record.add_argument("--kind", required=True, choices=sorted(KINDS))
    record.add_argument("--scope", required=True)
    record.add_argument("--tag", action="append", default=[])
    record.add_argument("--title")
    record.add_argument("--project")
    record.add_argument("--expires-at")
    record.add_argument("--event-at")
    record.add_argument("--thread")
    record.add_argument("--text", required=True, help="compact memory summary")
    record.add_argument("--source-message", action="append", required=True, help="verbatim user message; repeat in chronological order")
    record.add_argument("--turn-task", help="verbatim user task that opened the long execution turn, when relevant")
    record.add_argument("--interpretation", required=True, help="assistant explanation of why the memory exists and what it means")
    record.add_argument("--confidence", required=True, type=int, help="assistant interpretation confidence, 0-100")
    record.add_argument("--confidence-reason", required=True)
    record.add_argument("--state", required=True, choices=sorted(STATES))
    record.add_argument("--evidence", action="append", default=[])
    record.add_argument("--supersedes", action="append", default=[])
    record.add_argument("--standalone-correction", action="store_true", help="allow a correction that intentionally does not replace an existing memory")

    search = sub.add_parser("search")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--scope")
    search.add_argument("--tag", action="append", default=[])
    search.add_argument("--limit", type=int, default=DEFAULT_RECALL_LIMIT)
    search.add_argument("--history", action="store_true")

    behavior = sub.add_parser("behavior-search", help="search only current behavior-authority records")
    behavior.add_argument("query")
    behavior.add_argument("--limit", type=int, default=MAX_RECALL_LIMIT)

    context = sub.add_parser("context", help="build a compact task-scoped context pack from curated memory and historical corpus")
    context.add_argument("query")
    context.add_argument("--scope")
    context.add_argument("--tag", action="append", default=[])
    context.add_argument("--limit", type=int, default=MAX_RECALL_LIMIT)
    context.add_argument("--max-chars", type=int, default=DEFAULT_CONTEXT_CHARS)
    context.add_argument("--with-history", action="store_true", help="also search the preserved full-conversation corpus")

    orient = sub.add_parser("orient", help="optional historical/project orientation view")
    orient.add_argument("--project", action="append", default=[])
    orient.add_argument("--recent-events", type=int, default=8)
    orient.add_argument("--error-threads", type=int, default=4)
    orient.add_argument("--project-events", type=int, default=3)
    orient.add_argument("--repo-events", type=int, default=12, help="maximum local Git commits read per repo")
    orient.add_argument("--repo", action="append", default=[], metavar="PROJECT=PATH", help="explicit local Git repo; repeatable")
    orient.add_argument("--operator-live", type=Path, help="optional operator-live.json used only to discover repo paths")
    orient.add_argument("--no-repos", action="store_true", help="disable local Git projection")

    timeline_cmd = sub.add_parser("timeline", help="derived chronology over memory, immutable worker reports, and optional local Git events")
    timeline_cmd.add_argument("query", nargs="?", default="")
    timeline_cmd.add_argument("--view", choices=("general", "project", "errors"), default="general")
    timeline_cmd.add_argument("--project")
    timeline_cmd.add_argument("--thread")
    timeline_cmd.add_argument("--limit", type=int, default=20)
    timeline_cmd.add_argument("--with-repos", action="store_true", help="merge read-only local Git commit events into general/project views")
    timeline_cmd.add_argument("--repo-events", type=int, default=20)
    timeline_cmd.add_argument("--repo", action="append", default=[], metavar="PROJECT=PATH")
    timeline_cmd.add_argument("--operator-live", type=Path, help="optional operator-live.json used only to discover repo paths")
    timeline_cmd.add_argument("--worker-history", type=Path, default=DEFAULT_WORKER_HISTORY, help="immutable worker-report history root")
    timeline_cmd.add_argument("--no-workers", action="store_true", help="exclude worker-report history and utilization summary")

    history = sub.add_parser("history")
    history.add_argument("query", nargs="?", default="")
    history.add_argument("--scope")
    history.add_argument("--tag", action="append", default=[])
    history.add_argument("--limit", type=int, default=DEFAULT_HISTORY_LIMIT)

    recent_titles = sub.add_parser("recent-titles", aliases=["recent"])
    recent_titles.add_argument("--limit", type=int, default=DEFAULT_RECENT_TITLES_LIMIT)

    changes = sub.add_parser("changes", help="read-only Git-derived memory and policy change log")
    changes.add_argument("--limit", type=int, default=20)
    changes.add_argument("--ref", default="HEAD")

    args = parser.parse_args()
    try:
        configure_authority_registry(args.authority_registry)
        entries = load_bank(args.bank)
        if args.command == "validate":
            _print_json({"status": "PROVEN", "entries": len(entries)})
            return 0
        if args.command == "authority-validate":
            result = validate_authority_registry(entries, path=args.authority_registry)
            _print_json(result)
            return 0 if result.get("status") == "PROVEN" else 2
        if args.command == "note":
            text = args.text.strip()
            tags = ["quick-note"]
            if text.casefold().startswith(("error:", "error ")):
                tags.append("error")
            values = {"kind": "lesson", "scope": args.scope, "tags": tags, "text": text, "state": "PROVISIONAL", "evidence": [], "supersedes": [], "behavior_rule": False}
            if args.event_at:
                values["event_at"] = args.event_at
            if args.thread:
                values["thread"] = args.thread
            entry = append_entry(args.bank, values)
            _print_json(entry)
            return 0
        if args.command == "append":
            if args.standalone_correction and args.kind != "correction":
                raise BankError("--standalone-correction is valid only with --kind correction")
            if args.kind == "correction" and not args.supersedes and not args.standalone_correction:
                raise BankError("correction must name at least one --supersedes memory id, or explicitly use --standalone-correction")
            known_ids = {item["id"] for item in entries}
            missing_supersedes = [memory_id for memory_id in args.supersedes if memory_id not in known_ids]
            if missing_supersedes:
                raise BankError("supersedes target not found: " + ", ".join(missing_supersedes))
            values = {"kind": args.kind, "scope": args.scope, "tags": args.tag, "title": args.title, "text": args.text, "state": args.state, "evidence": args.evidence, "supersedes": args.supersedes, "behavior_rule": False}
            if args.project:
                values["project"] = args.project
            if args.expires_at:
                values["expires_at"] = args.expires_at
            if args.event_at:
                values["event_at"] = args.event_at
            if args.thread:
                values["thread"] = args.thread
            entry = append_entry(args.bank, values)
            _print_json(entry)
            return 0
        if args.command == "record":
            if args.standalone_correction and args.kind != "correction":
                raise BankError("--standalone-correction is valid only with --kind correction")
            if args.kind == "correction" and not args.supersedes and not args.standalone_correction:
                raise BankError("correction must name at least one --supersedes memory id, or explicitly use --standalone-correction")
            known_ids = {item["id"] for item in entries}
            missing_supersedes = [memory_id for memory_id in args.supersedes if memory_id not in known_ids]
            if missing_supersedes:
                raise BankError("supersedes target not found: " + ", ".join(missing_supersedes))
            values = {
                "kind": args.kind, "scope": args.scope,
                "tags": [*args.tag, "assistant-recorded", "verbatim-source"],
                "title": args.title, "text": args.text, "state": args.state,
                "evidence": args.evidence, "supersedes": args.supersedes, "behavior_rule": False,
                "source_messages": args.source_message, "interpretation": args.interpretation,
                "confidence": args.confidence, "confidence_reason": args.confidence_reason,
            }
            if args.project:
                values["project"] = args.project
            if args.expires_at:
                values["expires_at"] = args.expires_at
            if args.event_at:
                values["event_at"] = args.event_at
            if args.thread:
                values["thread"] = args.thread
            if args.turn_task:
                values["turn_task"] = args.turn_task
            entry = append_entry(args.bank, values)
            _print_json(entry)
            return 0
        if args.command == "orient":
            projects = args.project or ["p3", "tiny3d", "lowvram"]
            repo_history = {"events": [], "repo_snapshots": []}
            if not args.no_repos:
                specs = [parse_repo_arg(value) for value in args.repo]
                if not specs:
                    vault_root = Path(__file__).resolve().parents[1]
                    operator_live = args.operator_live or default_operator_live(vault_root)
                    specs = discover_repo_specs(operator_live, vault_root=vault_root)
                repo_history = collect_repo_history(specs, limit_per_repo=args.repo_events)
            _print_json(build_orientation(
                entries, projects=projects, recent_events=args.recent_events, error_threads=args.error_threads,
                project_events=args.project_events, repo_events=repo_history["events"], repo_snapshots=repo_history["repo_snapshots"],
            ))
            return 0
        if args.command == "timeline":
            repo_events = []
            if args.with_repos:
                specs = [parse_repo_arg(value) for value in args.repo]
                if not specs:
                    vault_root = Path(__file__).resolve().parents[1]
                    operator_live = args.operator_live or default_operator_live(vault_root)
                    specs = discover_repo_specs(operator_live, vault_root=vault_root)
                repo_events = collect_repo_history(specs, limit_per_repo=args.repo_events)["events"]
            worker_events = [] if args.no_workers else worker_history_events(args.worker_history)
            report = build_timeline(
                entries, view=args.view, project=args.project, query=args.query, thread=args.thread,
                limit=args.limit, repo_events=repo_events, worker_events=worker_events,
            )
            if not args.no_workers and args.view != "errors":
                report["worker_metrics"] = summarize_history(args.worker_history, hours=24.0)
            _print_json(report)
            return 0
        if args.command == "history":
            _print_json([annotate_memory(entry) for entry in search_entries(entries, args.query, scope=args.scope, tags=args.tag, limit=args.limit, history=True)])
            return 0
        if args.command in ("recent-titles", "recent"):
            _print_json(recent_title_entries(entries, limit=args.limit))
            return 0
        if args.command == "changes":
            _print_json(recent_memory_policy_changes(ref=args.ref, limit=args.limit))
            return 0
        if args.command == "behavior-search":
            _print_json([annotate_memory(entry) for entry in search_behavior_memory(entries, args.query, limit=args.limit)])
            return 0
        if args.command == "context":
            selected = search_context_memory(entries, args.query, scope=args.scope, tags=args.tag, limit=args.limit)
            hits = [annotate_memory(entry) for entry in selected]
            if args.with_history:
                report = conversation_history_report(args.query, limit=min(3, args.limit))
                summary = _conversation_summary_entry(args.query, report.get("summary") or {})
                if summary is not None:
                    hits.append(summary)
                hits.extend(list(report.get("hits") or [])[:2])
            timeline = build_recurrence_context(entries, args.query)
            _print_json(build_context_pack(args.query, hits, timeline=timeline, max_chars=args.max_chars))
            return 0
        if args.command == "search":
            _print_json([annotate_memory(entry) for entry in search_all_memory(entries, args.query, scope=args.scope, tags=args.tag, limit=args.limit, history=args.history)])
            return 0
    except BankError as exc:
        _print_json({"status": "REJECTED", "error": str(exc)})
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
