from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.memory_bank import load_bank, search_entries
from tools.memory_hybrid import search_entries_hybrid

DEFAULT_BANK = ROOT / "memory" / "memory-bank.jsonl"
DEFAULT_FIXTURE = ROOT / "tests" / "fixtures" / "memory-retrieval-eval-v1.json"


def evaluate(bank: Path, fixture: Path, strategy: str = "baseline") -> dict:
    entries = load_bank(bank)
    spec = json.loads(fixture.read_text(encoding="utf-8-sig"))
    known = {e["id"] for e in entries}
    details = []
    search = search_entries_hybrid if strategy == "hybrid" else search_entries
    for case in spec["cases"]:
        missing = [item for item in case["expected"] if item not in known]
        if missing:
            raise SystemExit(f"fixture references missing memory IDs for {case['id']}: {missing}")
        hits = search(entries, case["query"], limit=5)
        ids = [h["id"] for h in hits]
        expected = set(case["expected"])
        rank = next((i + 1 for i, item in enumerate(ids) if item in expected), None) if expected else None
        details.append({
            "id": case["id"], "cohort": case["cohort"], "query": case["query"],
            "expected": case["expected"], "hits": ids, "rank": rank, "abstained": len(ids) == 0,
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
        "fixture_version": spec["version"], "bank_entries": len(entries), "strategy": strategy,
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
    parser.add_argument("--strategy", choices=("baseline", "hybrid"), default="baseline")
    args = parser.parse_args()
    result = evaluate(args.bank, args.fixture, args.strategy)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
