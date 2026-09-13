from __future__ import annotations

import json

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
        "incident_event": {
            "event_id": "SW-V2-TEST-001",
            "occurrence_role": "CORRECTIVE_INTERVENTION",
            "trigger_kind": "SLOPWALL",
            "trigger_intent": "EXECUTE_CORRECTION_LOOP",
            "matched_form": "slopwall",
            "source_message": "slopwall",
            "capture": {
                "scope": "VISIBLE_CONTEXT_ONLY",
                "verbatim": True,
                "full_conversation_reload": False,
                "retrieval_for_capture_only": False,
                "evidence_ref": "tests/fixtures/slopwall-v2-visible-context-test.json",
            },
            "provenance": [{"ref": "conversation:test-turn"}],
            "parent_event_id": None,
            "memory_ref": None,
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
                "first_supported_divergence": "The assistant stopped at explanation instead of advancing the inherited objective.",
                "governing_guidance": [{"source": "RULES.md", "status": "LOADED"}],
                "failure_class": "RULE_VIOLATION",
                "correct_counterfactual": "Apply the existing rule and advance the inherited task.",
                "repaired_result": "The inherited task advances with corrected substance.",
                "rule_change_recommended": False,
                "behavior_contract_review": {
                    "search_performed": True,
                    "checked_assertions": ["original_objective_preserved"],
                    "disposition": "REUSE_EXISTING",
                    "reason": "The existing objective-preservation assertion covers this bounded failure.",
                    "reused_assertions": ["original_objective_preserved"],
                },
            },
            "closure_state": "OPEN",
        },
    }


def test_complete_fixture_validates() -> None:
    validate_slopwall_fixture(fixture(), root=ROOT, filename="example.json")


def test_literal_signal_is_required() -> None:
    raw = fixture()
    raw["incident_event"]["source_message"] = "please improve that"
    with pytest.raises(SlopwallV2Error, match="occur literally"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_d_confidence_is_unscorable() -> None:
    raw = fixture()
    raw["incident_event"]["evidence_confidence"] = "D"
    raw["incident_event"]["scores"] = None
    raw["incident_event"]["severity_100"] = None
    validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_repeated_slopwall_can_link_parent() -> None:
    raw = fixture()
    raw["incident_event"]["event_id"] = "SW-V2-TEST-002"
    raw["incident_event"]["parent_event_id"] = "SW-V2-TEST-001"
    validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def closed_fixture(tmp_path: Path) -> dict:
    raw = fixture()
    event = raw["incident_event"]
    event_id = "SW-V2-TEST-CLOSED"
    event["event_id"] = event_id
    event["closure_state"] = "CLOSED"
    raw["source_report"] = "01 Reports/test-incident.md"
    event["replay_ref"] = "03 Fixtures and Experiments/test-replay.json"
    event["capture"]["evidence_ref"] = "02 Evidence/test-visible.json"
    event["memory_ref"] = "memory/memory-bank.jsonl#mem-test-slopwall-v2"

    report = tmp_path / raw["source_report"]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(f"event_id: {event_id}\n", encoding="utf-8")

    evidence = tmp_path / event["capture"]["evidence_ref"]
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(json.dumps({
        "capture_scope": "VISIBLE_CONTEXT_ONLY",
        "verbatim": True,
        "full_conversation_reload": False,
        "items": [{"kind": "user_message", "content": event["source_message"]}],
    }), encoding="utf-8")

    replay = tmp_path / event["replay_ref"]
    replay.parent.mkdir(parents=True, exist_ok=True)
    replay.write_text(json.dumps(raw), encoding="utf-8")

    bank = tmp_path / "memory/memory-bank.jsonl"
    bank.parent.mkdir(parents=True, exist_ok=True)
    bank.write_text(json.dumps({
        "id": "mem-test-slopwall-v2",
        "kind": "correction",
        "state": "PROVEN",
        "tags": ["slopwall"],
        "text": f"Event {event_id} regression lesson.",
        "evidence": [raw["source_report"], event["replay_ref"], event["capture"]["evidence_ref"]],
        "source_messages": [event["source_message"]],
    }) + "\n", encoding="utf-8")
    return raw


def test_closed_event_accepts_only_bound_canonical_memory(tmp_path: Path) -> None:
    raw = closed_fixture(tmp_path)
    validate_slopwall_fixture(raw, root=tmp_path, filename="test-replay.json")


def test_closed_event_rejects_missing_or_pending_memory_pointer(tmp_path: Path) -> None:
    raw = closed_fixture(tmp_path)
    raw["incident_event"]["memory_ref"] = None
    with pytest.raises(SlopwallV2Error, match="requires memory_ref"):
        validate_slopwall_fixture(raw, root=tmp_path, filename="test-replay.json")

    raw = closed_fixture(tmp_path)
    pending = tmp_path / "memory/reports/pending.md"
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text("pending", encoding="utf-8")
    raw["incident_event"]["memory_ref"] = "memory/reports/pending.md"
    with pytest.raises(SlopwallV2Error, match="canonical memory/memory-bank.jsonl#mem"):
        validate_slopwall_fixture(raw, root=tmp_path, filename="test-replay.json")


def test_concrete_v2_event_remains_pending_until_canonical_memory() -> None:
    path = ROOT / "03 Fixtures and Experiments/2026-09-13_slopwall-v2_wrong-slopwall-semantics_replay.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["incident_event"]["closure_state"] == "REPAIRED_PENDING_DURABILITY"
    validate_slopwall_fixture(raw, root=ROOT, filename=path.name)


def test_rule_change_cannot_be_inferred_from_plain_failure() -> None:
    raw = fixture()
    raw["incident_event"]["analysis"]["rule_change_recommended"] = True
    with pytest.raises(SlopwallV2Error, match="RULE_GAP or RULE_CONFLICT"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_proven_rule_gap_can_recommend_change_with_evidence() -> None:
    raw = fixture()
    analysis = raw["incident_event"]["analysis"]
    analysis["failure_class"] = "RULE_GAP"
    analysis["rule_change_recommended"] = True
    analysis["rule_change_evidence"] = "The loaded canonical rule omitted the decision boundary that failed."
    validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_behavior_contract_search_is_required() -> None:
    raw = fixture()
    raw["incident_event"]["analysis"]["behavior_contract_review"]["search_performed"] = False
    with pytest.raises(SlopwallV2Error, match="search must be performed"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_proposed_behavior_contract_must_be_bound_to_fixture_scoring() -> None:
    raw = fixture()
    review = raw["incident_event"]["analysis"]["behavior_contract_review"]
    review["disposition"] = "PROPOSE_NEW"
    review.pop("reused_assertions")
    review["proposed_assertions"] = ["shared_rule_change_requires_proven_gap_or_conflict"]
    with pytest.raises(SlopwallV2Error, match="bound into fixture scoring"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_behavior_contract_can_guard_violation_without_shared_rule_change() -> None:
    raw = fixture()
    raw["scoring"]["shared_rule_change_requires_proven_gap_or_conflict"] = "required"
    analysis = raw["incident_event"]["analysis"]
    assert analysis["failure_class"] == "RULE_VIOLATION"
    assert analysis["rule_change_recommended"] is False
    review = analysis["behavior_contract_review"]
    review["disposition"] = "PROPOSE_NEW"
    review.pop("reused_assertions")
    review["proposed_assertions"] = ["shared_rule_change_requires_proven_gap_or_conflict"]
    review["reason"] = "A deterministic regression guard is useful even though the prose rule itself is already correct."
    validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_incident_report_is_an_explicit_full_loop_trigger() -> None:
    raw = fixture()
    event = raw["incident_event"]
    event["event_id"] = "INC-V2-TEST-001"
    event["trigger_kind"] = "INCIDENT_REPORT"
    event["matched_form"] = "incident report"
    event["source_message"] = "incident report"
    validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_meta_reference_cannot_claim_trigger_without_corrective_intent() -> None:
    raw = fixture()
    event = raw["incident_event"]
    event["event_id"] = "INC-V2-TEST-002"
    event["trigger_kind"] = "INCIDENT_REPORT"
    event["matched_form"] = "incident report"
    event["source_message"] = "mita incident report tarkoittaa?"
    event["trigger_intent"] = "META_REFERENCE"
    with pytest.raises(SlopwallV2Error, match="explicit corrective command"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_full_conversation_reload_is_forbidden() -> None:
    raw = fixture()
    raw["incident_event"]["capture"]["full_conversation_reload"] = True
    with pytest.raises(SlopwallV2Error, match="full conversation reload/backfill is forbidden"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_retrieval_solely_to_expand_capture_is_forbidden() -> None:
    raw = fixture()
    raw["incident_event"]["capture"]["retrieval_for_capture_only"] = True
    with pytest.raises(SlopwallV2Error, match="retrieval solely to expand incident capture is forbidden"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_visible_context_evidence_pointer_is_required() -> None:
    raw = fixture()
    raw["incident_event"]["capture"].pop("evidence_ref")
    with pytest.raises(SlopwallV2Error, match="capture.evidence_ref is required"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_source_message_must_match_verbatim_visible_evidence() -> None:
    raw = fixture()
    raw["incident_event"]["source_message"] = "slopwall but changed after capture"
    with pytest.raises(SlopwallV2Error, match="source_message must be preserved verbatim"):
        validate_slopwall_fixture(raw, root=ROOT, filename="example.json")


def test_legacy_coverage_audit_preserves_confirmed_lower_bound_without_backfill() -> None:
    audit = json.loads((ROOT / "02 Evidence/2026-09-13_slopwall-v2_legacy-coverage-audit.json").read_text(encoding="utf-8"))
    source = json.loads((ROOT / "02 Evidence/2026-08-26_slopwall_event_index.json").read_text(encoding="utf-8-sig"))
    assert audit["authority"] == "DERIVED_MIGRATION_AUDIT_NOT_NEW_EVENT_AUTHORITY"
    assert "No conversation reload" in audit["scope"]
    assert audit["summary"]["source_coverage_state"] == "NOT_PROVEN"
    assert audit["summary"]["canonical_events"] == len(source["events"]) == 39
    assert audit["summary"]["safe_legacy_manifest_events_without_chat_reload"] == 39
    assert audit["summary"]["all_events_have_provenance"] is True
    assert audit["summary"]["all_events_have_context_before"] is True
    assert audit["summary"]["all_events_have_context_after"] is True
    assert audit["summary"]["all_events_have_scores"] is True
    assert {item["event_id"] for item in audit["events"]} == {item["event_id"] for item in source["events"]}
    for item in audit["events"]:
        assert item["verbatim_user_corrections"]
        assert item["canonical_event_record"].startswith("02 Evidence/2026-08-26_slopwall_event_index.json#event_id=")
        assert "SYNTHESIZE" not in item["v2_migration_disposition"].replace("DO_NOT_SYNTHESIZE", "")
    assert "No date/topic similarity binding" in audit["binding_policy"]["forbidden"]
    assert "no retrospective report/replay/memory fabrication" in audit["binding_policy"]["forbidden"]
