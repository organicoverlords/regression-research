from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import tools.behavior_incident_capture as capture
from tools.behavior_incident_capture import BehaviorIncidentCaptureError, materialize_capture
from tools.provenance import validate as validate_provenance
from tools.slopwall_v2 import validate_slopwall_fixture


def capture_spec(event_id: str = "SW-V2-TEST-MAT-001") -> dict:
    return {
        "schema": "behavior-incident-capture.v2",
        "date": "2026-09-13",
        "event": {
            "event_id": event_id,
            "trigger_kind": "SLOPWALL",
            "trigger_intent": "EXECUTE_CORRECTION_LOOP",
            "matched_form": "slopwall",
            "source_message": "slopwall",
            "full_conversation_reload": False,
            "retrieval_for_capture_only": False,
            "provenance": [{"ref": "conversation:visible-test-boundary"}],
            "parent_event_id": None,
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
                "failure_boundary": "The prior reply explained the failure and stopped instead of advancing the inherited task.",
                "user_needed": "A corrected answer that advances the inherited objective.",
                "assistant_did": "Returned process explanation instead of the corrected result.",
                "first_supported_divergence": "The response selected explanation over the already-known next substantive action.",
                "governing_guidance": [{"source": "RULES.md", "status": "LOADED"}],
                "failure_class": "RULE_VIOLATION",
                "correct_counterfactual": "Apply the loaded correction rule and continue the inherited objective.",
                "repaired_result": "The inherited objective is resumed with the corrected substantive answer.",
                "rule_change_recommended": False,
                "behavior_contract_review": {
                    "search_performed": True,
                    "checked_assertions": ["original_objective_preserved"],
                    "disposition": "REUSE_EXISTING",
                    "reason": "The existing objective-preservation assertion covers this bounded failure.",
                    "reused_assertions": ["original_objective_preserved"],
                },
            },
        },
        "visible_evidence": [
            {"kind": "user_message", "source": "current-visible-context", "content": "slopwall"},
            {"kind": "rule_snapshot", "source": "RULES.md", "content": "Apply the correction and continue the inherited objective."},
        ],
        "replay": {
            "id": f"replay-{event_id.lower()}",
            "title": f"Replay for {event_id}",
            "incident_class": "correction_binding",
            "inherited_objective": "Continue the inherited task with the corrected result.",
            "live_state": ["The inherited task is still active."],
            "protected_state": ["The inherited objective."],
            "hard_exclusions": ["Do not replace repair with incident ceremony."],
            "failure_candidate": {"action": "Explain the failure and stop."},
            "success_candidate": {"action": "Apply the correction and continue the original task."},
            "discriminating_evidence": ["Whether the next substantive action advances the original task."],
            "completion_condition": "The original task advances with the correction applied.",
            "scoring": {
                "correction_applied_before_next_action": "required",
                "next_substantive_action_advances_objective": "required",
                "original_objective_preserved": "required",
            },
        },
        "memory": {
            "scope": "assistant-response-quality/test",
            "tags": ["slopwall", "regression"],
            "title": f"Bounded correction for {event_id}",
            "text": "The reusable lesson is to apply the known correction and advance the inherited objective instead of replacing repair with process explanation.",
            "interpretation": "The event records a correction-binding failure and preserves the reusable objective-preservation lesson.",
            "confidence": 95,
            "confidence_reason": "The trigger, failed boundary, governing rule, and repaired counterfactual are all present in the bounded visible evidence.",
        },
    }


def files_under(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def test_materialize_creates_bound_pending_bundle_without_canonical_memory(tmp_path: Path) -> None:
    result = materialize_capture(capture_spec(), root=tmp_path)
    assert result["status"] == "MATERIALIZED_PENDING_CANONICAL_MEMORY"
    assert result["closure_state"] == "REPAIRED_PENDING_DURABILITY"
    assert result["canonical_memory_written"] is False
    assert result["changed_files"] == 5

    expected = {
        result["report_ref"],
        result["evidence_ref"],
        result["replay_ref"],
        result["pending_memory_ref"],
        "provenance.json",
    }
    assert files_under(tmp_path) == expected
    assert not (tmp_path / "memory/memory-bank.jsonl").exists()

    replay = json.loads((tmp_path / result["replay_ref"]).read_text(encoding="utf-8"))
    event = replay["incident_event"]
    assert event["analysis"]["first_supported_divergence"].startswith("The response selected")
    assert event["capture"]["scope"] == "VISIBLE_CONTEXT_ONLY"
    assert event["capture"]["full_conversation_reload"] is False
    validate_slopwall_fixture(replay, root=tmp_path, filename=Path(result["replay_ref"]).name)

    ok, errors, _ = validate_provenance(tmp_path / "provenance.json")
    assert ok, errors


def test_invalid_generated_replay_leaves_no_final_artifacts(tmp_path: Path) -> None:
    spec = capture_spec()
    spec["event"]["severity_100"] = 100
    with pytest.raises(BehaviorIncidentCaptureError, match="generated replay failed V2 validation"):
        materialize_capture(spec, root=tmp_path)
    assert files_under(tmp_path) == set()


def test_destination_collision_is_preflighted_before_any_other_write(tmp_path: Path) -> None:
    spec = capture_spec()
    report = tmp_path / "01 Reports/SW-V2-TEST-MAT-001_incident.md"
    report.parent.mkdir(parents=True)
    report.write_text("pre-existing different report\n", encoding="utf-8")
    before = report.read_bytes()

    with pytest.raises(BehaviorIncidentCaptureError, match="refusing to overwrite different artifact"):
        materialize_capture(spec, root=tmp_path)

    assert report.read_bytes() == before
    assert files_under(tmp_path) == {"01 Reports/SW-V2-TEST-MAT-001_incident.md"}


def test_provenance_collision_is_preflighted_before_artifact_write(tmp_path: Path) -> None:
    provenance = {
        "entries": [{
            "incident_id": "SW-V2-TEST-MAT-001",
            "report_path": "01 Reports/different.md",
            "title": "Different incident",
            "date": "2026-09-13",
            "evidence_type": "other",
            "raw_transcripts": [],
            "evidence_files": [],
            "contract_snapshots": [],
            "duplicate_status": "canonical",
            "superseded_by": None,
            "missing": [],
        }]
    }
    (tmp_path / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    before = (tmp_path / "provenance.json").read_bytes()

    with pytest.raises(BehaviorIncidentCaptureError, match="provenance collision"):
        materialize_capture(capture_spec(), root=tmp_path)

    assert (tmp_path / "provenance.json").read_bytes() == before
    assert files_under(tmp_path) == {"provenance.json"}


def test_mid_commit_io_failure_rolls_back_all_capture_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real_replace = os.replace
    calls = {"count": 0, "failed": False}

    def fail_once_on_second_replace(src: str | bytes | os.PathLike[str] | os.PathLike[bytes], dst: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> None:
        calls["count"] += 1
        if calls["count"] == 2 and not calls["failed"]:
            calls["failed"] = True
            raise OSError("simulated commit failure")
        real_replace(src, dst)

    monkeypatch.setattr(capture.os, "replace", fail_once_on_second_replace)
    with pytest.raises(BehaviorIncidentCaptureError, match="rolled back"):
        materialize_capture(capture_spec(), root=tmp_path)

    assert calls["failed"] is True
    assert files_under(tmp_path) == set()


def test_materialize_is_idempotent_for_identical_bundle(tmp_path: Path) -> None:
    spec = capture_spec()
    first = materialize_capture(spec, root=tmp_path)
    snapshot = {ref: (tmp_path / ref).read_bytes() for ref in files_under(tmp_path)}

    second = materialize_capture(spec, root=tmp_path)
    assert second["status"] == "ALREADY_MATERIALIZED_PENDING_CANONICAL_MEMORY"
    assert second["changed_files"] == 0
    assert second["provenance_added"] is False
    assert {ref: (tmp_path / ref).read_bytes() for ref in files_under(tmp_path)} == snapshot


def test_capture_contract_rejects_full_chat_reload_before_writes(tmp_path: Path) -> None:
    spec = capture_spec()
    spec["event"]["full_conversation_reload"] = True
    with pytest.raises(BehaviorIncidentCaptureError, match="full_conversation_reload must be false"):
        materialize_capture(spec, root=tmp_path)
    assert files_under(tmp_path) == set()
