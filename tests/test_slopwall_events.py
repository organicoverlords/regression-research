from __future__ import annotations

import copy

import pytest

from tools.slopwall_events import DEFAULT_INDEX, load_index, summary, validate_index


def test_index_validates_and_counts_both_event_states() -> None:
    data = load_index(DEFAULT_INDEX)
    validate_index(data)
    counts = summary(data)
    assert counts["canonical_interventions"] == 2
    assert counts["scored"] == 1
    assert counts["unscorable"] == 1
    assert counts["forms"] == {"slopwall": 2}
    assert counts["excluded_meta_mentions"] == 2


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
    event = data["events"][1]
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


def test_both_literal_spellings_are_valid() -> None:
    data = copy.deepcopy(load_index(DEFAULT_INDEX))
    data["events"][0]["exact_spelling"] = "slop wall"
    validate_index(data)
