#!/usr/bin/env python3
"""Validate the frozen #174 coded samples and report auditable denominators."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "03 Fixtures and Experiments/2026-08-27_issue174_pilot-coded.csv"
TRANCHE2 = ROOT / "03 Fixtures and Experiments/2026-08-27_issue174_sample2-coded.csv"
STATUSES = {"MISTAKE", "CONTROL", "NO_CLEAR_MISTAKE"}
STRATA = {"GEN", "UE"}
PILOT_FIELDS = {
    "sample_id", "stratum", "conversation_id", "user_index", "tool_calls", "coding_status",
    "failure_class", "severity_1_3", "preventability_0_3", "rationale", "counterfactual", "source_snapshot_file",
}
TRANCHE2_FIELDS = {
    "sample2_id", "seed", "stratum", "conversation_id", "user_index", "tool_calls", "coding_status",
    "failure_class", "severity_1_3", "preventability_0_3", "rationale", "counterfactual", "local_sample_file",
}


def _int_field(row: dict[str, str], field: str, *, low: int, high: int) -> int:
    raw = row.get(field, "")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if not low <= value <= high:
        raise ValueError(f"{field} must be between {low} and {high}")
    return value


def _has_text(row: dict[str, str], field: str) -> bool:
    return bool((row.get(field) or "").strip())


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"{path.name} must contain coded episodes")
    return rows


def validate_rows(rows: list[dict[str, str]], *, tranche: str) -> None:
    if len(rows) != 24:
        raise ValueError(f"{tranche} must contain exactly 24 episodes")
    expected_fields = PILOT_FIELDS if tranche == "pilot" else TRANCHE2_FIELDS
    id_field = "sample_id" if tranche == "pilot" else "sample2_id"
    provenance_field = "source_snapshot_file" if tranche == "pilot" else "local_sample_file"
    for row in rows:
        if set(row) != expected_fields:
            missing = sorted(expected_fields - set(row))
            extra = sorted(set(row) - expected_fields, key=str)
            raise ValueError(f"{tranche} coded schema drift: missing={missing} extra={extra}")
    sample_ids = [row.get(id_field) for row in rows]
    if any(not (sample_id or "").strip() for sample_id in sample_ids):
        raise ValueError(f"{tranche} {id_field} is required")
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError(f"{tranche} {id_field} values must be unique")
    expected_ids = {str(value) for value in range(1, 25)}
    if set(sample_ids) != expected_ids:
        raise ValueError(f"{tranche} {id_field} values must remain frozen at 1..24")
    strata = Counter(row.get("stratum") for row in rows)
    if strata != Counter({"GEN": 12, "UE": 12}):
        raise ValueError(f"{tranche} must contain exactly 12 GEN and 12 UE episodes")
    for row in rows:
        if row.get("stratum") not in STRATA:
            raise ValueError("stratum must be GEN or UE")
        if row.get("coding_status") not in STATUSES:
            raise ValueError("coding_status is invalid")
        _int_field(row, "user_index", low=1, high=10**9)
        _int_field(row, "tool_calls", low=1, high=10**9)
        if not _has_text(row, "conversation_id"):
            raise ValueError("conversation_id is required")
        if not _has_text(row, "rationale"):
            raise ValueError("rationale is required")
        if not _has_text(row, provenance_field):
            raise ValueError(f"{tranche} {provenance_field} is required")
        status = row["coding_status"]
        if status == "MISTAKE":
            if not _has_text(row, "failure_class") or not _has_text(row, "counterfactual"):
                raise ValueError("MISTAKE rows require failure_class and counterfactual")
            _int_field(row, "severity_1_3", low=1, high=3)
            _int_field(row, "preventability_0_3", low=0, high=3)
        else:
            for field in ("failure_class", "severity_1_3", "preventability_0_3", "counterfactual"):
                if row.get(field):
                    raise ValueError(f"{status} rows must leave {field} empty")
        if status == "CONTROL" and not row["rationale"].startswith("CONTROL:"):
            raise ValueError("CONTROL rationale must start with CONTROL:")
    if tranche == "tranche2":
        seeds = {row.get("seed") for row in rows}
        if seeds != {"1742"}:
            raise ValueError("tranche2 seed must remain frozen at 1742")


def validate_samples(pilot: list[dict[str, str]], tranche2: list[dict[str, str]]) -> None:
    validate_rows(pilot, tranche="pilot")
    validate_rows(tranche2, tranche="tranche2")
    keys = [((row["conversation_id"] or "").strip(), row["user_index"]) for row in pilot + tranche2]
    if len(keys) != len(set(keys)):
        raise ValueError("coded samples must not duplicate episode keys across tranches")


def summarize(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for stratum in ("ALL", "GEN", "UE"):
        selected = rows if stratum == "ALL" else [row for row in rows if row["stratum"] == stratum]
        counts = Counter(row["coding_status"] for row in selected)
        result[stratum] = {
            "episodes": len(selected), "mistakes": counts["MISTAKE"], "controls": counts["CONTROL"],
            "no_clear_mistake": counts["NO_CLEAR_MISTAKE"],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=PILOT)
    parser.add_argument("--tranche2", type=Path, default=TRANCHE2)
    args = parser.parse_args()
    pilot = load_rows(args.pilot)
    tranche2 = load_rows(args.tranche2)
    validate_samples(pilot, tranche2)
    for label, rows in (("pilot", pilot), ("tranche2", tranche2), ("combined", pilot + tranche2)):
        print(f"{label}: {summarize(rows)}")
    print("ISSUE174_CODED_SAMPLE_GUARD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
