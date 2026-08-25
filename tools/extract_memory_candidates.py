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


_FRUSTRATION_MARKERS = ("asshole", "fuck you")

def _looks_like_keyboard_smash(text: str) -> bool:
    compact = "".join(ch for ch in text.casefold() if ch.isalpha())
    if len(compact) < 10 or " " in text.strip():
        return False
    vowels = sum(ch in "aeiouy??" for ch in compact)
    return vowels / len(compact) < 0.35

def _is_strong_negative_feedback(text: str) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in _FRUSTRATION_MARKERS) or _looks_like_keyboard_smash(text)

def extract_negative_feedback_candidates(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(sources)
    out: list[dict[str, Any]] = []
    for i, source in enumerate(rows):
        text = " ".join(str(source.get("text") or "").split())
        if not _is_strong_negative_feedback(text):
            continue
        previous = rows[i - 1] if i else None
        if not previous or str(previous.get("role", "")).casefold() != "assistant":
            continue
        correction = rows[i + 1] if i + 1 < len(rows) else None
        lesson = "Avoid repeating the preceding assistant behavior after strong negative feedback: " + " ".join(str(previous.get("text") or "").split())
        if correction and str(correction.get("role", "")).casefold() == "user":
            lesson += ". User correction: " + " ".join(str(correction.get("text") or "").split())
        lesson = lesson[:MAX_TEXT_CHARS]
        evidence = [str(source.get("evidence") or source.get("source_id") or f"turn-{i}")]
        out.append({
            "id": _candidate_id(str(source.get("source_id") or "corpus"), evidence, lesson, "lesson"),
            "timestamp": str(source["source_timestamp"]), "kind": "lesson",
            "scope": str(source.get("scope") or "global"),
            "tags": ["extracted", "negative-feedback"], "text": lesson,
            "state": "PROVISIONAL", "evidence": evidence, "supersedes": [],
            "source_id": str(source.get("source_id") or "corpus"),
            "source_class": str(source.get("source_class") or "HISTORICAL_CONTEXT"),
            "source_timestamp": str(source["source_timestamp"]),
        })
    return out

def _candidate_id(source_id: str, evidence: list[str], text: str, kind: str) -> str:
    raw = "\x1f".join([source_id, kind, text, *evidence]).encode("utf-8")
    return "memory-candidate-" + hashlib.sha256(raw).hexdigest()[:16]


def extract_candidates(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    source_rows = list(sources)
    candidates: list[dict[str, Any]] = []
    for source in source_rows:
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
    candidates.extend(extract_negative_feedback_candidates(source_rows))
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
