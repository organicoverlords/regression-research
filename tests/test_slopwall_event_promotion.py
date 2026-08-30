from __future__ import annotations

import json
from pathlib import Path

from tools.slopwall_event_promotion import PROMOTIONS, promote
from tools.slopwall_raw_review import META_REASONS
from tools.slopwall_events import validate_index

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "02 Evidence" / "2026-08-27_slopwall_raw_discovery.json"
INDEX = ROOT / "02 Evidence" / "2026-08-26_slopwall_event_index.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_reviewed_promotion_batches_are_present_and_scored() -> None:
    data = _load(INDEX)
    validate_index(data)
    by_mid = {event.get("raw_message_id"): event for event in data["events"]}
    assert len(PROMOTIONS) == 28
    for mid, spec in PROMOTIONS.items():
        event = by_mid[mid]
        assert event["event_id"] == spec["event_id"]
        assert event["evidence_confidence"] == "B"
        assert event["severity_100"] == sum(spec["scores"].values()) * 4


def test_promotion_is_idempotent_on_promoted_index() -> None:
    raw = _load(RAW)
    current = _load(INDEX)
    again = promote(raw, current)
    validate_index(again)
    assert again == current


def test_raw_meta_references_are_exact_and_idempotent() -> None:
    raw = _load(RAW)
    current = _load(INDEX)
    by_mid = {record["message_id"]: record for record in raw["records"]}
    meta_occurrences = [
        occurrence
        for occurrence in current["occurrences"]
        if occurrence["occurrence_role"] == "META_REFERENCE"
        and occurrence["occurrence_id"].startswith("OCC-RAW-META-")
    ]
    assert len(META_REASONS) == 8
    assert len(meta_occurrences) == 8
    for mid in META_REASONS:
        record = by_mid[mid]
        matches = [
            occurrence
            for occurrence in meta_occurrences
            if any(f"#message={mid}" in item["ref"] for item in occurrence["provenance"])
        ]
        assert len(matches) == sum(record["matched_forms"].values()) == 1
        assert matches[0]["raw_user_text"] == record["raw_user_text"]
        assert matches[0]["matched_form"] == "slopwall"
    assert all(occurrence["matched_form"] != "slop wall" for occurrence in current["occurrences"])
