#!/usr/bin/env python3
"""Provenance index validator for regression-research.

Validates provenance.json per issue #5 acceptance criteria:
- every report in 01 Reports is indexed
- every indexed path exists
- duplicate/superseded artifacts are marked
- detects broken paths and duplicate incident ids
- guards against credential-bearing material

Usage:
  python tools/provenance.py validate
  python tools/provenance.py validate --index provenance.json
  python tools/provenance.py check --index provenance.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_INDEX = Path(__file__).resolve().parents[1] / "provenance.json"
REPORTS_DIR = Path(__file__).resolve().parents[1] / "01 Reports"
DUPLICATE_DIR = Path(__file__).resolve().parents[1] / "99 Duplicate Archive"

# Deny credential-bearing patterns (path substrings, case-insensitive)
DENY_SUBSTRINGS = [
    ".env",
    "tailscale",
    "_share_check.html",
    "share-check",
    "credentials",
    "secret",
]

def _load_index(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"_error": f"index not found: {path}"}
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid JSON in {path}: {exc}"}
    except OSError as exc:
        return {"_error": f"cannot read {path}: {exc}"}
    return data


def validate(index_path: Path = DEFAULT_INDEX) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    repo_root = index_path.resolve().parent if index_path.name == "provenance.json" and index_path.parent.name != "tools" else Path(__file__).resolve().parents[1]
    # repo_root is parent of provenance.json which is repo root
    if index_path.name == "provenance.json":
        repo_root = index_path.resolve().parent
    else:
        repo_root = Path(__file__).resolve().parents[1]

    data = _load_index(index_path)
    if "_error" in data:
        return False, [data["_error"]], {"errors": 1}

    # Schema checks
    if "entries" not in data or not isinstance(data["entries"], list):
        errors.append("missing or invalid 'entries' array")
        return False, errors, {"errors": len(errors)}

    entries = data["entries"]
    if not isinstance(data.get("orphan_evidence", []), list):
        errors.append("'orphan_evidence' must be a list if present")

    # Collect indexed report paths
    indexed_reports: set[str] = set()
    incident_ids: dict[str, str] = {}
    all_indexed_paths: list[tuple[str, str]] = []  # (kind, path)

    for idx, entry in enumerate(entries):
        prefix = f"entries[{idx}]"
        report_path = entry.get("report_path")
        if not isinstance(report_path, str) or not report_path.strip():
            errors.append(f"{prefix}: report_path must be non-empty string")
            continue
        # Normalize slashes
        norm = report_path.replace("\\", "/")
        if norm in indexed_reports:
            errors.append(f"{prefix}: duplicate report_path '{norm}'")
        indexed_reports.add(norm)
        all_indexed_paths.append(("report", norm))

        # incident_id uniqueness (only for non-null)
        incident_id = entry.get("incident_id")
        if incident_id is not None:
            if not isinstance(incident_id, str) or not incident_id.strip():
                errors.append(f"{prefix}: incident_id must be string or null, got empty string")
            else:
                if incident_id in incident_ids:
                    errors.append(
                        f"{prefix}: duplicate incident_id '{incident_id}' also used by {incident_ids[incident_id]}"
                    )
                else:
                    incident_ids[incident_id] = f"{prefix} ({norm})"

        # duplicate_status
        status = entry.get("duplicate_status")
        if status not in ("canonical", "superseded", "duplicate"):
            errors.append(f"{prefix}: duplicate_status must be canonical|superseded|duplicate, got '{status}'")

        # required fields
        for field in ("title", "date", "evidence_type"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{prefix}: {field} must be non-empty string")

        # arrays
        for arr_field in ("raw_transcripts", "evidence_files", "contract_snapshots", "missing"):
            val = entry.get(arr_field)
            if not isinstance(val, list):
                errors.append(f"{prefix}: {arr_field} must be array")
            else:
                for p in val:
                    if not isinstance(p, str) or not p.strip():
                        errors.append(f"{prefix}: {arr_field} contains empty string")
        # Collect paths for existence check
        for kind in ("raw_transcripts", "evidence_files", "contract_snapshots"):
            for p in entry.get(kind, []):
                if isinstance(p, str) and p.strip():
                    all_indexed_paths.append((kind, p.replace("\\", "/")))

    # Orphan evidence paths also must exist
    for idx, orphan in enumerate(data.get("orphan_evidence", [])):
        p = orphan.get("path")
        if isinstance(p, str) and p.strip():
            all_indexed_paths.append((f"orphan_evidence[{idx}]", p.replace("\\", "/")))
        else:
            errors.append(f"orphan_evidence[{idx}]: path must be non-empty string")

    # duplicate_archive entries if any
    dup_archive = data.get("duplicate_archive", {})
    for idx, dup in enumerate(dup_archive.get("entries", []) if isinstance(dup_archive, dict) else []):
        p = dup.get("path") if isinstance(dup, dict) else None
        if isinstance(p, str) and p.strip():
            all_indexed_paths.append((f"duplicate_archive[{idx}]", p.replace("\\", "/")))

    # Check every indexed path exists
    for kind, rel in all_indexed_paths:
        # skip empty
        abs_path = repo_root / rel
        if not abs_path.exists():
            errors.append(f"broken path ({kind}): '{rel}' does not exist")
        # credential guard
        low = rel.lower()
        for deny in DENY_SUBSTRINGS:
            if deny.lower() in low:
                errors.append(f"credential-bearing path denied ({kind}): '{rel}' contains '{deny}'")

    # Check every report in 01 Reports is indexed
    if REPORTS_DIR.exists():
        actual_reports: set[str] = set()
        for p in REPORTS_DIR.iterdir():
            if p.is_file() and p.suffix.lower() in (".md", ".txt"):
                actual_reports.add(f"01 Reports/{p.name}")
        # indexed_reports already normalized
        for actual in sorted(actual_reports):
            if actual not in indexed_reports:
                errors.append(f"unindexed report: '{actual}'")
        for indexed in sorted(indexed_reports):
            # also verify that any indexed report not in actual is already reported as broken, but give clearer message
            if indexed not in actual_reports:
                # already flagged as broken path, but also note
                pass
    else:
        errors.append(f"reports directory not found: {REPORTS_DIR}")

    # Check duplicate archive marking: if files exist under 99 Duplicate Archive, they must be represented
    if DUPLICATE_DIR.exists():
        dup_files = [p for p in DUPLICATE_DIR.iterdir() if p.is_file()]
        if dup_files:
            # If there are files, ensure duplicate_archive.entries covers them and entries with duplicate_status
            indexed_dup_paths = set()
            for entry in entries:
                if entry.get("duplicate_status") in ("superseded", "duplicate"):
                    indexed_dup_paths.add(entry.get("report_path", "").replace("\\", "/"))
                for kind in ("raw_transcripts", "evidence_files", "contract_snapshots"):
                    for p in entry.get(kind, []):
                        if "99 Duplicate Archive" in p:
                            indexed_dup_paths.add(p.replace("\\", "/"))
            for dup_key in dup_archive.get("entries", []) if isinstance(dup_archive, dict) else []:
                if isinstance(dup_key, dict) and isinstance(dup_key.get("path"), str):
                    indexed_dup_paths.add(dup_key["path"].replace("\\", "/"))
            for f in dup_files:
                rel = f"99 Duplicate Archive/{f.name}"
                if rel not in indexed_dup_paths:
                    # Check orphan or duplicate_archive entries already counted
                    found = False
                    for p in data.get("orphan_evidence", []):
                        if p.get("path", "").replace("\\", "/") == rel:
                            found = True
                            break
                    if not found and dup_archive.get("entries"):
                        for e in dup_archive.get("entries", []):
                            if isinstance(e, dict) and e.get("path", "").replace("\\", "/") == rel:
                                found = True
                                break
                    if not found:
                        errors.append(f"duplicate archive file not indexed/marked: '{rel}'")
                # Also check that any file in duplicate archive is not marked canonical elsewhere
                for entry in entries:
                    if entry.get("report_path", "").replace("\\", "/") == rel and entry.get("duplicate_status") == "canonical":
                        errors.append(f"duplicate archive file marked canonical: '{rel}'")

    # Validation rules field presence
    if "validation_rules" not in data:
        warnings.append("validation_rules section missing (informational)")

    stats = {
        "reports_indexed": len(indexed_reports),
        "incident_ids_unique": len(incident_ids),
        "paths_checked": len(all_indexed_paths),
        "errors": len(errors),
        "warnings": len(warnings),
    }
    all_messages = errors + [f"WARN: {w}" for w in warnings]
    ok = len(errors) == 0
    return ok, all_messages, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate provenance index")
    parser.add_argument("command", nargs="?", default="validate", choices=["validate", "check"])
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX, help="path to provenance.json")
    args = parser.parse_args()

    ok, messages, stats = validate(args.index)
    if ok:
        print(json.dumps({"status": "PROVEN", **stats}, ensure_ascii=False))
        if messages:
            for m in messages:
                print(m)
        return 0
    else:
        print(json.dumps({"status": "REJECTED", **stats, "messages": messages}, ensure_ascii=False, indent=2))
        for m in messages:
            print(f"ERROR: {m}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
