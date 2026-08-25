from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from tools.memory_bank import append_entry, load_bank, validate_entry
except ModuleNotFoundError:
    from memory_bank import append_entry, load_bank, validate_entry


def _semantic_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        entry["kind"].casefold(),
        entry["scope"].casefold(),
        " ".join(entry["text"].split()).casefold(),
        entry["state"],
    )


def migrate_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str]] = []
    for candidate in candidates:
        validate_entry(candidate)
        key = _semantic_key(candidate)
        if key not in merged:
            merged[key] = dict(candidate)
            merged[key]["tags"] = list(dict.fromkeys(candidate["tags"]))
            merged[key]["evidence"] = list(dict.fromkeys(candidate["evidence"]))
            merged[key]["supersedes"] = list(dict.fromkeys(candidate["supersedes"]))
            order.append(key)
            continue
        current = merged[key]
        current["tags"] = list(dict.fromkeys(current["tags"] + candidate["tags"]))
        current["evidence"] = list(dict.fromkeys(current["evidence"] + candidate["evidence"]))
        current["supersedes"] = list(dict.fromkeys(current["supersedes"] + candidate["supersedes"]))
    return [merged[key] for key in order]


def read_candidates(path: Path) -> list[dict[str, Any]]:
    return load_bank(path)


def write_bank(entries: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("", encoding="utf-8")
    for entry in entries:
        append_entry(output, entry)


def main() -> int:
    parser = argparse.ArgumentParser(description="Curate prepared memory-bank candidates")
    parser.add_argument("candidates", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    entries = migrate_candidates(read_candidates(args.candidates))
    write_bank(entries, args.output)
    print(json.dumps({"status":"PROVEN","entries":len(entries),"output":str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
