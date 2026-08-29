from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.memory_bank import load_bank, search_behavior_memory
from tools.memory_authority import behavioral_context, ROLE_USER

FIXTURE = ROOT / "tests" / "fixtures" / "memory-behavior-retrieval-v1.json"


def evaluate() -> dict:
    entries = load_bank()
    current_user = {e["id"] for e in behavioral_context(entries) if e["behavioral_authority"]["role"] == ROLE_USER}
    spec = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    expected_ids = {case["expected"] for case in spec["cases"]}
    missing_coverage = sorted(current_user - expected_ids)
    stale_expected = sorted(expected_ids - current_user)
    rows=[]
    for case in spec["cases"]:
        ids=[e["id"] for e in search_behavior_memory(entries, case["query"], limit=8)]
        rank=ids.index(case["expected"])+1 if case["expected"] in ids else None
        rows.append({**case,"rank":rank,"hits":ids})
    def metrics(cohort: str | None = None) -> dict:
        selected=[r for r in rows if cohort is None or r["cohort"] == cohort]
        n=len(selected)
        return {
            "n":n,
            "recall_at_1":sum(r["rank"] == 1 for r in selected)/n if n else 0.0,
            "recall_at_5":sum(r["rank"] is not None and r["rank"] <= 5 for r in selected)/n if n else 0.0,
            "recall_at_8":sum(r["rank"] is not None and r["rank"] <= 8 for r in selected)/n if n else 0.0,
            "mrr":sum(1/r["rank"] if r["rank"] else 0 for r in selected)/n if n else 0.0,
        }
    return {"coverage":{"active_user_rules":len(current_user),"fixture_rules":len(expected_ids),"missing":missing_coverage,"stale":stale_expected},"all":metrics(),"development":metrics("development"),"holdout":metrics("holdout"),"cases":rows}


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path); args=parser.parse_args()
    result=evaluate(); rendered=json.dumps(result,indent=2,ensure_ascii=False)+"\n"
    if args.output: args.output.write_text(rendered,encoding="utf-8")
    print(rendered,end="")
    return 0

if __name__ == "__main__": raise SystemExit(main())
