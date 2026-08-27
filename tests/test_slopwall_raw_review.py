from __future__ import annotations

import json
from pathlib import Path

from tools.slopwall_raw_review import build_review, reconcile_existing_events
from tools.slopwall_events import validate_index

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "02 Evidence" / "2026-08-27_slopwall_raw_discovery.json"
INDEX = ROOT / "02 Evidence" / "2026-08-26_slopwall_event_index.json"
REVIEW = ROOT / "02 Evidence" / "2026-08-27_slopwall_raw_review.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_raw_review_classifies_every_deduped_hit_once() -> None:
    data = _load(REVIEW)
    assert data["summary"] == {
        "reviewed_hit_messages": 46,
        "role_counts": {"CORRECTIVE_INTERVENTION": 38, "META_REFERENCE": 8},
        "existing_event_bindings": 24,
        "new_canonical_event_candidates": 14,
        "meta_references": 8,
    }
    records = data["records"]
    assert len(records) == len({row["message_id"] for row in records}) == 46
    assert all(row["bounded_context_turns_before"] <= 4 for row in records)
    assert all(row["bounded_context_turns_after"] <= 4 for row in records)


def test_review_is_reproducible_from_raw_snapshot_and_index() -> None:
    assert build_review(_load(RAW), _load(INDEX)) == _load(REVIEW)


def test_existing_event_reconciliation_leaves_only_unbound_events_d_confidence() -> None:
    data = _load(INDEX)
    validate_index(data)
    confidence = {event["event_id"]: event["evidence_confidence"] for event in data["events"]}
    assert {event_id for event_id, grade in confidence.items() if grade == "D"} == {
        "SW-20260826-009",
        "SW-20260826-011",
    }
    scored = [event for event in data["events"] if event["severity_100"] is not None]
    assert len(scored) == 24
    assert all(event.get("raw_message_id") for event in scored)


def test_reconciliation_is_deterministic() -> None:
    raw = _load(RAW)
    current = _load(INDEX)
    # Reconcile from a copy that already contains the reviewed data; it must stay valid
    # and preserve the same scores/bindings rather than duplicating provenance refs.
    again = reconcile_existing_events(raw, current)
    validate_index(again)
    assert again == current
