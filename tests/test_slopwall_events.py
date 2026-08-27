from __future__ import annotations

import copy

import pytest

from tools.slopwall_events import DEFAULT_INDEX, load_index, summary, validate_index


def test_index_validates_and_separates_lexical_occurrences_from_events() -> None:
    data = load_index(DEFAULT_INDEX)
    validate_index(data)
    counts = summary(data)
    assert counts["lexical_occurrences"] == 44
    assert counts["canonical_interventions"] == 40
    assert counts["scored"] == 38
    assert counts["unscorable"] == 2
    assert counts["slopwall"] == 43
    assert counts["slop wall"] == 1
    assert counts["occurrence_roles"] == {
        "CORRECTIVE_INTERVENTION": 40,
        "META_REFERENCE": 4,
    }


def test_scored_event_composite_is_auditable() -> None:
    data = load_index(DEFAULT_INDEX)
    event = data["events"][0]
    assert event["severity_100"] == sum(event["scores"].values()) * 4 == 84
    assert event["evidence_confidence"] == "B"


def test_composite_mismatch_is_rejected() -> None:
    data = copy.deepcopy(load_index(DEFAULT_INDEX))
    data["events"][0]["severity_100"] = 80
    with pytest.raises(ValueError, match="severity_100"):
        validate_index(data)


def test_d_confidence_cannot_be_guessed() -> None:
    data = copy.deepcopy(load_index(DEFAULT_INDEX))
    event = next(item for item in data["events"] if item["evidence_confidence"] == "D")
    event["scores"] = {
        "information_slop": 1,
        "task_displacement": 1,
        "execution_damage": 1,
        "correction_resistance": 1,
        "control_state_pathology": 1,
    }
    event["severity_100"] = 20
    with pytest.raises(ValueError, match="D-confidence"):
        validate_index(data)


def test_both_literal_spellings_are_counted_as_occurrences() -> None:
    data = load_index(DEFAULT_INDEX)
    forms = [item["matched_form"] for item in data["occurrences"]]
    assert "slopwall" in forms
    assert "slop wall" in forms
    validate_index(data)


def test_meta_reference_does_not_require_canonical_event() -> None:
    data = copy.deepcopy(load_index(DEFAULT_INDEX))
    meta = next(item for item in data["occurrences"] if item["occurrence_role"] == "META_REFERENCE")
    assert meta["canonical_event_id"] is None
    validate_index(data)


def test_corrective_occurrence_must_link_to_event() -> None:
    data = copy.deepcopy(load_index(DEFAULT_INDEX))
    corrective = next(item for item in data["occurrences"] if item["occurrence_role"] == "CORRECTIVE_INTERVENTION")
    corrective["canonical_event_id"] = None
    with pytest.raises(ValueError, match="corrective occurrence must link"):
        validate_index(data)


def test_confirmed_counts_cannot_drift_from_records() -> None:
    data = copy.deepcopy(load_index(DEFAULT_INDEX))
    data["confirmed_counts"]["lexical_occurrences"] += 1
    with pytest.raises(ValueError, match="confirmed_counts"):
        validate_index(data)


def test_literal_form_must_exist_in_raw_user_text() -> None:
    data = copy.deepcopy(load_index(DEFAULT_INDEX))
    occurrence = data["occurrences"][0]
    occurrence["raw_user_text"] = "unrelated text"
    with pytest.raises(ValueError, match="not literal"):
        validate_index(data)
