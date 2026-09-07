import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "02 Evidence" / "2026-08-26_slopwall_event_index.json"
RESOLUTION = ROOT / "02 Evidence" / "2026-09-07_issue89_unresolved_event_resolution.json"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_issue89_resolves_all_preexisting_unscorable_canonical_events():
    data = _load(INDEX)
    assert data["schema_version"] == "1.2.0"
    assert data["confirmed_counts"] == {
        "lexical_occurrences": 48,
        "canonical_interventions": 39,
        "slopwall": 48,
        "slop wall": 0,
        "scored": 39,
        "unscorable": 0,
        "occurrence_roles": {"CORRECTIVE_INTERVENTION": 39, "META_REFERENCE": 9},
    }
    assert all(event.get("scores") is not None for event in data["events"])
    assert all(event["severity_100"] == 4 * sum(event["scores"].values()) for event in data["events"])


def test_issue89_009_is_bound_to_preserved_raw_conversation_and_scored():
    data = _load(INDEX)
    event = next(event for event in data["events"] if event["event_id"] == "SW-20260826-009")
    assert event["evidence_confidence"] == "B"
    assert event["raw_message_id"] == "f2c759e3-cb6d-46d9-bed3-f4fbf349c835"
    assert event["execution_restored_next_substantive_turn"] is True
    assert event["severity_100"] == 24
    assert any("d31ad0a34d8911c3" in item["ref"] for item in event["provenance"])


def test_issue89_011_is_rejected_not_scored_or_counted():
    data = _load(INDEX)
    assert "SW-20260826-011" not in {event["event_id"] for event in data["events"]}
    assert "SW-20260826-011" not in {occ.get("canonical_event_id") for occ in data["occurrences"]}
    rejected = next(item for item in data["rejected_candidates"] if item["candidate_id"] == "SW-20260826-011")
    assert rejected["disposition"] == "REJECTED_NO_SOURCE_MATCH"
    resolution = _load(RESOLUTION)["findings"]["SW-20260826-011"]
    assert resolution["preserved_corpus_checks"]["user_slopwall_messages_20_22_40_to_20_23_00Z"] == 0
    assert resolution["preserved_corpus_checks"]["source_messages_matching_claimed_concretely_established_phrase"] == 0
