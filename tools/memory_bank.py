from __future__ import annotations

import argparse
import json
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

KINDS = {"fact", "decision", "lesson", "preference", "status", "correction"}
STATES = {"PROVEN", "PROVISIONAL", "REJECTED"}
REQUIRED = {"id", "timestamp", "kind", "scope", "tags", "text", "state", "evidence", "supersedes"}
DEFAULT_BANK = Path(__file__).resolve().parents[1] / "memory" / "memory-bank.jsonl"
DEFAULT_SOURCES = Path(__file__).resolve().parents[1] / "memory" / "sources.json"
DEFAULT_RECALL_LIMIT = 5
MAX_RECALL_LIMIT = 8
DEFAULT_HISTORY_LIMIT = 8
MAX_HISTORY_LIMIT = 20
MAX_TEXT_CHARS = 800
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


def load_bank(path: Path = DEFAULT_BANK) -> list[dict[str, Any]]:
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


def append_entry(path: Path, values: dict[str, Any]) -> dict[str, Any]:
    entry = dict(values)
    now = datetime.now().astimezone()
    entry.setdefault("id", f"mem-{now:%Y%m%d}-{secrets.token_hex(4)}")
    entry.setdefault("timestamp", now.isoformat(timespec="seconds"))
    validate_entry(entry)
    if any(existing["id"] == entry["id"] for existing in load_bank(path)):
        raise BankError(f"duplicate id {entry['id']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return entry


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[\w-]+", value.casefold(), flags=re.UNICODE))


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



def _main() -> int:
    parser = argparse.ArgumentParser(description="Shared memory bank")
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")

    append = sub.add_parser("append")
    append.add_argument("--kind", required=True, choices=sorted(KINDS))
    append.add_argument("--scope", required=True)
    append.add_argument("--tag", action="append", default=[])
    append.add_argument("--text", required=True)
    append.add_argument("--state", required=True, choices=sorted(STATES))
    append.add_argument("--evidence", action="append", default=[])
    append.add_argument("--supersedes", action="append", default=[])

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

    args = parser.parse_args()
    try:
        entries = load_bank(args.bank)
        if args.command == "validate":
            print(json.dumps({"status": "PROVEN", "entries": len(entries)}))
            return 0
        if args.command == "append":
            entry = append_entry(args.bank, {"kind": args.kind, "scope": args.scope, "tags": args.tag, "text": args.text, "state": args.state, "evidence": args.evidence, "supersedes": args.supersedes})
            print(json.dumps(entry, ensure_ascii=False))
            return 0
        if args.command == "history":
            print(json.dumps(search_entries(entries, args.query, scope=args.scope, tags=args.tag, limit=args.limit, history=True), ensure_ascii=False))
            return 0
        if args.command == "search":
            print(json.dumps(search_entries(entries, args.query, scope=args.scope, tags=args.tag, limit=args.limit, history=args.history), ensure_ascii=False))
            return 0
    except BankError as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False))
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
