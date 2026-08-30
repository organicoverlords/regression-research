from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BANK = ROOT / "memory" / "memory-bank.jsonl"
OUT = ROOT / "tests" / "fixtures" / "memory-holdout-v1.json"
MEM_ID_RE = re.compile(r"mem-[A-Za-z0-9_-]+")
PAIR_LIMIT = 20
NEGATIVE_LIMIT = 20
TEXT_PREFIX_CHARS = 160
SENTINELS = {
    "mem-20260827-afce2baf",
    "mem-20260827-9a770b5b",
    "mem-20260827-d4e21c4c",
}


def _load_bank() -> list[dict[str, Any]]:
    return [json.loads(line) for line in BANK.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _normalize_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _derived_title(entry: dict[str, Any]) -> str:
    explicit = entry.get("title")
    if isinstance(explicit, str) and explicit.strip():
        return _normalize_ws(explicit)
    text = _normalize_ws(str(entry.get("text") or ""))
    if len(text) <= 80:
        return text
    return text[:79].rstrip() + "…"


def _issue172_exclusions() -> set[str]:
    paths = list((ROOT / "tests" / "fixtures").glob("*issue172*"))
    paths += list((ROOT / "03 Fixtures and Experiments").glob("*issue172*"))
    paths += [ROOT / "tests" / "test_memory_authority.py"]
    found = set(SENTINELS)
    for path in paths:
        if path.is_file():
            found.update(MEM_ID_RE.findall(path.read_text(encoding="utf-8-sig", errors="replace")))
    return found


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def main() -> int:
    entries = _load_bank()
    by_id = {str(entry["id"]): entry for entry in entries}
    superseded = {old for entry in entries for old in entry.get("supersedes", [])}
    exclusions = _issue172_exclusions()

    pairs: list[dict[str, Any]] = []
    for correction in entries:
        correction_id = str(correction["id"])
        if correction.get("kind") != "correction" or correction.get("state") == "REJECTED":
            continue
        if correction_id in superseded or correction_id in exclusions:
            continue
        for old_id in correction.get("supersedes", []):
            if old_id not in by_id or old_id in exclusions:
                continue
            old = by_id[old_id]
            key = f"{old_id}->{correction_id}"
            prefix = _normalize_ws(str(old.get("text") or ""))[:TEXT_PREFIX_CHARS]
            title = _derived_title(old)
            query = _normalize_ws(f"{title} {prefix}")
            pairs.append({
                "selection_sha256": _sha(key),
                "old_id": old_id,
                "correction_id": correction_id,
                "query": query,
            })
    pairs.sort(key=lambda item: item["selection_sha256"])
    pairs = pairs[:PAIR_LIMIT]

    negatives: list[dict[str, Any]] = []
    for entry in entries:
        ident = str(entry["id"])
        if ident in exclusions or ident in superseded or entry.get("state") == "REJECTED":
            continue
        if entry.get("kind") not in {"fact", "lesson"}:
            continue
        negatives.append({
            "selection_sha256": _sha(ident),
            "id": ident,
            "kind": entry.get("kind"),
            "state": entry.get("state"),
        })
    negatives.sort(key=lambda item: item["selection_sha256"])
    negatives = negatives[:NEGATIVE_LIMIT]

    payload = {
        "schema": "memory-holdout-v1",
        "issue": 176,
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "bank_sha256": hashlib.sha256(BANK.read_bytes()).hexdigest(),
        "bank_entries": len(entries),
        "selection": {
            "pair_limit": PAIR_LIMIT,
            "negative_limit": NEGATIVE_LIMIT,
            "text_prefix_chars": TEXT_PREFIX_CHARS,
            "pair_order": "sha256(old_id + '->' + correction_id), lowercase hex ascending",
            "negative_order": "sha256(memory_id), lowercase hex ascending",
            "issue172_excluded_ids": sorted(exclusions),
        },
        "pairs": pairs,
        "negative_controls": negatives,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"pairs": len(pairs), "negatives": len(negatives), "bank_entries": len(entries), "output": str(OUT.relative_to(ROOT))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
