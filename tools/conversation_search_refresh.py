from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    from .conversation_search import DEFAULT_CORPUS_ROOT, DEFAULT_DB, index_roots
except ImportError:
    from conversation_search import DEFAULT_CORPUS_ROOT, DEFAULT_DB, index_roots


def rebuild_index(db: Path = DEFAULT_DB, corpus_root: Path = DEFAULT_CORPUS_ROOT) -> dict:
    if not corpus_root.is_dir():
        return {"status": "NOT_PROVEN", "error": f"canonical Vault conversation corpus missing: {corpus_root}"}
    db.parent.mkdir(parents=True, exist_ok=True)
    temp = db.with_name(db.name + f".rebuild-{os.getpid()}")
    for path in (temp, Path(str(temp) + "-wal"), Path(str(temp) + "-shm")):
        path.unlink(missing_ok=True)
    result = index_roots(temp, [corpus_root], force=True)
    if result["status"] != "PROVEN":
        return result
    for sidecar in (Path(str(temp) + "-wal"), Path(str(temp) + "-shm")):
        if sidecar.exists() and sidecar.stat().st_size:
            raise RuntimeError(f"temporary SQLite sidecar did not checkpoint: {sidecar}")
        sidecar.unlink(missing_ok=True)
    for sidecar in (Path(str(db) + "-wal"), Path(str(db) + "-shm")):
        sidecar.unlink(missing_ok=True)
    os.replace(temp, db)
    result["db"] = str(db)
    result["canonical_corpus_root"] = str(corpus_root)
    result["rebuild"] = "atomic-fresh"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild full-text search solely from the canonical Vault conversation corpus.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    args = parser.parse_args()
    try:
        result = rebuild_index(args.db, args.corpus_root)
    except (OSError, RuntimeError) as exc:
        result = {"status": "REJECTED", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
