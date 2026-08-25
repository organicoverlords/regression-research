from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_INDEX = REPO / "02 Evidence" / "2026-08-25_screenshot_execution_state_index.json"


def load_index(path: Path = DEFAULT_INDEX) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def searchable_text(case: dict) -> str:
    parts: list[str] = []
    for key in ("id", "filename", "polarity", "phenotype", "observation", "contrast"):
        value = case.get(key)
        if value:
            parts.append(str(value))
    parts.extend(str(x) for x in case.get("filenames", []))
    parts.extend(str(x) for x in case.get("tags", []))
    return " ".join(parts).casefold()


def search(query: str, *, path: Path = DEFAULT_INDEX, min_rating: int = 1) -> list[dict]:
    needle = query.casefold().strip()
    cases = load_index(path).get("cases", [])
    return [c for c in cases if int(c.get("rating", 0)) >= min_rating and needle in searchable_text(c)]
def main() -> int:
    parser = argparse.ArgumentParser(description="Search rated conversation screenshot evidence")
    parser.add_argument("query", help="substring matched across ids, tags, filenames and descriptions")
    parser.add_argument("--min-rating", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args()
    matches = search(args.query, path=args.index, min_rating=args.min_rating)
    print(json.dumps({"query": args.query, "count": len(matches), "matches": matches}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
