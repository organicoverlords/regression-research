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
    from .memory_git_sync import MemorySyncError, sync_bank, sync_lock
    from .memory_authority import annotate_memory, behavioral_authority
except ImportError:
    from memory_git_sync import MemorySyncError, sync_bank, sync_lock
    from memory_authority import annotate_memory, behavioral_authority

KINDS = {"fact", "decision", "lesson", "preference", "status", "correction"}
STATES = {"PROVEN", "PROVISIONAL", "REJECTED"}
REQUIRED = {"id", "timestamp", "kind", "scope", "tags", "text", "state", "evidence", "supersedes"}
DEFAULT_BANK = Path(__file__).resolve().parents[1] / "memory" / "memory-bank.jsonl"
DEFAULT_SOURCES = Path(__file__).resolve().parents[1] / "memory" / "sources.json"
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
    try:
        parsed = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise BankError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise BankError("timestamp must include a timezone offset")
    for field in ("tags", "evidence", "supersedes"):
        _string_list(entry, field)
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


def append_entry(path: Path, values: dict[str, Any]) -> dict[str, Any]:
    entry = dict(values)
    now = datetime.now().astimezone()
    entry.setdefault("id", f"mem-{now:%Y%m%d}-{secrets.token_hex(4)}")
    entry.setdefault("timestamp", now.isoformat(timespec="seconds"))
    if not entry.get("title"):
        entry.pop("title", None)
    validate_entry(entry)
    if _is_canonical_bank(path):
        with sync_lock(path):
            _sync_canonical_locked(path, strict=False)
            saved = _append_entry_file(path, entry)
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


def recent_title_entries(entries: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    effective_limit = min(MAX_RECENT_TITLES_LIMIT, max(0, DEFAULT_RECENT_TITLES_LIMIT if limit is None else limit))
    if effective_limit == 0:
        return []
    superseded = {old for entry in entries for old in entry.get("supersedes", [])}
    current = [entry for entry in entries if entry["state"] != "REJECTED" and entry["id"] not in superseded]
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
        if not history and (entry["state"] == "REJECTED" or entry["id"] in superseded):
            continue
        text_tokens = _tokens(entry["text"])
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


def _print_json(value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False) + "\n"
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        print(json.dumps(value, ensure_ascii=True))
        return
    stream.write(payload.encode("utf-8", "backslashreplace"))
    stream.flush()


def _main() -> int:
    parser = argparse.ArgumentParser(description="Shared memory bank")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")

    note = sub.add_parser("note", help="save a quick durable note")
    note.add_argument("text")
    note.add_argument("--scope", default="global")

    append = sub.add_parser("append")
    append.add_argument("--kind", required=True, choices=sorted(KINDS))
    append.add_argument("--scope", required=True)
    append.add_argument("--tag", action="append", default=[])
    append.add_argument("--title")
    append.add_argument("--text", required=True)
    append.add_argument("--state", required=True, choices=sorted(STATES))
    append.add_argument("--evidence", action="append", default=[])
    append.add_argument("--supersedes", action="append", default=[])
    append.add_argument("--standalone-correction", action="store_true", help="allow a correction that intentionally does not replace an existing memory")

    search = sub.add_parser("search")
    search.add_argument("query", nargs="?", default="")
    search.add_argument("--scope")
    search.add_argument("--tag", action="append", default=[])
    search.add_argument("--limit", type=int, default=DEFAULT_RECALL_LIMIT)
    search.add_argument("--history", action="store_true")

    history = sub.add_parser("history")
    history.add_argument("query", nargs="?", default="")
    history.add_argument("--scope")
    history.add_argument("--tag", action="append", default=[])
    history.add_argument("--limit", type=int, default=DEFAULT_HISTORY_LIMIT)

    recent_titles = sub.add_parser("recent-titles", aliases=["recent"])
    recent_titles.add_argument("--limit", type=int, default=DEFAULT_RECENT_TITLES_LIMIT)

    args = parser.parse_args()
    try:
        entries = load_bank(args.bank)
        if args.command == "validate":
            _print_json({"status": "PROVEN", "entries": len(entries)})
            return 0
        if args.command == "note":
            text = args.text.strip()
            tags = ["quick-note"]
            if text.casefold().startswith(("error:", "error ")):
                tags.append("error")
            entry = append_entry(args.bank, {"kind": "lesson", "scope": args.scope, "tags": tags, "text": text, "state": "PROVISIONAL", "evidence": [], "supersedes": []})
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
            entry = append_entry(args.bank, {"kind": args.kind, "scope": args.scope, "tags": args.tag, "title": args.title, "text": args.text, "state": args.state, "evidence": args.evidence, "supersedes": args.supersedes})
            _print_json(entry)
            return 0
        if args.command == "history":
            _print_json([annotate_memory(entry) for entry in search_entries(entries, args.query, scope=args.scope, tags=args.tag, limit=args.limit, history=True)])
            return 0
        if args.command in ("recent-titles", "recent"):
            _print_json(recent_title_entries(entries, limit=args.limit))
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
