from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.memory_bank import load_bank
from tools.memory_hybrid import search_entries_hybrid

DEFAULT_BANK = ROOT / "memory" / "memory-bank.jsonl"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "memory-retrieval-eval-v1.json"


def evaluate(bank: Path, fixture: Path) -> dict:
    entries = load_bank(bank)
    spec = json.loads(fixture.read_text(encoding="utf-8-sig"))
    known = {e["id"] for e in entries}
    superseded_by: dict[str, list[str]] = {}
    for entry in entries:
        for old_id in entry.get("supersedes", []):
            superseded_by.setdefault(str(old_id), []).append(str(entry["id"]))

    def current_expected(ids: list[str]) -> list[str]:
        resolved: set[str] = set()
        pending = list(ids)
        seen: set[str] = set()
        while pending:
            item = pending.pop()
            if item in seen:
                continue
            seen.add(item)
            replacements = superseded_by.get(item, [])
            if replacements:
                pending.extend(replacements)
            else:
                resolved.add(item)
        return sorted(resolved)

    details = []
    for case in spec["cases"]:
        missing = [item for item in case["expected"] if item not in known]
        if missing:
            raise SystemExit(f"fixture references missing memory IDs for {case['id']}: {missing}")
        hits = search_entries_hybrid(entries, case["query"], limit=5)
        ids = [h["id"] for h in hits]
        resolved_expected = current_expected(case["expected"])
        expected = set(resolved_expected)
        rank = next((i + 1 for i, item in enumerate(ids) if item in expected), None) if expected else None
        details.append({
            "id": case["id"], "cohort": case["cohort"], "query": case["query"],
            "expected": case["expected"], "current_expected": resolved_expected, "hits": ids, "rank": rank, "abstained": len(ids) == 0,
        })

    def positive_metrics(cohort: str) -> dict:
        rows = [r for r in details if r["cohort"] == cohort]
        n = len(rows)
        return {
            "n": n,
            "recall_at_1": sum(r["rank"] == 1 for r in rows) / n,
            "recall_at_3": sum(r["rank"] is not None and r["rank"] <= 3 for r in rows) / n,
            "recall_at_5": sum(r["rank"] is not None and r["rank"] <= 5 for r in rows) / n,
            "mrr": sum((1.0 / r["rank"]) if r["rank"] else 0.0 for r in rows) / n,
        }

    negatives = [r for r in details if r["cohort"] == "abstain"]
    return {
        "fixture_version": spec["version"], "bank_entries": len(entries), "strategy": "hybrid",
        "metrics": {
            "paraphrase": positive_metrics("paraphrase"),
            "exact_control": positive_metrics("exact_control"),
            "abstain": {"n": len(negatives), "correct_abstention": sum(r["abstained"] for r in negatives) / len(negatives)},
        },
        "cases": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.bank, args.fixture)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
