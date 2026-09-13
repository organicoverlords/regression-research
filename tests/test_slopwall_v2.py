from __future__ import annotations

from pathlib import Path

import pytest

from tools.slopwall_v2 import SlopwallV2Error, validate_slopwall_fixture

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPORT = "01 Reports/2026-08-26_2236_EEST_correction-regurgitation_incident_report.md"


def fixture() -> dict:
    return {
        "id": "slopwall-v2-example",
        "title": "Slopwall V2 example",
        "source_report": SOURCE_REPORT,
        "incident_class": "correction_binding",
        "inherited_objective": "Continue the inherited task with the corrected result.",
        "live_state": ["The inherited task is still active."],
        "user_correction": "slopwall",
        "protected_state": ["The inherited objective"],
        "hard_exclusions": ["Do not replace the repair with incident ceremony."],
        "failure_candidate": {"action": "Explain the failure and stop."},
        "success_candidate": {"action": "Apply the correction and continue the original task."},
        "discriminating_evidence": ["Whether the next substantive action advances the original task."],
        "completion_condition": "The original task advances with the correction applied.",
        "scoring": {
            "correction_applied_before_next_action": "required",
            "next_substantive_action_advances_objective": "required",
            "original_objective_preserved": "required",
        },
        "slopwall_event": {
            "event_id": "SW-V2-TEST-001",
            "occurrence_role": "CORRECTIVE_INTERVENTION",
            "matched_form": "slopwall",
            "source_message": "slopwall",
            "provenance": [{"ref": "conversation:test-turn"}],
            "parent_event_id": None,
            "memory_ref": "mem-test-slopwall-v2",
            "evidence_confidence": "B",
            "scores": {
                "information_slop": 3,
                "task_displacement": 4,
                "execution_damage": 1,
                "correction_resistance": 0,
                "control_state_pathology": 1,
            },
            "severity_100": 36,
            "analysis": {
                "failure_boundary": "The prior answer displaced the inherited objective.",
                "user_needed": "The corrected task result.",
                "assistant_did": "Explained the failure and stopped.",
                "governing_guidance": [{"source": "RULES.md", "status": "LOADED"}],
                "failure_class": "RULE_VIOLATION",
                "correct_counterfactual": "Apply the existing rule and advance the inherited task.",
                "repaired_result": "The inherited task advances with corrected substance.",
                "rule_change_recommended": False,
            },
            "closure_state": "CLOSED",
        },
    }


def test_complete_fixture_validates() -> None:
    validate_slopwall_fixture(fixture(), root=ROOT, filename="example.json")


def test_literal_signal_is_required() -> None:
    raw = fixture()
    raw["slopwall_event"]["source_message"] = "please improve that"
    with pytest.raises(SlopwallV2Error, match="occur literally"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_d_confidence_is_unscorable() -> None:
    raw = fixture()
    raw["slopwall_event"]["evidence_confidence"] = "D"
    raw["slopwall_event"]["scores"] = None
    raw["slopwall_event"]["severity_100"] = None
    validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_repeated_slopwall_can_link_parent() -> None:
    raw = fixture()
    raw["slopwall_event"]["event_id"] = "SW-V2-TEST-002"
    raw["slopwall_event"]["parent_event_id"] = "SW-V2-TEST-001"
    validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_closed_event_requires_memory_pointer() -> None:
    raw = fixture()
    raw["slopwall_event"]["memory_ref"] = ""
    with pytest.raises(SlopwallV2Error, match="memory_ref"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_rule_change_cannot_be_inferred_from_plain_failure() -> None:
    raw = fixture()
    raw["slopwall_event"]["analysis"]["rule_change_recommended"] = True
    with pytest.raises(SlopwallV2Error, match="RULE_GAP or RULE_CONFLICT"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_proven_rule_gap_can_recommend_change_with_evidence() -> None:
    raw = fixture()
    analysis = raw["slopwall_event"]["analysis"]
    analysis["failure_class"] = "RULE_GAP"
    analysis["rule_change_recommended"] = True
    analysis["rule_change_evidence"] = "The loaded canonical rule omitted the decision boundary that failed."
    validate_slopwall_fixture(raw, root=ROOT, filename="example.json")
