from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from tools.memory_bank import MAX_TEXT_CHARS, validate_entry
except ModuleNotFoundError:
    from memory_bank import MAX_TEXT_CHARS, validate_entry  # type: ignore

# Bounded import: never dump full histories
MAX_DURABLE_CANDIDATES = 50
DEFAULT_SOURCE_ID = "chatgpt-personal-context"
# valid memory kinds
KINDS = {"fact", "decision", "lesson", "preference", "status", "correction"}
# unsupported kinds that must be skipped
UNSUPPORTED_KINDS = {"transient", "ephemeral", "debug", "temporary", "volatile"}

# Sensitive/private patterns — conservative: anything matching is dropped and never
# written into the public bank or issues.
_SENSITIVE_REGEXES = [
    re.compile(r"password\s*[:=]", re.I),
    re.compile(r"passwd\s*[:=]", re.I),
    re.compile(r"secret\s*[:=]", re.I),
    re.compile(r"api[_-]?key\s*[:=]", re.I),
    re.compile(r"\btoken\s*[:=]", re.I),
    re.compile(r"credential", re.I),
    re.compile(r"private\s*key", re.I),
    re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"),
    re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),  # card-like
]

# Vague/unsupported text patterns
_VAGUE_TOKENS = {"", "n/a", "none", "null", "test", "tmp"}


def _is_sensitive(text: str, meta: dict[str, Any]) -> bool:
    if meta.get("sensitive") is True or meta.get("private") is True:
        return True
    tags = meta.get("tags") or meta.get("labels") or []
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, str) and tag.casefold() in {"sensitive", "private", "secret", "pii"}:
                return True
    for pat in _SENSITIVE_REGEXES:
        if pat.search(text):
            return True
    return False


def _is_unsupported(kind: str, text: str) -> bool:
    if kind.casefold() in UNSUPPORTED_KINDS:
        return True
    stripped = text.strip()
    if len(stripped) < 10:
        return True
    if stripped.casefold() in _VAGUE_TOKENS:
        return True
    # single-token or very short entries are not stable continuity
    tokens = [t for t in re.split(r"\s+", stripped) if t]
    if len(tokens) < 2:
        return True
    return False


def _normalize_kind(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip().casefold() in KINDS:
        return raw.strip().casefold()
    # heuristics: map common export labels
    if isinstance(raw, str):
        low = raw.strip().casefold()
        if low in {"pref", "preference", "user_preference"}:
            return "preference"
        if low in {"fact", "memory", "note"}:
            return "fact"
        if low in {"lesson", "learning"}:
            return "lesson"
        if low in {"decision", "choice"}:
            return "decision"
        if low in {"status", "state"}:
            return "status"
        if low in {"correction", "fix"}:
            return "correction"
    # default: stable user-relevant material is usually preference/fact
    return "preference"


def _normalize_scope(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "global"


def _extract_text(raw: dict[str, Any]) -> str | None:
    for key in ("text", "content", "memory", "value", "description", "body"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            return " ".join(val.split())
    return None


def _parse_timestamp(raw: dict[str, Any]) -> str:
    for key in ("timestamp", "created_at", "updated_at", "source_timestamp", "time"):
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                continue
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _candidate_id(source_id: str, evidence: list[str], text: str, kind: str) -> str:
    raw = "\x1f".join([source_id, kind, text, *evidence]).encode("utf-8")
    return "memory-candidate-" + hashlib.sha256(raw).hexdigest()[:16]


def adapt_record(raw: dict[str, Any], *, source_id: str = DEFAULT_SOURCE_ID,
                 export_name: str = "export", index: int = 0) -> dict[str, Any] | None:
    text = _extract_text(raw)
    if text is None:
        return None
    # truncate early for sensitive check on full text, then bound
    bounded_text = text[:MAX_TEXT_CHARS].strip()
    if not bounded_text:
        return None
    raw_kind = raw.get("kind") or raw.get("type") or raw.get("category")
    if isinstance(raw_kind, str) and raw_kind.strip().casefold() in UNSUPPORTED_KINDS:
        return None
    kind = _normalize_kind(raw_kind)
    if kind not in KINDS:
        return None
    if _is_sensitive(bounded_text, raw):
        return None
    if _is_unsupported(kind, bounded_text):
        return None
    scope = _normalize_scope(raw.get("scope") or raw.get("project") or raw.get("area"))
    timestamp = _parse_timestamp(raw)
    # evidence with provenance — maps to DURABLE_MEMORY (75) via sources.json
    raw_id = str(raw.get("id") or raw.get("memory_id") or raw.get("identifier") or f"idx-{index}").strip()
    # keep export provenance opaque but stable
    provenance = f"durable-memory:export:{export_name}:{raw_id}"
    # if tags hint at personal context, also add personal-context prefix evidence?
    # Keep single evidence entry to stay bounded; durable-memory prefix already maps to DURABLE_MEMORY
    evidence = [provenance]
    # carry explicit evidence if provided and not sensitive
    extra = raw.get("evidence") or raw.get("source")
    if isinstance(extra, str) and extra.strip() and not _is_sensitive(extra, {}):
        # limit length and avoid duplicates
        evidence.append(extra.strip()[:200])
    elif isinstance(extra, list):
        for item in extra:
            if isinstance(item, str) and item.strip() and not _is_sensitive(item, {}):
                if len(evidence) >= 4:
                    break
                evidence.append(item.strip()[:200])
    # tags: bounded, always include provenance class tag
    tags: list[str] = ["durable-memory"]
    raw_tags = raw.get("tags") or raw.get("labels") or []
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            if isinstance(tag, str) and tag.strip():
                norm = tag.strip().casefold()
                if norm in {"sensitive", "private", "secret", "pii"}:
                    continue
                if len(tags) >= 6:
                    break
                if norm not in tags:
                    tags.append(norm)
    # ensure at least one tag beyond class is not required; keep minimal
    candidate = {
        "id": _candidate_id(source_id, evidence, bounded_text, kind),
        "timestamp": timestamp,
        "kind": kind,
        "scope": scope,
        "tags": tags,
        "text": bounded_text,
        "state": "PROVEN",
        "evidence": evidence,
        "supersedes": [],
        "source_id": source_id,
        "source_class": "DURABLE_MEMORY",
        "source_timestamp": timestamp,
    }
    try:
        validate_entry({k: candidate[k] for k in ("id","timestamp","kind","scope","tags","text","state","evidence","supersedes")})
    except Exception:
        return None
    return candidate


def adapt_export(records: Iterable[dict[str, Any]], *, source_id: str = DEFAULT_SOURCE_ID,
                 export_name: str = "export", limit: int = MAX_DURABLE_CANDIDATES) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, raw in enumerate(records):
        if len(out) >= limit:
            break
        if not isinstance(raw, dict):
            continue
        cand = adapt_record(raw, source_id=source_id, export_name=export_name, index=idx)
        if cand is None:
            continue
        if cand["id"] in seen_ids:
            continue
        seen_ids.add(cand["id"])
        out.append(cand)
    return out


def load_export(path: Path, *, source_id: str = DEFAULT_SOURCE_ID) -> list[dict[str, Any]]:
    """Load an export file. Returns [] if the surface is unavailable — never raises for
    missing files so the adapter remains optional and never becomes a startup dependency."""
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    if not text.strip():
        return []
    # try JSON array / single object first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return adapt_export([data], source_id=source_id, export_name=path.stem)
        if isinstance(data, list):
            return adapt_export(data, source_id=source_id, export_name=path.stem)
    except json.JSONDecodeError:
        pass
    # fall back to JSONL
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                records.append(obj)
        except json.JSONDecodeError:
            continue
    return adapt_export(records, source_id=source_id, export_name=path.stem)


def _read_jsonl_or_json(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
        except json.JSONDecodeError:
            continue
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional ChatGPT durable-memory and personal-context adapter")
    parser.add_argument("input", type=Path, help="export fixture (JSON array or JSONL); missing file yields 0 candidates")
    parser.add_argument("output", type=Path, help="output JSONL for curated candidates")
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID, help="source_id for provenance")
    parser.add_argument("--limit", type=int, default=MAX_DURABLE_CANDIDATES, help=f"max candidates (default {MAX_DURABLE_CANDIDATES})")
    args = parser.parse_args()

    # optional surface: missing input is not an error
    if not args.input.is_file():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("", encoding="utf-8")
        print(json.dumps({"status": "PROVEN", "candidates": 0, "output": str(args.output), "note": "surface unavailable — optional adapter produced no candidates"}))
        return 0

    raw_records = _read_jsonl_or_json(args.input)
    candidates = adapt_export(raw_records, source_id=args.source_id, export_name=args.input.stem, limit=args.limit)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for cand in candidates:
            handle.write(json.dumps(cand, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"status": "PROVEN", "candidates": len(candidates), "output": str(args.output),
                      "source_class": "DURABLE_MEMORY", "bounded": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
