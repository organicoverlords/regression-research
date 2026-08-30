from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

try:
    from .memory_authority import ROLE_ADVISORY, ROLE_USER, behavioral_authority, behavioral_context
    from .memory_bank import load_bank, search_entries
    from .memory_hybrid import search_entries_hybrid
except ImportError:
    from memory_authority import ROLE_ADVISORY, ROLE_USER, behavioral_authority, behavioral_context
    from memory_bank import load_bank, search_entries
    from memory_hybrid import search_entries_hybrid

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "memory-holdout-v1.json"
BANK = ROOT / "memory" / "memory-bank.jsonl"


def _metrics(ranks: list[int | None]) -> dict[str, Any]:
    n = len(ranks)
    return {
        "n": n,
        "recall_at_1": sum(rank is not None and rank <= 1 for rank in ranks) / n if n else 0.0,
        "recall_at_3": sum(rank is not None and rank <= 3 for rank in ranks) / n if n else 0.0,
        "recall_at_5": sum(rank is not None and rank <= 5 for rank in ranks) / n if n else 0.0,
        "mrr": sum((1.0 / rank) if rank else 0.0 for rank in ranks) / n if n else 0.0,
    }


def _rank(ids: list[str], expected: str) -> int | None:
    try:
        return ids.index(expected) + 1
    except ValueError:
        return None


def _eval_strategy(entries: list[dict[str, Any]], pairs: list[dict[str, Any]], fn: Callable[..., list[dict[str, Any]]]) -> dict[str, Any]:
    cases = []
    ranks: list[int | None] = []
    stale_leaks = 0
    for case in pairs:
        hits = fn(entries, case["query"], limit=8)
        ids = [str(entry["id"]) for entry in hits]
        rank = _rank(ids, case["correction_id"])
        stale_present = case["old_id"] in ids
        stale_leaks += int(stale_present)
        ranks.append(rank)
        cases.append({
            "old_id": case["old_id"],
            "correction_id": case["correction_id"],
            "rank": rank,
            "stale_present": stale_present,
            "top_ids": ids,
        })
    return {"metrics": _metrics(ranks), "stale_leaks": stale_leaks, "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    bank_hash = hashlib.sha256(BANK.read_bytes()).hexdigest()
    if bank_hash != fixture["bank_sha256"]:
        raise SystemExit(f"bank hash drift: fixture={fixture['bank_sha256']} current={bank_hash}")
    entries = load_bank()
    by_id = {str(entry["id"]): entry for entry in entries}
    behavioral_ids = {str(entry["id"]) for entry in behavioral_context(entries)}

    authority_pairs = []
    authority_failures = 0
    for case in fixture["pairs"]:
        old = by_id[case["old_id"]]
        correction = by_id[case["correction_id"]]
        old_in_context = case["old_id"] in behavioral_ids
        correction_auth = behavioral_authority(correction)
        user_backed = any(str(ev).startswith("user-instruction:") for ev in correction.get("evidence", []))
        user_authority_ok = (not user_backed) or (correction_auth["role"] == ROLE_USER and correction_auth["may_change_behavior"])
        passed = (not old_in_context) and user_authority_ok
        authority_failures += int(not passed)
        authority_pairs.append({
            "old_id": case["old_id"],
            "correction_id": case["correction_id"],
            "old_in_behavioral_context": old_in_context,
            "correction_authority": correction_auth,
            "user_backed": user_backed,
            "passed": passed,
        })

    negatives = []
    negative_failures = 0
    for control in fixture["negative_controls"]:
        entry = by_id[control["id"]]
        auth = behavioral_authority(entry)
        passed = auth["role"] == ROLE_ADVISORY and not auth["may_change_behavior"]
        negative_failures += int(not passed)
        negatives.append({"id": control["id"], "authority": auth, "passed": passed})

    payload = {
        "schema": "memory-holdout-result-v1",
        "issue": 176,
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "bank_sha256": bank_hash,
        "bank_entries": len(entries),
        "legacy": _eval_strategy(entries, fixture["pairs"], search_entries),
        "hybrid": _eval_strategy(entries, fixture["pairs"], search_entries_hybrid),
        "authority": {
            "pair_failures": authority_failures,
            "negative_failures": negative_failures,
            "pairs": authority_pairs,
            "negative_controls": negatives,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "legacy": payload["legacy"]["metrics"],
        "hybrid": payload["hybrid"]["metrics"],
        "legacy_stale_leaks": payload["legacy"]["stale_leaks"],
        "hybrid_stale_leaks": payload["hybrid"]["stale_leaks"],
        "authority_pair_failures": authority_failures,
        "authority_negative_failures": negative_failures,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

