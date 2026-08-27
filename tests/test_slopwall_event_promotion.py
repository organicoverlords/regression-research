from __future__ import annotations

import json
from pathlib import Path

from tools.slopwall_event_promotion import PROMOTIONS, promote
from tools.slopwall_events import validate_index

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "02 Evidence" / "2026-08-27_slopwall_raw_discovery.json"
INDEX = ROOT / "02 Evidence" / "2026-08-26_slopwall_event_index.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_first_promotion_batch_is_present_and_scored() -> None:
    data = _load(INDEX)
    validate_index(data)
    by_mid = {event.get("raw_message_id"): event for event in data["events"]}
    assert len(PROMOTIONS) == 14
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
