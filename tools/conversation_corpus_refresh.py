from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .conversation_corpus import DEFAULT_ROOT, _load_manifest, sync_source, verify
    from .conversation_search import DEFAULT_DB, index_roots
    from .conversation_search_refresh import rebuild_index
except ImportError:
    from conversation_corpus import DEFAULT_ROOT, _load_manifest, sync_source, verify
    from conversation_search import DEFAULT_DB, index_roots
    from conversation_search_refresh import rebuild_index


def configured_imports(corpus_root: Path = DEFAULT_ROOT) -> list[dict[str, str]]:
    manifest = _load_manifest(corpus_root / "manifest.json")
    out: list[dict[str, str]] = []
    for item in manifest.get("imports", []):
        label = str(item.get("label") or "").strip()
        source = str(item.get("original_source") or "").strip()
        if not label or not source:
            continue
        out.append({"label": label, "source": source})
    return out


def refresh_corpus(
    *,
    corpus_root: Path = DEFAULT_ROOT,
    db: Path = DEFAULT_DB,
    labels: set[str] | None = None,
    index: bool = True,
    full_rebuild: bool = False,
    full_verify: bool = False,
    min_age_seconds: float = 120.0,
) -> dict[str, Any]:
    imports = configured_imports(corpus_root)
    selected = [item for item in imports if labels is None or item["label"] in labels]
    unknown = sorted((labels or set()) - {item["label"] for item in imports})
    if unknown:
        return {"status": "REJECTED", "error": "unknown import label(s): " + ", ".join(unknown)}

    synced: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    for item in selected:
        source = Path(item["source"])
        if not source.exists():
            unavailable.append(item)
            continue
        synced.append(sync_source(source, item["label"], corpus_root, min_age_seconds=min_age_seconds))

    verification = verify(corpus_root, hashes=full_verify)
    if verification.get("status") != "PROVEN":
        return {
            "status": "REJECTED",
            "synced": synced,
            "unavailable": unavailable,
            "verification": verification,
        }

    index_result = None
    if index:
        index_result = rebuild_index(db, corpus_root) if full_rebuild else index_roots(db, [corpus_root], force=False)
        if index_result.get("status") != "PROVEN":
            return {
                "status": "REJECTED",
                "synced": synced,
                "unavailable": unavailable,
                "verification": verification,
                "index": index_result,
            }

    return {
        "status": "PROVEN",
        "synced": synced,
        "unavailable": unavailable,
        "verification": verification,
        "index": index_result,
        "copied": sum(int(item.get("copied") or 0) for item in synced),
        "reused": sum(int(item.get("reused") or 0) for item in synced),
        "fast_reused": sum(int(item.get("fast_reused") or 0) for item in synced),
        "revisions_copied": sum(int(item.get("revisions_copied") or 0) for item in synced),
        "deferred_unstable": sum(int(item.get("deferred_unstable") or 0) for item in synced),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Incrementally preserve configured conversation exports and atomically rebuild the Vault search index.")
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument("--full-verify", action="store_true")
    parser.add_argument("--min-age-seconds", type=float, default=120.0)
    args = parser.parse_args()
    try:
        result = refresh_corpus(
            corpus_root=args.corpus_root,
            db=args.db,
            labels=set(args.label) if args.label else None,
            index=not args.no_index,
            full_rebuild=args.rebuild_index,
            full_verify=args.full_verify,
            min_age_seconds=args.min_age_seconds,
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "REJECTED", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
