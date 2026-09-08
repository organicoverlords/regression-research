from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "stack-atlas.tiny3d-current.v1"
DEFAULT_LIBRARY_ROOT = Path(r"C:\Users\Lauri\Desktop\Tiny3D_LIBRARY")
CACHE_RELATIVE = Path(".tiny3d") / "library" / "index-v1.json"
SHOWROOM_RELATIVE = Path(".tiny3d") / "library" / "showroom-v2-catalog-v1.json"
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_RESULTS = 20


def _load_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"source missing: {path}")
    size = path.stat().st_size
    if size > MAX_SOURCE_BYTES:
        raise ValueError(f"source exceeds {MAX_SOURCE_BYTES} bytes: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"source is not readable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"source is not a JSON object: {path}")
    return value


def _source_fact(path: Path, payload: dict[str, Any], *, freshness: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "schema": payload.get("schema"),
        "bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "freshness_semantics": freshness,
    }


def _signature_target(asset_dir: Path, label: str) -> Path | None:
    if label == ".":
        return asset_dir
    if label.startswith("upstream[") and "]:" in label:
        raw = label.split("]:", 1)[1]
        target = Path(raw)
        return target if target.is_absolute() else asset_dir / target
    if not label or label.startswith("upstream["):
        return None
    return asset_dir / Path(label.replace("/", "\\"))


def _signature_freshness(cache_entry: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    signature = cache_entry.get("signature")
    asset_dir_raw = record.get("asset_dir")
    if not isinstance(signature, list) or not isinstance(asset_dir_raw, str) or not asset_dir_raw:
        return {"state": "UNKNOWN_NO_SIGNATURE", "checked": 0, "mismatches": []}
    asset_dir = Path(asset_dir_raw)
    mismatches: list[dict[str, Any]] = []
    checked = 0
    for expected in signature:
        if not isinstance(expected, dict) or not isinstance(expected.get("path"), str):
            mismatches.append({"path": None, "reason": "invalid_signature_record"})
            continue
        label = expected["path"]
        target = _signature_target(asset_dir, label)
        if target is None:
            mismatches.append({"path": label, "reason": "unresolvable_signature_path"})
            continue
        checked += 1
        exists = target.exists()
        if bool(expected.get("exists")) != exists:
            mismatches.append({"path": label, "reason": "existence_changed"})
            continue
        if not exists:
            continue
        try:
            stat = target.stat()
        except OSError:
            mismatches.append({"path": label, "reason": "stat_failed"})
            continue
        if isinstance(expected.get("bytes"), int) and stat.st_size != expected["bytes"]:
            mismatches.append({"path": label, "reason": "size_changed"})
        if isinstance(expected.get("mtime_ns"), int) and stat.st_mtime_ns != expected["mtime_ns"]:
            mismatches.append({"path": label, "reason": "mtime_changed"})
    return {
        "state": "CURRENT_SIGNATURE_MATCH" if not mismatches else "STALE_SIGNATURE_MISMATCH",
        "checked": checked,
        "mismatches": mismatches[:8],
        "mismatches_truncated": len(mismatches) > 8,
    }


def _matches(record: dict[str, Any], query: str) -> bool:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    values = (
        record.get("asset_id"),
        record.get("directory_name"),
        record.get("display_name"),
        record.get("profile"),
        source.get("name"),
        source.get("path"),
    )
    needle = query.casefold()
    return any(needle in str(value).casefold() for value in values if value is not None)


def _durable_fact(value: Any, asset_dir: Path) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {"state": "NOT_DECLARED", "path": None, "present": False}
    target = Path(value)
    if not target.is_absolute():
        target = asset_dir / target
    present = target.is_file()
    return {
        "state": "PRESENT" if present else "DECLARED_PATH_MISSING",
        "path": str(target),
        "present": present,
    }


def _proof_projection(record: dict[str, Any], freshness: dict[str, Any]) -> dict[str, Any]:
    if freshness.get("state") != "CURRENT_SIGNATURE_MATCH":
        return {
            "current_state": "UNKNOWN_STALE_OR_UNVERIFIED_CACHE",
            "reason": freshness.get("state"),
        }
    proof = record.get("proof") if isinstance(record.get("proof"), dict) else {}
    states = proof.get("states") if isinstance(proof.get("states"), dict) else {}
    latest = proof.get("latest_visual_proof") if isinstance(proof.get("latest_visual_proof"), dict) else {}
    bundle = proof.get("proof_bundle") if isinstance(proof.get("proof_bundle"), dict) else {}
    reviewed = proof.get("reviewed_visual_proof") if isinstance(proof.get("reviewed_visual_proof"), list) else []
    review_state = proof.get("independent_review_state")
    if not isinstance(review_state, str) or not review_state:
        review_state = "NOT_RECORDED" if not reviewed else "REVIEW_RECORD_PRESENT_STATE_UNSPECIFIED"
    asset_dir = Path(str(record.get("asset_dir") or "."))
    return {
        "current_state": "CURRENT_SIGNATURE_MATCH",
        "strongest_state": proof.get("strongest_state"),
        "p3_runtime_proven": states.get("P3_RUNTIME_PROVEN") is True,
        "proof_bundle_state": bundle.get("state"),
        "durable_visual": _durable_fact(latest.get("durable_path"), asset_dir),
        "durable_motion_sequence": _durable_fact(latest.get("durable_motion_sequence_path"), asset_dir),
        "independent_review_state": review_state,
        "metadata_gaps": proof.get("metadata_gaps") if isinstance(proof.get("metadata_gaps"), list) else [],
    }


def _showroom_index(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    for row in assets:
        if not isinstance(row, dict):
            continue
        ids = row.get("tiny3d_asset_ids") if isinstance(row.get("tiny3d_asset_ids"), list) else []
        for asset_id in ids:
            if isinstance(asset_id, str) and asset_id:
                result.setdefault(asset_id, []).append(row)
    return result


def _showroom_projection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"state": "NOT_LINKED_IN_MATERIALIZED_CATALOGUE", "match_count": 0}
    if len(rows) > 1:
        return {
            "state": "AMBIGUOUS_MATERIALIZED_LINKAGE",
            "match_count": len(rows),
            "logical_ids": [row.get("logical_id") for row in rows],
        }
    row = rows[0]
    return {
        "state": "LINKED_MATERIALIZED_CATALOGUE",
        "match_count": 1,
        "catalog_state": row.get("catalog_state"),
        "zone": row.get("zone"),
        "logical_id": row.get("logical_id"),
        "display_name": row.get("display_name"),
        "freshness_semantics": "MATERIALIZED_SOURCE_ONLY_NO_LIVE_FRESHNESS_ASSERTION",
    }


def project_current(
    query: str,
    library_root: str | Path = DEFAULT_LIBRARY_ROOT,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    started = time.perf_counter()
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    if limit < 1 or limit > MAX_RESULTS:
        raise ValueError(f"limit must be 1..{MAX_RESULTS}")
    root = Path(library_root).resolve()
    cache_path = root / CACHE_RELATIVE
    showroom_path = root / SHOWROOM_RELATIVE
    cache = _load_object(cache_path)
    showroom = _load_object(showroom_path)
    raw_entries = cache.get("entries") if isinstance(cache.get("entries"), dict) else {}
    showroom_by_asset = _showroom_index(showroom)
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for cache_entry in raw_entries.values():
        if not isinstance(cache_entry, dict):
            continue
        record = cache_entry.get("record") if isinstance(cache_entry.get("record"), dict) else None
        if record is not None and _matches(record, query):
            matches.append((cache_entry, record))
    matches.sort(key=lambda item: (str(item[1].get("display_name") or "").casefold(), str(item[1].get("asset_id") or "")))
    truncated = len(matches) > limit
    entries: list[dict[str, Any]] = []
    for cache_entry, record in matches[:limit]:
        asset_id = str(record.get("asset_id") or "")
        freshness = _signature_freshness(cache_entry, record)
        actions = record.get("actions") if isinstance(record.get("actions"), dict) else {}
        entries.append(
            {
                "asset_id": asset_id or None,
                "display_name": record.get("display_name"),
                "asset_dir": record.get("asset_dir"),
                "cache_freshness": freshness,
                "showroom": _showroom_projection(showroom_by_asset.get(asset_id, [])),
                "proof": _proof_projection(record, freshness),
                "reopen": {
                    "inspect_command": actions.get("inspect"),
                    "asset_dir": record.get("asset_dir"),
                },
            }
        )
    result = {
        "schema": SCHEMA,
        "authority": "READ_ONLY_MATERIALIZED_TINY3D_ORIENTATION",
        "query": query,
        "workspace": str(root),
        "count": len(matches),
        "returned": len(entries),
        "truncated": truncated,
        "sources": {
            "library_cache": _source_fact(
                cache_path,
                cache,
                freshness="MATCHED_RECORD_PROOF_IS_CURRENT_ONLY_WHEN_STORED_FILE_SIGNATURE_MATCHES",
            ),
            "showroom_catalogue": _source_fact(
                showroom_path,
                showroom,
                freshness="MATERIALIZED_SOURCE_ONLY_NO_LIVE_FRESHNESS_ASSERTION",
            ),
        },
        "entries": entries,
        "boundary": "Read-only bounded projection. No recursive scan, Tiny3D command, cache write, fetch, archive expansion, media regeneration, or proof re-encoding.",
    }
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(description="Bounded read-only Tiny3D current-state projection for Stack Atlas")
    parser.add_argument("query")
    parser.add_argument("--library-root", type=Path, default=DEFAULT_LIBRARY_ROOT)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    try:
        result = project_current(args.query, args.library_root, limit=args.limit)
    except ValueError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "UNKNOWN", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
