from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from conversation_search import DEFAULT_DB, DISCOVERY_RE, _zip_relevant, discover_roots, index_roots

MAX_DEPTH = 3
CONVERSATION_FILES = {"conversations.json", "conversation.json"}


def _key(path: Path) -> str:
    return str(path.resolve(strict=False)).casefold()


def _covered(candidate: Path, roots: list[Path]) -> bool:
    resolved = candidate.resolve(strict=False)
    for root in roots:
        root_resolved = root.resolve(strict=False)
        if root_resolved.is_dir():
            try:
                resolved.relative_to(root_resolved)
                return True
            except ValueError:
                pass
        elif _key(resolved) == _key(root_resolved):
            return True
    return False


def discover_extended(downloads: Path, max_depth: int = MAX_DEPTH) -> list[Path]:
    roots = list(discover_roots(downloads))
    seen = {_key(path) for path in roots}
    if not downloads.is_dir():
        return roots

    base_parts = len(downloads.resolve(strict=False).parts)
    for current, dirs, files in os.walk(downloads):
        current_path = Path(current)
        depth = len(current_path.resolve(strict=False).parts) - base_parts
        if depth >= max_depth:
            dirs[:] = []
        if depth > max_depth:
            continue

        for dirname in list(dirs):
            child = current_path / dirname
            if DISCOVERY_RE.search(dirname) and not _covered(child, roots):
                key = _key(child)
                if key not in seen:
                    seen.add(key)
                    roots.append(child)

        for filename in files:
            path = current_path / filename
            lower = filename.casefold()
            candidate: Path | None = None
            if lower in CONVERSATION_FILES:
                candidate = current_path
            elif path.suffix.casefold() == ".zip" and _zip_relevant(path):
                candidate = path
            if candidate is None or _covered(candidate, roots):
                continue
            key = _key(candidate)
            if key not in seen:
                seen.add(key)
                roots.append(candidate)
    return roots


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded refresh of the downloaded full-conversation search index.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--max-depth", type=int, default=MAX_DEPTH)
    parser.add_argument("--discover-only", action="store_true")
    args = parser.parse_args()

    depth = max(1, min(6, int(args.max_depth)))
    roots = discover_extended(args.downloads, max_depth=depth)
    if args.discover_only:
        print(json.dumps({"roots": [str(path) for path in roots], "max_depth": depth}, ensure_ascii=False, indent=2))
        return 0 if roots else 2
    if not roots:
        print(json.dumps({"status": "NOT_PROVEN", "error": "no conversation sources discovered"}, ensure_ascii=False))
        return 2
    result = index_roots(args.db, roots)
    result["discovery_max_depth"] = depth
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
