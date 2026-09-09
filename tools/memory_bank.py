from __future__ import annotations

import argparse
from collections import Counter
import json
import mmap
import os
import re
import tempfile
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .memory_git_sync import MemorySyncError, sync_bank, sync_lock
    from .memory_context import DEFAULT_CONTEXT_CHARS, build_context_pack, context_memory_eligible, context_selectors, entry_context_labels, entry_matches_selectors, context_residual_query
    from .memory_lifecycle import is_expired, parse_expiry, parse_iso_datetime
    from .memory_classification import classify_entry, infer_single_project
    from .memory_timeline import build_incident_rollups, build_recurrence_context, build_timeline
    from .repo_timeline import collect_repo_history, discover_repo_specs, parse_repo_arg, tracked_artifact_events
    from .worker_report_history import worker_history_events
except ImportError:
    from memory_git_sync import MemorySyncError, sync_bank, sync_lock
    from memory_context import DEFAULT_CONTEXT_CHARS, build_context_pack, context_memory_eligible, context_selectors, entry_context_labels, entry_matches_selectors, context_residual_query
    from memory_lifecycle import is_expired, parse_expiry, parse_iso_datetime
    from memory_classification import classify_entry, infer_single_project
    from memory_timeline import build_incident_rollups, build_recurrence_context, build_timeline
    from repo_timeline import collect_repo_history, discover_repo_specs, parse_repo_arg, tracked_artifact_events
    from worker_report_history import worker_history_events

def _default_local_bank_path() -> Path:
    override = os.environ.get("VAULT_MEMORY_LOCAL_BANK")
    if override:
        return Path(override).expanduser()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "VaultMemory" / "memory-bank.local.jsonl"
    return Path.home() / ".local" / "state" / "vault-memory" / "memory-bank.local.jsonl"


KINDS = {"fact", "decision", "lesson", "preference", "status", "correction"}
STATES = {"PROVEN", "PROVISIONAL", "REJECTED"}
REQUIRED = {"id", "timestamp", "kind", "scope", "tags", "text", "state", "evidence", "supersedes"}
DEFAULT_BANK = Path(__file__).resolve().parents[1] / "memory" / "memory-bank.jsonl"
DEFAULT_LOCAL_BANK = _default_local_bank_path()
DEFAULT_SOURCES = Path(__file__).resolve().parents[1] / "memory" / "sources.json"
DEFAULT_WORKER_HISTORY = Path(__file__).resolve().parents[1] / "worker-reports" / "history"
DEFAULT_MANUAL_WORKER_HISTORY = Path(__file__).resolve().parents[1] / "worker-reports" / "manual" / "history"
DEFAULT_TIMED_WORKER_METRICS = Path(__file__).resolve().parents[1] / "worker-reports" / "metrics.json"
DEFAULT_MANUAL_WORKER_METRICS = Path(__file__).resolve().parents[1] / "worker-reports" / "manual" / "metrics.json"
MAX_WORKER_FINDING_CHARS = 320
DEFAULT_RECALL_LIMIT = 5
MAX_RECALL_LIMIT = 8
DEFAULT_HISTORY_LIMIT = 8
MAX_HISTORY_LIMIT = 20
DEFAULT_RECENT_TITLES_LIMIT = 10
MAX_RECENT_TITLES_LIMIT = 20
MAX_TITLE_CHARS = 100
POSITIVE_MILESTONE_STICKER = "★"
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
    if "behavior_rule" in entry and not isinstance(entry["behavior_rule"], bool):
        raise BankError("behavior_rule must be a boolean when present")
    if "positive_milestone" in entry and not isinstance(entry["positive_milestone"], bool):
        raise BankError("positive_milestone must be a boolean when present")
    milestone = bool(entry.get("positive_milestone"))
    sticker = entry.get("milestone_sticker")
    if milestone and sticker != POSITIVE_MILESTONE_STICKER:
        raise BankError(f"positive milestone requires milestone_sticker {POSITIVE_MILESTONE_STICKER!r}")
    if not milestone and sticker is not None:
        raise BankError("milestone_sticker requires positive_milestone=true")
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
            event_at = parse_iso_datetime(entry["event_at"])
        except ValueError as exc:
            raise BankError("event_at must be ISO-8601") from exc
        if event_at.tzinfo is None:
            raise BankError("event_at must include a timezone offset")
    try:
        parsed = parse_iso_datetime(entry["timestamp"])
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


def _uses_default_local_overlay(path: Path) -> bool:
    try:
        return path.resolve() == DEFAULT_BANK.resolve()
    except OSError:
        return False


def _merge_effective_entries(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(primary)
    by_id = {entry["id"]: entry for entry in primary}
    for entry in secondary:
        ident = entry["id"]
        if ident in by_id:
            if by_id[ident] != entry:
                raise BankError(f"memory id conflict: {ident}")
            continue
        merged.append(entry)
        by_id[ident] = entry
    return merged


def _effective_bank_entries(path: Path) -> list[dict[str, Any]]:
    base = _read_bank_file(path)
    if not _uses_default_local_overlay(path):
        return base
    return _merge_effective_entries(base, _read_bank_file(DEFAULT_LOCAL_BANK))


def _write_entries_file(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n" for entry in entries)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(text, encoding="utf-8", newline="\n")
    temp_path.replace(path)


def _write_overlay_delta(seed_path: Path, effective_entries: list[dict[str, Any]]) -> None:
    seed = _read_bank_file(seed_path)
    seed_by_id = {entry["id"]: entry for entry in seed}
    overlay: list[dict[str, Any]] = []
    for entry in effective_entries:
        ident = entry["id"]
        if ident in seed_by_id:
            if seed_by_id[ident] != entry:
                raise BankError(f"memory id conflict: {ident}")
            continue
        overlay.append(entry)
    _write_entries_file(DEFAULT_LOCAL_BANK, overlay)


def _sync_default_overlay_locked(path: Path, *, strict: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="vault-memory-overlay-") as raw:
        staged = Path(raw) / "memory-bank.jsonl"
        _write_entries_file(staged, _effective_bank_entries(path))
        try:
            result = sync_bank(staged, publish=True)
        except MemorySyncError as exc:
            message = f"canonical memory GitHub sync NOT_PROVEN: {exc}"
            if strict:
                raise BankError(f"local memory was saved; {message}; do not append a duplicate") from exc
            print(message, file=sys.stderr)
            return
        _write_overlay_delta(path, _read_bank_file(staged))
    if result.get("pulled") or result.get("pushed"):
        print("MEMORY_SYNC " + json.dumps(result, ensure_ascii=False), file=sys.stderr)


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
    # Reads are local and side-effect free. The tracked bank is a seed; local-only
    # canonical writes live in the external overlay and are merged by id on read.
    return _effective_bank_entries(path)


def _bank_has_id(path: Path, entry_id: str) -> bool:
    """Check one top-level JSONL id without decoding the whole append-only bank."""
    try:
        if path.stat().st_size == 0:
            return False
        needle = json.dumps(str(entry_id), ensure_ascii=False).encode("utf-8")
        with path.open("rb") as handle:
            with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
                position = mapped.find(needle)
                while position >= 0:
                    line_start = mapped.rfind(b"\n", 0, position) + 1
                    line_end = mapped.find(b"\n", position)
                    if line_end < 0:
                        line_end = len(mapped)
                    try:
                        candidate = json.loads(mapped[line_start:line_end].decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        candidate = None
                    if isinstance(candidate, dict) and str(candidate.get("id") or "") == str(entry_id):
                        return True
                    position = mapped.find(needle, position + len(needle))
                return False
    except FileNotFoundError:
        return False


def _append_entry_file(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    if _bank_has_id(path, entry["id"]):
        raise BankError(f"duplicate id {entry['id']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
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


def _require_canonical_reroute_evidence(entry: dict[str, Any]) -> None:
    try:
        try:
            from tools.mcp_reroute_evidence import DEFAULT_ROUTING, load_jsonl, requires_routing_link, routing_link_for_memory
        except ImportError:
            from mcp_reroute_evidence import DEFAULT_ROUTING, load_jsonl, requires_routing_link, routing_link_for_memory
        if not requires_routing_link(entry, DEFAULT_ROUTING):
            return
        routes = load_jsonl(DEFAULT_ROUTING)
    except (OSError, ValueError) as exc:
        raise BankError(f"reroute routing evidence could not be verified before memory write: {exc}") from exc
    if not routing_link_for_memory(entry, routes, DEFAULT_ROUTING):
        raise BankError(
            "reroute memory cites mcp-security-routing-events.jsonl but no matching routing event exists; "
            "append the routing event first, then record the memory"
        )


def append_entry(path: Path, values: dict[str, Any], *, publish: bool = False) -> dict[str, Any]:
    entry = _prepare_entry(values)
    if _is_canonical_bank(path):
        _require_canonical_reroute_evidence(entry)
        if _uses_default_local_overlay(path):
            DEFAULT_LOCAL_BANK.parent.mkdir(parents=True, exist_ok=True)
            with sync_lock(DEFAULT_LOCAL_BANK):
                if publish:
                    _sync_default_overlay_locked(path, strict=False)
                if _bank_has_id(path, entry["id"]) or _bank_has_id(DEFAULT_LOCAL_BANK, entry["id"]):
                    raise BankError(f"duplicate id {entry['id']}")
                saved = _append_entry_file(DEFAULT_LOCAL_BANK, entry)
                if publish:
                    _sync_default_overlay_locked(path, strict=True)
                return saved
        with sync_lock(path):
            if publish:
                _sync_canonical_locked(path, strict=False)
            saved = _append_entry_file(path, entry)
            if publish:
                _sync_canonical_locked(path, strict=True)
            return saved
    return _append_entry_file(path, entry)


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


def annotate_memory(entry: dict[str, Any]) -> dict[str, Any]:
    """Attach derived classification only; Vault memory is evidence, not behavior authority."""
    annotated = dict(entry)
    annotated["classification"] = classify_entry(entry)
    return annotated


def recent_title_entries(entries: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    effective_limit = min(MAX_RECENT_TITLES_LIMIT, max(0, DEFAULT_RECENT_TITLES_LIMIT if limit is None else limit))
    if effective_limit == 0:
        return []
    superseded = {old for entry in entries for old in entry.get("supersedes", [])}
    current = [entry for entry in entries if _ordinary_recall_eligible(entry, superseded)]
    current.sort(
        key=lambda entry: (
            parse_iso_datetime(entry["timestamp"]),
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
        }
        for entry in current[:effective_limit]
    ]



def aggregate_memory(entries: list[dict[str, Any]], limit: int = 8) -> dict[str, Any]:
    """Build a bounded query-free digest of durable Vault memory evidence."""
    effective_limit = min(MAX_RECENT_TITLES_LIMIT, max(0, limit))
    superseded = {old for entry in entries for old in entry.get("supersedes", [])}
    current = [entry for entry in entries if _ordinary_recall_eligible(entry, superseded)]
    current.sort(
        key=lambda entry: (
            parse_iso_datetime(entry["timestamp"]),
            entry["id"],
        ),
        reverse=True,
    )

    projects: Counter[str] = Counter()
    scopes: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    latest_by_project: dict[str, dict[str, Any]] = {}
    ignored_tags = {"assistant-recorded", "verbatim-source"}

    for entry in current:
        kind = str(entry.get("kind") or "unknown").strip()
        if kind:
            kinds[kind] += 1
        scope = str(entry.get("scope") or "").strip()
        if scope:
            scopes[scope] += 1
        project = str(entry.get("project") or infer_single_project(entry) or "").strip()
        if project:
            projects[project] += 1
            latest_by_project.setdefault(project, entry)
        for tag in entry.get("tags", []):
            normalized = str(tag).strip()
            if normalized and normalized.casefold() not in ignored_tags:
                tags[normalized] += 1

    def ranked(counter: Counter[str]) -> list[dict[str, Any]]:
        return [
            {"name": name, "count": count}
            for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0].casefold()))[:effective_limit]
        ]

    project_summary: list[dict[str, Any]] = []
    for name, count in sorted(projects.items(), key=lambda item: (-item[1], item[0].casefold()))[:effective_limit]:
        latest = latest_by_project[name]
        project_summary.append({
            "name": name,
            "count": count,
            "latest": {
                "id": latest["id"],
                "timestamp": latest["timestamp"],
                "title": derive_display_title(latest),
            },
        })

    return {
        "schema": "memory-bank.overview.v1",
        "contract": "Aggregated durable/historical evidence only; never current repo, runtime, scheduler, or machine truth.",
        "eligible_entries": len(current),
        "recent": recent_title_entries(entries, limit=effective_limit),
        "projects": project_summary,
        "scopes": ranked(scopes),
        "kinds": ranked(kinds),
        "top_tags": ranked(tags),
        "recurring_tags": [item for item in ranked(tags) if item["count"] >= 2],
        "incident_rollups": build_incident_rollups(current, limit=min(5, effective_limit), member_id_limit=20),
    }


def _bounded_worker_finding(value: Any, max_chars: int = MAX_WORKER_FINDING_CHARS) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def _metrics_generated_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parse_iso_datetime(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def worker_findings_overview(
    *,
    timed_metrics: Path = DEFAULT_TIMED_WORKER_METRICS,
    manual_metrics: Path = DEFAULT_MANUAL_WORKER_METRICS,
    limit: int = 3,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Summarize existing worker-report metrics projections as historical evidence."""
    effective_limit = min(5, max(0, limit))
    now = now or datetime.now().astimezone()
    populations: list[dict[str, Any]] = []
    combined_tags: Counter[str] = Counter()

    for expected_population, path in (("timed", timed_metrics), ("manual", manual_metrics)):
        base = {"population": expected_population, "path": str(path)}
        if not path.is_file():
            populations.append({**base, "status": "MISSING"})
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            populations.append({**base, "status": "INVALID", "error": str(exc)})
            continue
        if not isinstance(payload, dict):
            populations.append({**base, "status": "INVALID", "error": "metrics projection is not an object"})
            continue

        generated = _metrics_generated_at(payload.get("generated_at"))
        window_hours = float(payload.get("window_hours") or 0.0)
        source_age_hours = None
        status = "AVAILABLE"
        if generated is not None:
            try:
                source_age_hours = max(0.0, (now - generated.astimezone(now.tzinfo)).total_seconds() / 3600.0)
            except (TypeError, ValueError):
                source_age_hours = None
        if source_age_hours is not None and window_hours > 0 and source_age_hours > window_hours:
            status = "STALE_PROJECTION"

        raw_counts = payload.get("finding_tag_counts") or {}
        tag_counts: Counter[str] = Counter()
        if isinstance(raw_counts, dict):
            for name, count in raw_counts.items():
                try:
                    numeric = int(count)
                except (TypeError, ValueError):
                    continue
                if numeric > 0:
                    tag_counts[str(name)] += numeric
                    combined_tags[str(name)] += numeric
        top_tags = [
            {"name": name, "count": count}
            for name, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0].casefold()))[:effective_limit]
        ]

        recent_findings: list[dict[str, Any]] = []
        latest_reports = payload.get("latest_reports") or []
        if isinstance(latest_reports, list):
            for item in latest_reports:
                if not isinstance(item, dict):
                    continue
                finding = _bounded_worker_finding(item.get("findings"))
                if not finding:
                    continue
                recent_findings.append({
                    "display_label": item.get("display_label"),
                    "archived_at": item.get("archived_at"),
                    "repo": item.get("repo"),
                    "finding_tags": list(item.get("finding_tags") or []),
                    "finding": finding,
                })
                if len(recent_findings) >= effective_limit:
                    break

        populations.append({
            **base,
            "status": status,
            "generated_at": payload.get("generated_at"),
            "source_age_hours": round(source_age_hours, 2) if source_age_hours is not None else None,
            "window_hours": window_hours,
            "reports": int(payload.get("reports") or 0),
            "top_tags": top_tags,
            "recent_findings": recent_findings,
        })

    combined_top_tags = [
        {"name": name, "count": count}
        for name, count in sorted(combined_tags.items(), key=lambda item: (-item[1], item[0].casefold()))[:effective_limit]
    ]
    return {
        "contract": "Archived worker self-report evidence only; never current liveness, scheduler membership, progress, repo/runtime truth, behavior authority, or policy authority. Repetition never promotes a report finding into a rule.",
        "top_tags": combined_top_tags,
        "populations": populations,
    }


def _canonical_timeline_sources(
    *,
    now: datetime | None = None,
    days: int = 7,
    repo_events_per_repo: int = 100,
    artifact_events_limit: int = 240,
) -> dict[str, Any]:
    """Collect bounded local evidence streams for the canonical Vault timeline."""
    now = now or datetime.now().astimezone()
    since = now - timedelta(days=max(1, int(days)))
    vault_root = Path(__file__).resolve().parents[1]
    specs = discover_repo_specs(vault_root=vault_root)
    repo_report = collect_repo_history(specs, limit_per_repo=repo_events_per_repo, since=since)
    repo_events = repo_report["events"]
    worker_events: list[dict[str, Any]] = []
    for history_root in (DEFAULT_WORKER_HISTORY, DEFAULT_MANUAL_WORKER_HISTORY):
        worker_events.extend(worker_history_events(history_root))
    artifact_events = tracked_artifact_events(vault_root, limit=artifact_events_limit, since=since)
    return {
        "now": now,
        "since": since,
        "repo_events": repo_events,
        "worker_events": worker_events,
        "artifact_events": artifact_events,
        "source_coverage": {
            "repos": repo_report.get("coverage", {}),
            "artifacts": {
                "events": len(artifact_events),
                "limit": artifact_events_limit,
                "saturated": len(artifact_events) >= artifact_events_limit,
            },
            "workers": {"bounded": False},
        },
    }


def build_overview(
    entries: list[dict[str, Any]],
    *,
    limit: int = 8,
    timed_metrics: Path = DEFAULT_TIMED_WORKER_METRICS,
    manual_metrics: Path = DEFAULT_MANUAL_WORKER_METRICS,
    now: datetime | None = None,
    include_timeline_snapshots: bool = False,
) -> dict[str, Any]:
    overview = aggregate_memory(entries, limit=limit)
    overview["worker_findings"] = worker_findings_overview(
        timed_metrics=timed_metrics,
        manual_metrics=manual_metrics,
        limit=min(3, max(0, limit)),
        now=now,
    )
    if include_timeline_snapshots:
        sources = _canonical_timeline_sources(now=now, days=7)
        timeline = build_timeline(
            entries,
            limit=50,
            since=sources["since"],
            repo_events=sources["repo_events"],
            worker_events=sources["worker_events"],
            artifact_events=sources["artifact_events"],
            snapshot_now=sources["now"],
            source_coverage=sources["source_coverage"],
        )
        overview["timeline_snapshots"] = timeline["snapshots"]
        overview["timeline_source_health"] = {
            "matching_events": timeline["matching_events"],
            "memory_events": timeline["memory_events"],
            "repo_events": timeline["repo_events"],
            "worker_events": timeline["worker_events"],
            "artifact_events": timeline["artifact_events"],
            "invalid_source_events": timeline["invalid_source_events"],
        }
    return overview

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


def _is_entry_id(query: str) -> bool:
    return re.fullmatch(r"mem-[A-Za-z0-9_-]+", query.strip()) is not None


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
    exact_id = query.strip() if _is_entry_id(query) else None
    for entry in entries:
        if not history and not _ordinary_recall_eligible(entry, superseded):
            continue
        if exact_id is not None and entry["id"] != exact_id:
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
        relevance = 1.0 if exact_id is not None else 0.0
        if scope and entry["scope"].casefold() == scope.casefold():
            relevance += 4
        relevance += 4 * sum(tag in tag_tokens for tag in tags)
        relevance += sum(token in text_tokens or token in tag_tokens or token == entry["scope"].casefold() for token in query_tokens)
        if (query_tokens or scope or tags) and relevance == 0:
            continue
        source_score = source_relevance(entry, registry)
        stamp = parse_iso_datetime(entry["timestamp"])
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


def search_memory_entries(entries: list[dict[str, Any]], query: str, *, scope: str | None = None, tags: list[str] | None = None, limit: int = DEFAULT_RECALL_LIMIT, history: bool = False, strict_admission: bool = False) -> list[dict[str, Any]]:
    if history or _is_entry_id(query):
        return search_entries(entries, query, scope=scope, tags=tags, limit=limit, history=history)
    try:
        from .memory_hybrid import search_entries_hybrid
    except ImportError:
        from memory_hybrid import search_entries_hybrid
    return search_entries_hybrid(
        entries, query, scope=scope, tags=tags, limit=limit, history=False,
        strict_admission=strict_admission,
    )


def search_context_memory(
    entries: list[dict[str, Any]], query: str, *, scope: str | None = None,
    tags: list[str] | None = None, limit: int = MAX_RECALL_LIMIT,
) -> list[dict[str, Any]]:
    """Return bounded evidence context without promoting stored memory into behavior authority."""
    effective_limit = min(MAX_RECALL_LIMIT, max(1, int(limit)))
    if _is_entry_id(query):
        return search_memory_entries(entries, query, scope=scope, tags=tags, limit=effective_limit)
    selectors = context_selectors(query)
    filtered = [
        entry for entry in entries
        if entry_matches_selectors(entry, selectors) and context_memory_eligible(entry)
    ]
    projects = selectors.get("projects") or set()
    residual = context_residual_query(query)

    if not projects:
        residual_tokens = _tokens(residual)
        if len(residual_tokens) < 2:
            return []
        return search_memory_entries(
            filtered, residual, scope=scope, tags=tags, limit=effective_limit, history=False,
            strict_admission=True,
        )

    project_entries: list[dict[str, Any]] = []
    entity_project_entries: list[dict[str, Any]] = []
    ambient_entries: list[dict[str, Any]] = []
    for entry in filtered:
        labels = entry_context_labels(entry)
        if labels["projects"] & projects:
            project_entries.append(entry)
        elif not labels["projects"]:
            entities = set(classify_entry(entry).get("entities") or [])
            if entities & projects:
                entity_project_entries.append(entry)
            else:
                ambient_entries.append(entry)

    project_target = max(1, (effective_limit * 3 + 3) // 4)
    if len(_tokens(residual)) >= 1:
        project_hits = search_memory_entries(
            project_entries, residual, scope=scope, tags=tags, limit=project_target, history=False,
            strict_admission=True,
        )
        remaining_project = project_target - len(project_hits)
        if remaining_project > 0:
            project_hits.extend(search_memory_entries(
                entity_project_entries, residual, scope=scope, tags=tags,
                limit=remaining_project, history=False, strict_admission=True
            ))
    else:
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
                parse_iso_datetime(entry["timestamp"]),
            ),
            reverse=True,
        )
        project_hits = project_hits[:project_target]

    remaining = effective_limit - len(project_hits)
    ambient_hits: list[dict[str, Any]] = []
    if remaining > 0 and len(_tokens(residual)) >= 2:
        ambient_hits = search_memory_entries(
            ambient_entries, residual, scope=scope, tags=tags, limit=remaining, history=False,
            strict_admission=True,
        )
    return [*project_hits, *ambient_hits][:effective_limit]

def _materialized_context_query_eligible(query: str) -> bool:
    if _is_entry_id(query):
        return False
    selectors = context_selectors(query)
    residual_tokens = _tokens(context_residual_query(query))
    return len(residual_tokens) >= 2 or (bool(selectors.get("projects")) and len(residual_tokens) >= 1)


def _materialized_lesson_history(query: str, *, root: Path, limit: int = 2) -> list[dict[str, Any]]:
    """Return bounded labeled lesson priors from the existing materialized timeline only."""
    effective_limit = min(2, max(0, int(limit)))
    if effective_limit == 0 or not _materialized_context_query_eligible(query):
        return []
    try:
        from .timeline_materializer import query_materialized
    except ImportError:
        from timeline_materializer import query_materialized
    try:
        report = query_materialized(root=root, query=query, limit=max(3, effective_limit))
    except (OSError, TypeError, ValueError):
        return []
    if not isinstance(report, dict):
        return []
    packet = report.get("lesson_packet")
    if not isinstance(packet, dict) or packet.get("status") != "READY":
        return []
    materialized = report.get("materialized") if isinstance(report.get("materialized"), dict) else {}
    out: list[dict[str, Any]] = []
    for item in list(packet.get("items") or [])[:effective_limit]:
        if not isinstance(item, dict):
            continue
        prior = {
            "source_class": "HISTORICAL_CONTEXT",
            "retrieval_role": "LESSON_PRIOR",
            "source_event_id": item.get("source_event_id"),
            "source_type": item.get("source_type"),
            "project": item.get("project"),
            "event_at": item.get("event_at"),
            "title": item.get("title"),
            "conclusion": item.get("conclusion"),
            "evidence_anchors": list(item.get("evidence_anchors") or [])[:6],
            "relevance_terms": list(item.get("relevance_terms") or [])[:6],
            "changed_paths": list(item.get("changed_paths") or [])[:6],
            "lineage_event_ids": list(item.get("lineage_event_ids") or [])[:8],
            "lineage_projects": list(item.get("lineage_projects") or [])[:8],
            "lineage_copy_count": item.get("lineage_copy_count"),
            "lineage_semantics": item.get("lineage_semantics"),
            "authority": packet.get("authority"),
            "validation": packet.get("validation"),
            "live_truth_required": bool(packet.get("live_truth_required")),
            "materialized_status": materialized.get("status"),
            "materialized_as_of": materialized.get("as_of"),
        }
        out.append({key: value for key, value in prior.items() if value not in (None, "", [], {})})
    return out


def search_all_memory(entries: list[dict[str, Any]], query: str, *, scope: str | None = None, tags: list[str] | None = None, limit: int | None = None, history: bool = False, conversation_db: Path | None = None) -> list[dict[str, Any]]:
    default_limit = DEFAULT_HISTORY_LIMIT if history else DEFAULT_RECALL_LIMIT
    hard_cap = MAX_HISTORY_LIMIT if history else MAX_RECALL_LIMIT
    effective_limit = min(hard_cap, max(0, default_limit if limit is None else int(limit)))
    manual = search_memory_entries(entries, query, scope=scope, tags=tags, limit=effective_limit, history=history)
    if history or _is_entry_id(query) or not query.strip() or effective_limit == 0:
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


def attach_materialized_orientation(
    report: dict[str, Any],
    *,
    vault_root: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Attach the same materialized timeline orientation used by bootstrap."""
    vault_root = vault_root or Path(__file__).resolve().parents[1]
    try:
        from tools.timeline_materializer import load_bootstrap_projection, materialized_health
    except ImportError:
        from timeline_materializer import load_bootstrap_projection, materialized_health
    projection = load_bootstrap_projection(root=vault_root)
    if isinstance(projection, dict) and isinstance(projection.get("overview"), dict):
        projected = projection["overview"]
        report["timeline_snapshots"] = projected.get("timeline_snapshots", {})
        materialized = projected.get("timeline_materialized")
        materialized = dict(materialized) if isinstance(materialized, dict) else {}
        materialized.update(materialized_health(projection, now=now or datetime.now().astimezone()))
        report["timeline_materialized"] = materialized
        report["debugging_boundary"] = {
            "timeline_role": "HISTORICAL_ORIENTATION_AND_LINEAGE",
            "current_diagnosis": "VERIFY_THE_OWNING_LIVE_REPO_RUNTIME_SCHEDULER_OR_COORDINATOR",
            "absence_semantics": materialized.get("absence_semantics"),
        }
    else:
        report["timeline_materialized"] = {
            "status": "MISSING",
            "read_mode": "MATERIALIZED_ONLY",
            "live_truth_required": True,
            "absence_semantics": "NO_TIMELINE_ORIENTATION_AVAILABLE_DO_NOT_INFER_ABSENCE",
            "refresh_command": "python tools\\timeline_materializer.py refresh",
        }
        report["debugging_boundary"] = {
            "timeline_role": "HISTORICAL_ORIENTATION_UNAVAILABLE",
            "current_diagnosis": "VERIFY_THE_OWNING_LIVE_REPO_RUNTIME_SCHEDULER_OR_COORDINATOR",
            "absence_semantics": report["timeline_materialized"]["absence_semantics"],
        }
    return report


def _main() -> int:
    parser = argparse.ArgumentParser(description="Shared memory bank")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
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
    record.add_argument("--positive-milestone", action="store_true", help="mark an explicitly user-rewarded positive milestone with the canonical tiny star sticker")
    record.add_argument("--publish", action="store_true", help="explicitly reconcile/publish the canonical bank through Git; default record is local-only")

    search = sub.add_parser("search")
    search.add_argument("query", nargs="?", default="", help="words to match, or an exact mem-... ID; --history can read superseded/rejected records")
    search.add_argument("--scope")
    search.add_argument("--tag", action="append", default=[])
    search.add_argument("--limit", type=int)
    search.add_argument("--history", action="store_true")

    context = sub.add_parser("context", help="build a compact task-scoped context pack from curated memory and historical corpus")
    context.add_argument("query", help="task wording with project, or an exact mem-... ID; oversized records are listed in omitted_memory_ids")
    context.add_argument("--scope")
    context.add_argument("--tag", action="append", default=[])
    context.add_argument("--limit", type=int, default=MAX_RECALL_LIMIT)
    context.add_argument("--max-chars", type=int, default=DEFAULT_CONTEXT_CHARS)
    context.add_argument("--with-history", action="store_true", help="also search the preserved full-conversation corpus")

    timeline_cmd = sub.add_parser("timeline", help="derived chronology over memory, immutable worker reports, and optional local Git events")
    timeline_cmd.add_argument("query", nargs="?", default="")
    timeline_cmd.add_argument("--view", choices=("general", "project", "errors"), default="general")
    timeline_cmd.add_argument("--project")
    timeline_cmd.add_argument("--thread")
    timeline_cmd.add_argument("--limit", type=int, default=20)
    timeline_cmd.add_argument("--with-repos", action="store_true", help="merge read-only local all-branch Git commit/ref events")
    timeline_cmd.add_argument("--with-artifacts", action="store_true", help="merge Git-tracked reports/evidence/logs/screenshots/proofs/fixtures/contracts/transcripts")
    timeline_cmd.add_argument("--with-all", action="store_true", help="merge all canonical local timeline sources (repos + artifacts + timed/manual workers)")
    timeline_cmd.add_argument("--days", type=int, help="limit source collection and timeline events to the last N days")
    timeline_cmd.add_argument("--repo-events", type=int, default=20)
    timeline_cmd.add_argument("--artifact-events", type=int, default=120)
    timeline_cmd.add_argument("--repo", action="append", default=[], metavar="PROJECT=PATH")
    timeline_cmd.add_argument("--worker-history", type=Path, default=DEFAULT_WORKER_HISTORY, help="additional immutable worker-report history root")
    timeline_cmd.add_argument("--no-workers", action="store_true", help="exclude timed/manual worker-report history")
    timeline_cmd.add_argument(
        "--live-rebuild", action="store_true",
        help="explicitly rescan timeline sources instead of reading the periodic Vault materialization",
    )

    overview = sub.add_parser("overview", aliases=["digest"], help="aggregate durable Vault memory plus the current materialized timeline orientation into a bounded query-free digest")
    overview.add_argument("--limit", type=int, default=8)

    recent_titles = sub.add_parser("recent-titles", aliases=["recent"])
    recent_titles.add_argument("--limit", type=int, default=DEFAULT_RECENT_TITLES_LIMIT)

    args = parser.parse_args()
    try:
        entries = load_bank(args.bank)
        if args.command == "validate":
            _print_json({"status": "PROVEN", "entries": len(entries)})
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
            record_tags = [*args.tag, "assistant-recorded", "verbatim-source"]
            if args.positive_milestone:
                record_tags.append("positive-milestone")
            values = {
                "kind": args.kind, "scope": args.scope,
                "tags": list(dict.fromkeys(record_tags)),
                "title": args.title, "text": args.text, "state": args.state,
                "evidence": args.evidence, "supersedes": args.supersedes,
                "source_messages": args.source_message, "interpretation": args.interpretation,
                "confidence": args.confidence, "confidence_reason": args.confidence_reason,
            }
            if args.positive_milestone:
                values["positive_milestone"] = True
                values["milestone_sticker"] = POSITIVE_MILESTONE_STICKER
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
            entry = append_entry(args.bank, values, publish=args.publish)
            _print_json(entry)
            return 0
        if args.command == "timeline":
            now = datetime.now().astimezone()
            if args.days is not None and args.days < 0:
                raise BankError("--days must be non-negative")
            since = now - timedelta(days=args.days) if args.days is not None else None
            vault_root = Path(__file__).resolve().parents[1]

            # Canonical reads use the periodically materialized multi-source timeline.
            # Explicit --live-rebuild (or custom --repo inputs) is the escape hatch for
            # an intentional expensive rescan; bootstrap/workers should not do this by default.
            if not args.live_rebuild and not args.repo and args.bank.resolve() == DEFAULT_BANK.resolve():
                try:
                    from tools.timeline_materializer import query_materialized
                except ImportError:
                    from timeline_materializer import query_materialized
                materialized = query_materialized(
                    root=vault_root,
                    query=args.query,
                    view=args.view,
                    project=args.project,
                    thread=args.thread,
                    days=args.days,
                    limit=args.limit,
                    include_workers=not args.no_workers,
                )
                if materialized is not None:
                    _print_json(materialized)
                    return 0
                _print_json({
                    "status": "MISSING",
                    "authority": "DERIVED_HISTORY_ONLY",
                    "read_mode": "MATERIALIZED_ONLY",
                    "error": "periodic Vault timeline materialization is unavailable",
                    "refresh_command": "python tools\\timeline_materializer.py refresh",
                    "live_rebuild_command": "python tools\\memory_bank.py timeline --live-rebuild --with-all",
                })
                return 2

            repo_events: list[dict[str, Any]] = []
            repo_coverage: dict[str, Any] = {}
            if args.with_repos or args.with_all:
                specs = [parse_repo_arg(value) for value in args.repo]
                if not specs:
                    specs = discover_repo_specs(vault_root=vault_root)
                repo_report = collect_repo_history(specs, limit_per_repo=args.repo_events, since=since)
                repo_events = repo_report["events"]
                repo_coverage = repo_report.get("coverage", {})
            artifact_events: list[dict[str, Any]] = []
            if args.with_artifacts or args.with_all:
                artifact_events = tracked_artifact_events(vault_root, limit=args.artifact_events, since=since)
            worker_events: list[dict[str, Any]] = []
            if not args.no_workers:
                roots = [DEFAULT_WORKER_HISTORY, DEFAULT_MANUAL_WORKER_HISTORY]
                if args.worker_history not in roots:
                    roots.append(args.worker_history)
                for history_root in roots:
                    worker_events.extend(worker_history_events(history_root))
            report = build_timeline(
                entries, view=args.view, project=args.project, query=args.query, thread=args.thread,
                limit=args.limit, since=since, repo_events=repo_events, worker_events=worker_events,
                artifact_events=artifact_events, snapshot_now=now,
                source_coverage={
                    "repos": repo_coverage,
                    "artifacts": {
                        "events": len(artifact_events),
                        "limit": args.artifact_events,
                        "saturated": bool((args.with_artifacts or args.with_all) and len(artifact_events) >= args.artifact_events),
                    },
                    "workers": {"bounded": False, "included": not args.no_workers},
                },
            )
            _print_json(report)
            return 0
        if args.command in ("overview", "digest"):
            report = build_overview(entries, limit=args.limit)
            if args.bank.resolve() == DEFAULT_BANK.resolve():
                attach_materialized_orientation(report)
            _print_json(report)
            return 0
        if args.command in ("recent-titles", "recent"):
            _print_json(recent_title_entries(entries, limit=args.limit))
            return 0
        if args.command == "context":
            selected = search_context_memory(entries, args.query, scope=args.scope, tags=args.tag, limit=args.limit)
            hits = [annotate_memory(entry) for entry in selected]
            if args.bank.resolve() == DEFAULT_BANK.resolve() and not _is_entry_id(args.query):
                vault_root = Path(__file__).resolve().parents[1]
                hits.extend(_materialized_lesson_history(args.query, root=vault_root, limit=min(2, args.limit)))
            if args.with_history and not _is_entry_id(args.query):
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
