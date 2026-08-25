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
DEFAULT_FRUSTRATION_MARKERS = ("ASSHOLE", "FUCK YOU", "asädasdnasdnda")


def _classify(line: str) -> tuple[str, str, str] | None:
    for kind, pattern in _PREFIXES:
        if pattern.match(line):
            return kind, pattern.sub("", line, count=1).strip(), "PROVISIONAL"
    if re.match(r"^(?:do not|don't|never)\b", line, re.I):
        return "preference", line.strip(), "PROVISIONAL"
    letters = [char for char in line if char.isalpha()]
    if len(letters) >= 8 and line.upper() == line:
        return "preference", line.strip(), "PROVISIONAL"
    return None


def _candidate_id(source_id: str, evidence: list[str], text: str, kind: str) -> str:
    raw = "\x1f".join([source_id, kind, text, *evidence]).encode("utf-8")
    return "memory-candidate-" + hashlib.sha256(raw).hexdigest()[:16]


def _candidate(source_id: str, source_class: str, timestamp: str, scope: str,
               evidence: list[str], text: str, kind: str, tags: list[str],
               supersedes: list[str] | None = None) -> dict[str, Any]:
    text = text[:MAX_TEXT_CHARS]
    return {
        "id": _candidate_id(source_id, evidence, text, kind), "timestamp": timestamp,
        "kind": kind, "scope": scope, "tags": tags, "text": text,
        "state": "PROVISIONAL", "evidence": evidence,
        "supersedes": list(supersedes or []), "source_id": source_id,
        "source_class": source_class, "source_timestamp": timestamp,
    }


def extract_negative_feedback_candidates(
    sources: Iterable[dict[str, Any]], markers: Iterable[str] = DEFAULT_FRUSTRATION_MARKERS
) -> list[dict[str, Any]]:
    """Extract bounded lesson candidates around strong user-frustration turns.

    Conversation-shaped sources provide ``turns`` with role/text/evidence. The marker
    itself is never stored as lesson text: the candidate describes the preceding
    assistant action plus the following assistant correction, when present.
    """
    needles = tuple(m.casefold() for m in markers if m.strip())
    out: list[dict[str, Any]] = []
    for source in sources:
        turns = list(source.get("turns") or [])
        for index, turn in enumerate(turns):
            text = " ".join(str(turn.get("text") or "").split())
            if str(turn.get("role") or "").casefold() != "user" or not any(n in text.casefold() for n in needles):
                continue
            previous = next((turns[i] for i in range(index - 1, -1, -1)
                             if str(turns[i].get("role") or "").casefold() == "assistant"), None)
            following = next((turns[i] for i in range(index + 1, len(turns))
                              if str(turns[i].get("role") or "").casefold() == "assistant"), None)
            if not previous:
                continue
            before = " ".join(str(previous.get("text") or "").split())
            after = " ".join(str((following or {}).get("text") or "").split())
            lesson = f"Problematic assistant behavior: {before}"
            if after:
                lesson += f" Correction: {after}"
            evidence_value = turn.get("evidence") or source.get("evidence") or f"{source['source_id']}:turn-{index}"
            evidence = [evidence_value] if isinstance(evidence_value, str) else list(evidence_value)
            out.append(_candidate(
                str(source["source_id"]), str(source["source_class"]), str(source["source_timestamp"]),
                str(source.get("scope") or "global"), evidence, lesson, "lesson",
                ["extracted", str(source["source_class"]).casefold(), "negative-feedback"],
                list(source.get("supersedes") or []),
            ))
    return out


def extract_candidates(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = list(sources)
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
            kind, text, _state = classified
            if text:
                candidates.append(_candidate(source_id, source_class, timestamp, scope, evidence,
                                             text, kind, ["extracted", source_class.casefold()],
                                             list(source.get("supersedes") or [])))
    candidates.extend(extract_negative_feedback_candidates(sources))
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
