from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

try:
    from tools.memory_bank import MAX_TEXT_CHARS
except ModuleNotFoundError:
    from memory_bank import MAX_TEXT_CHARS

_PREFIXES = (
    ("correction", re.compile(r"^Correction:\s*", re.I)),
    ("decision", re.compile(r"^Decision:\s*", re.I)),
    ("lesson", re.compile(r"^Lesson:\s*", re.I)),
    ("status", re.compile(r"^PROVEN:\s*", re.I)),
    ("preference", re.compile(r"^RULE:\s*", re.I)),
)


def _classify(line: str) -> tuple[str, str, str] | None:
    for kind, pattern in _PREFIXES:
        if pattern.match(line):
            state = "PROVISIONAL"
            return kind, pattern.sub("", line, count=1).strip(), state
    if re.match(r"^(?:do not|don't|never)\b", line, re.I):
        return "preference", line.strip(), "PROVISIONAL"
    letters = [char for char in line if char.isalpha()]
    if len(letters) >= 8 and line.upper() == line:
        return "preference", line.strip(), "PROVISIONAL"
    return None


def _candidate_id(source_id: str, evidence: list[str], text: str, kind: str) -> str:
    raw = "\x1f".join([source_id, kind, text, *evidence]).encode("utf-8")
    return "memory-candidate-" + hashlib.sha256(raw).hexdigest()[:16]


def extract_candidates(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source["source_id"])
        source_class = str(source["source_class"])
        timestamp = str(source["source_timestamp"])
        scope = str(source.get("scope") or "global")
        raw_evidence = source.get("evidence", [])
        evidence = [raw_evidence] if isinstance(raw_evidence, str) else list(raw_evidence)
        for raw_line in str(source.get("text") or "").splitlines():
            line = " ".join(raw_line.split())
            classified = _classify(line)
            if not classified:
                continue
            kind, text, state = classified
            text = text[:MAX_TEXT_CHARS]
            if not text:
                continue
            candidates.append({
                "id": _candidate_id(source_id, evidence, text, kind),
                "timestamp": timestamp,
                "kind": kind,
                "scope": scope,
                "tags": ["extracted", source_class.casefold()],
                "text": text,
                "state": state,
                "evidence": evidence,
                "supersedes": list(source.get("supersedes") or []),
                "source_id": source_id,
                "source_class": source_class,
                "source_timestamp": timestamp,
            })
    return candidates


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract compact memory candidates from bounded source snippets")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sources = _read_jsonl(args.input)
    records = extract_candidates(sources)
    _write_jsonl(args.output, records)
    print(json.dumps({"status":"PROVEN","sources":len(sources),"candidates":len(records),"output":str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
