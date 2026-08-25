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
from typing import Any

DEFAULT_INDEX = Path(__file__).resolve().parents[1] / "provenance.json"
REPORTS_DIR_NAME = "01 Reports"
DUPLICATE_DIR_NAME = "99 Duplicate Archive"

# Deny credential-bearing patterns (path substrings, case-insensitive)
DENY_SUBSTRINGS = [
    ".env",
    "tailscale",
    "_share_check.html",
    "share-check",
    "credentials",
    "secret",
]

def _load_index(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"_error": f"index not found: {path}"}
    except json.JSONDecodeError as exc:
        return {"_error": f"invalid JSON in {path}: {exc}"}
    except OSError as exc:
        return {"_error": f"cannot read {path}: {exc}"}
    if not isinstance(data, dict):
        return {"_error": f"provenance root must be an object: {path}"}
    return data


def _repo_root(index_path: Path) -> Path:
    """Resolve the checkout root from the index being validated.

    Keeping this derived from ``index_path`` makes temporary fixture validation
    faithful to the CLI and avoids checking a fixture against this module's
    checkout by accident.
    """

    resolved = index_path.resolve()
    return resolved.parent if resolved.name == "provenance.json" else DEFAULT_INDEX.parent


def _normalise_relative_path(value: Any) -> str | None:
    """Return a safe repository-relative path, or ``None`` when unsafe."""

    if not isinstance(value, str) or not value.strip():
        return None
    normalised = value.replace("\\", "/")
    candidate = Path(normalised)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return candidate.as_posix()


def _path_error(kind: str, value: Any, repo_root: Path) -> str | None:
    """Validate path shape and existence without ever resolving outside root."""

    normalised = _normalise_relative_path(value)
    if normalised is None:
        return f"unsafe or empty path ({kind}): {value!r}"
    resolved = (repo_root / normalised).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return f"unsafe path ({kind}): '{normalised}'"
    if not resolved.is_file():
        return f"broken path ({kind}): '{normalised}' does not exist"
    low = normalised.lower()
    for deny in DENY_SUBSTRINGS:
        if deny.lower() in low:
            return f"credential-bearing path denied ({kind}): '{normalised}' contains '{deny}'"
    return None


def validate(index_path: Path = DEFAULT_INDEX) -> tuple[bool, list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []
    index_path = Path(index_path)
    repo_root = _repo_root(index_path)
    reports_dir = repo_root / REPORTS_DIR_NAME
    duplicate_dir = repo_root / DUPLICATE_DIR_NAME

    data = _load_index(index_path)
    if "_error" in data:
        return False, [data["_error"]], {"errors": 1}

    # Schema checks
    if "entries" not in data or not isinstance(data["entries"], list):
        errors.append("missing or invalid 'entries' array")
        return False, errors, {"errors": len(errors)}

    entries = data["entries"]
    orphan_evidence = data.get("orphan_evidence", [])
    if not isinstance(orphan_evidence, list):
        errors.append("'orphan_evidence' must be a list if present")
        orphan_evidence = []

    duplicate_archive = data.get("duplicate_archive", {})
    if not isinstance(duplicate_archive, dict):
        errors.append("'duplicate_archive' must be an object if present")
        duplicate_archive = {}
    archive_entries_value = duplicate_archive.get("entries", [])
    if not isinstance(archive_entries_value, list):
        errors.append("'duplicate_archive.entries' must be a list if present")
        archive_entries_value = []
    archive_status = duplicate_archive.get("status")
    if archive_status is not None and (not isinstance(archive_status, str) or not archive_status.strip()):
        errors.append("'duplicate_archive.status' must be a non-empty string if present")
    archive_root = duplicate_archive.get("path")
    if archive_root is not None:
        normalised_archive_root = _normalise_relative_path(archive_root)
        if normalised_archive_root != DUPLICATE_DIR_NAME:
            errors.append(
                "'duplicate_archive.path' must be the safe repository-relative archive root "
                f"'{DUPLICATE_DIR_NAME}'"
            )

    # Collect indexed report paths
    indexed_reports: set[str] = set()
    incident_ids: dict[str, str] = {}
    all_indexed_paths: list[tuple[str, Any]] = []  # (kind, path)

    for idx, entry in enumerate(entries):
        prefix = f"entries[{idx}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: entry must be an object")
            continue
        report_path = entry.get("report_path")
        if not isinstance(report_path, str) or not report_path.strip():
            errors.append(f"{prefix}: report_path must be non-empty string")
        else:
            norm = _normalise_relative_path(report_path)
            if norm is None:
                errors.append(f"{prefix}: unsafe report_path '{report_path}'")
            else:
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
                incident_key = incident_id.strip()
                if incident_key in incident_ids:
                    errors.append(
                        f"{prefix}: duplicate incident_id '{incident_id}' also used by {incident_ids[incident_key]}"
                    )
                else:
                    incident_ids[incident_key] = f"{prefix} ({entry.get('report_path', '')})"

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
                    elif arr_field != "missing":
                        all_indexed_paths.append((arr_field, p))
        superseded_by = entry.get("superseded_by")
        if superseded_by is not None and (not isinstance(superseded_by, str) or not superseded_by.strip()):
            errors.append(f"{prefix}: superseded_by must be a non-empty string or null")

    # Orphan evidence paths also must exist
    for idx, orphan in enumerate(orphan_evidence):
        if not isinstance(orphan, dict):
            errors.append(f"orphan_evidence[{idx}]: entry must be an object")
            continue
        p = orphan.get("path")
        if isinstance(p, str) and p.strip():
            all_indexed_paths.append((f"orphan_evidence[{idx}]", p))
        else:
            errors.append(f"orphan_evidence[{idx}]: path must be non-empty string")

    # Duplicate archive entries must point inside the declared archive root.
    archive_paths: set[str] = set()
    for idx, duplicate in enumerate(archive_entries_value):
        prefix = f"duplicate_archive.entries[{idx}]"
        if not isinstance(duplicate, dict):
            errors.append(f"{prefix}: entry must be an object")
            continue
        path = duplicate.get("path")
        normalised = _normalise_relative_path(path)
        if normalised is None:
            errors.append(f"{prefix}: path must be a safe non-empty repository-relative path")
            continue
        if normalised == DUPLICATE_DIR_NAME or not normalised.startswith(DUPLICATE_DIR_NAME + "/"):
            errors.append(f"{prefix}: path must be under '{DUPLICATE_DIR_NAME}/'")
            continue
        if normalised in archive_paths:
            errors.append(f"{prefix}: duplicate archive path '{normalised}'")
        archive_paths.add(normalised)
        all_indexed_paths.append((prefix, normalised))

    # Check every indexed path exists
    for kind, rel in all_indexed_paths:
        error = _path_error(kind, rel, repo_root)
        if error:
            errors.append(error)

    # Check every report in 01 Reports is indexed
    if reports_dir.exists() and reports_dir.is_dir():
        actual_reports: set[str] = set()
        for p in reports_dir.iterdir():
            if p.is_file() and p.suffix.lower() in (".md", ".txt"):
                actual_reports.add(f"{REPORTS_DIR_NAME}/{p.name}")
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
        errors.append(f"reports directory not found: {reports_dir}")

    # Check duplicate archive marking: if files exist under 99 Duplicate Archive, they must be represented
    dup_files: list[Path] = []
    if duplicate_dir.exists() and duplicate_dir.is_dir():
        dup_files = [p for p in duplicate_dir.iterdir() if p.is_file()]
        if dup_files:
            # If there are files, ensure duplicate_archive.entries covers them and entries with duplicate_status
            indexed_dup_paths = set(archive_paths)
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                report = _normalise_relative_path(entry.get("report_path"))
                if entry.get("duplicate_status") in ("superseded", "duplicate"):
                    if report:
                        indexed_dup_paths.add(report)
                for kind in ("raw_transcripts", "evidence_files", "contract_snapshots"):
                    for p in entry.get(kind, []):
                        normalised = _normalise_relative_path(p)
                        if normalised and normalised.startswith(DUPLICATE_DIR_NAME + "/"):
                            indexed_dup_paths.add(normalised)
            for orphan in orphan_evidence:
                if isinstance(orphan, dict):
                    normalised = _normalise_relative_path(orphan.get("path"))
                    if normalised and normalised.startswith(DUPLICATE_DIR_NAME + "/"):
                        indexed_dup_paths.add(normalised)
            for f in dup_files:
                rel = f"{DUPLICATE_DIR_NAME}/{f.name}"
                if rel not in indexed_dup_paths:
                    errors.append(f"duplicate archive file not indexed/marked: '{rel}'")
                # Also check that any file in duplicate archive is not marked canonical elsewhere
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    if _normalise_relative_path(entry.get("report_path")) == rel and entry.get("duplicate_status") == "canonical":
                        errors.append(f"duplicate archive file marked canonical: '{rel}'")

    if archive_status == "empty_no_superseded_artifacts_currently_archived" and (archive_entries_value or dup_files):
        errors.append("duplicate archive status says empty but archive entries/files are present")
    if dup_files and archive_status == "empty_no_superseded_artifacts_currently_archived":
        errors.append("duplicate archive files are present while duplicate archive status says empty")

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
