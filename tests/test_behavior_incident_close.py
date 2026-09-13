from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import tools.behavior_incident_close as close_mod
from tests.test_behavior_incident_capture import capture_spec
from tools.behavior_incident_capture import materialize_capture
from tools.behavior_incident_close import BehaviorIncidentCloseError, bind_repair, close_incident, plan_closure
from tools.memory_bank import MAX_TITLE_CHARS, append_entry, load_bank, search_memory_entries
from tools.replay_scoring import score_fixture
from tools.slopwall_v2 import validate_slopwall_fixture




def init_feature_repo_with_origin_main(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Behavior Incident Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.test").write_text("canonical base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp_path, check=True)
    subprocess.run(["git", "switch", "-c", "incident"], cwd=tmp_path, check=True, capture_output=True)

def prepared_incident(tmp_path: Path, event_id: str = "SW-V2-TEST-CLOSE-001", *, bind: bool = True) -> tuple[dict, Path]:
    result = materialize_capture(capture_spec(event_id), root=tmp_path)
    replay_path = tmp_path / result["replay_ref"]
    if bind:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        candidate = replay["success_candidate"]
        bound = bind_repair(replay_path, observation=candidate["action"], candidate=candidate, root=tmp_path)
        assert bound["passed"] is True
    return result, replay_path




def test_repair_candidate_must_equal_observed_visible_content(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path, "SW-V2-TEST-CLOSE-MISMATCH", bind=False)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    candidate = replay["success_candidate"]
    with pytest.raises(BehaviorIncidentCloseError, match="must equal the observed visible repair content"):
        bind_repair(replay_path, observation="A different user-visible reply.", candidate=candidate, root=tmp_path)
    unchanged = json.loads(replay_path.read_text(encoding="utf-8"))
    assert unchanged["incident_event"]["repair_binding"]["status"] == "PENDING_OBSERVATION"


def test_authority_sensitive_repair_requires_normal_owner_gate_proof(tmp_path: Path) -> None:
    spec = capture_spec("SW-V2-TEST-CLOSE-AUTH")
    spec["event"]["repair_authority"] = {
        "mode": "REQUIRED",
        "owner": "runner-owner",
        "gate": "runner-start-gate",
        "corrective_trigger_is_authority": False,
    }
    result = materialize_capture(spec, root=tmp_path)
    replay_path = tmp_path / result["replay_ref"]
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    candidate = dict(replay["success_candidate"])
    scored_without_authority = score_fixture(replay, candidate, candidate_name="missing-authority", root=tmp_path)
    assert scored_without_authority["passed"] is False
    assert "repair_authority_independently_proven" in scored_without_authority["violations"]

    with pytest.raises(BehaviorIncidentCloseError, match="independent authority proof"):
        bind_repair(replay_path, observation=candidate["action"], candidate=candidate, root=tmp_path)

    candidate["authority_proof"] = {
        "status": "PASS",
        "owner": "runner-owner",
        "gate": "runner-start-gate",
        "basis": "normal_owner_gate",
        "evidence_refs": ["runtime:runner-owner-gate-pass"],
    }
    scored_with_authority = score_fixture(replay, candidate, candidate_name="valid-authority", root=tmp_path)
    assert scored_with_authority["passed"] is True
    authority_evidence = [{
        "kind": "authority_evidence",
        "ref": "runtime:runner-owner-gate-pass",
        "source": "runner-owner-runtime-receipt",
        "owner": "runner-owner",
        "gate": "runner-start-gate",
        "status": "PASS",
        "content": "The normal runner owner/gate independently accepted the mutation.",
    }]
    bound = bind_repair(
        replay_path, observation=candidate["action"], candidate=candidate,
        authority_evidence=authority_evidence, root=tmp_path,
    )
    assert bound["passed"] is True
    rebound = json.loads(replay_path.read_text(encoding="utf-8"))
    assert rebound["incident_event"]["repair_binding"]["status"] == "SCORED_PASS"
    assert rebound["repair_candidate"]["authority_proof"]["owner"] == "runner-owner"
    binding = rebound["incident_event"]["repair_binding"]
    assert len(binding["authority_item_indexes"]) == 1
    evidence = json.loads((tmp_path / rebound["incident_event"]["capture"]["evidence_ref"]).read_text(encoding="utf-8"))
    authority_item = evidence["items"][binding["authority_item_indexes"][0]]
    assert authority_item["ref"] == "runtime:runner-owner-gate-pass"
    assert authority_item["kind"] == "authority_evidence"


def test_authority_proof_without_persisted_owner_gate_evidence_is_rejected(tmp_path: Path) -> None:
    spec = capture_spec("SW-V2-TEST-CLOSE-AUTH-NO-EVIDENCE")
    spec["event"]["repair_authority"] = {
        "mode": "REQUIRED",
        "owner": "runner-owner",
        "gate": "runner-start-gate",
        "corrective_trigger_is_authority": False,
    }
    result = materialize_capture(spec, root=tmp_path)
    replay_path = tmp_path / result["replay_ref"]
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    candidate = dict(replay["success_candidate"])
    candidate["authority_proof"] = {
        "status": "PASS",
        "owner": "runner-owner",
        "gate": "runner-start-gate",
        "basis": "normal_owner_gate",
        "evidence_refs": ["runtime:runner-owner-gate-pass"],
    }
    with pytest.raises(BehaviorIncidentCloseError, match="persisted authority evidence"):
        bind_repair(replay_path, observation=candidate["action"], candidate=candidate, root=tmp_path)


def test_corrective_trigger_cannot_be_authority_proof(tmp_path: Path) -> None:
    spec = capture_spec("SW-V2-TEST-CLOSE-AUTH-TRIGGER")
    spec["event"]["repair_authority"] = {
        "mode": "REQUIRED",
        "owner": "runner-owner",
        "gate": "runner-start-gate",
        "corrective_trigger_is_authority": False,
    }
    result = materialize_capture(spec, root=tmp_path)
    replay_path = tmp_path / result["replay_ref"]
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    candidate = dict(replay["success_candidate"])
    candidate["authority_proof"] = {
        "status": "PASS",
        "owner": "runner-owner",
        "gate": "runner-start-gate",
        "basis": "slopwall",
        "evidence_refs": ["conversation:slopwall"],
    }
    with pytest.raises(BehaviorIncidentCloseError, match="corrective trigger is not repair authority"):
        bind_repair(replay_path, observation=candidate["action"], candidate=candidate, root=tmp_path)


def test_bind_repair_cli_forwards_authority_evidence_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    observation_path = tmp_path / "observation.txt"
    candidate_path = tmp_path / "candidate.json"
    authority_path = tmp_path / "authority.json"
    replay_path = tmp_path / "replay.json"
    observation_path.write_text("Observed repaired action.", encoding="utf-8")
    candidate_path.write_text(json.dumps({"action": "Observed repaired action."}), encoding="utf-8")
    authority_items = [{
        "kind": "authority_evidence",
        "ref": "runtime:gate-pass",
        "source": "normal-owner",
        "owner": "normal-owner",
        "gate": "normal-gate",
        "status": "PASS",
        "content": "Normal owner gate passed.",
    }]
    authority_path.write_text(json.dumps(authority_items), encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_bind(replay: Path, **kwargs):
        seen["replay"] = replay
        seen.update(kwargs)
        return {"status": "BOUND", "passed": True}

    monkeypatch.setattr(close_mod, "bind_repair", fake_bind)
    monkeypatch.setattr(sys, "argv", [
        "behavior_incident_close.py", "bind-repair", str(replay_path),
        "--observation-file", str(observation_path),
        "--candidate-file", str(candidate_path),
        "--authority-evidence-file", str(authority_path),
        "--kind", "assistant_action",
    ])
    assert close_mod.main() == 0
    assert seen["replay"] == replay_path
    assert seen["observation"] == "Observed repaired action."
    assert seen["candidate"] == {"action": "Observed repaired action."}
    assert seen["authority_evidence"] == authority_items
    assert seen["kind"] == "assistant_action"
    assert json.loads(capsys.readouterr().out)["status"] == "BOUND"


def test_unbound_repair_blocks_closure_before_memory(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path, "SW-V2-TEST-CLOSE-UNBOUND", bind=False)
    with pytest.raises(BehaviorIncidentCloseError, match="actual visible repair"):
        plan_closure(replay_path, root=tmp_path)
    assert not (tmp_path / "memory/memory-bank.jsonl").exists()


def test_failed_repair_is_preserved_but_cannot_close(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path, "SW-V2-TEST-CLOSE-FAILED", bind=False)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    candidate = replay["failure_candidate"]
    bound = bind_repair(replay_path, observation=candidate["action"], candidate=candidate, root=tmp_path)
    assert bound["passed"] is False
    rebound = json.loads(replay_path.read_text(encoding="utf-8"))
    assert rebound["incident_event"]["repair_binding"]["status"] == "SCORED_FAIL"
    evidence = json.loads((tmp_path / rebound["incident_event"]["capture"]["evidence_ref"]).read_text(encoding="utf-8"))
    assert evidence["items"][-1]["content"] == candidate["action"]
    with pytest.raises(BehaviorIncidentCloseError, match="actual visible repair"):
        plan_closure(replay_path, root=tmp_path)

def test_plan_is_read_only_and_uses_deterministic_memory_id(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path)
    before = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    plan = plan_closure(replay_path, root=tmp_path)
    after = {p.relative_to(tmp_path).as_posix(): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert plan["memory_id"] == "mem-sw-v2-test-close-001"
    assert plan["memory_ref"] == "memory/memory-bank.jsonl#mem-sw-v2-test-close-001"
    assert before == after


def test_close_records_canonical_memory_and_closes_replay_and_provenance(tmp_path: Path) -> None:
    result, replay_path = prepared_incident(tmp_path)
    provenance_path = tmp_path / "provenance.json"
    pending_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    pending_provenance["entries"][0]["missing"].append("searchable_memory_pointer_pending_non_live_v2_design")
    provenance_path.write_text(json.dumps(pending_provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    closed = close_incident(replay_path, root=tmp_path)
    assert closed["status"] == "CLOSED"
    assert closed["canonical_memory_written"] is True

    bank = load_bank(tmp_path / "memory/memory-bank.jsonl")
    assert len(bank) == 1
    memory = bank[0]
    assert memory["id"] == closed["memory_id"]
    assert memory["state"] == "PROVEN"
    assert memory["source_messages"] == ["slopwall"]
    assert memory["thread"] == "behavior-incident:SW-V2-TEST-CLOSE-001"
    assert set(memory["evidence"]) == {result["report_ref"], result["replay_ref"], result["evidence_ref"]}

    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    event = replay["incident_event"]
    assert event["closure_state"] == "CLOSED"
    assert event["memory_ref"] == closed["memory_ref"]
    validate_slopwall_fixture(replay, root=tmp_path, filename=replay_path.name)

    provenance = json.loads((tmp_path / "provenance.json").read_text(encoding="utf-8"))
    entry = provenance["entries"][0]
    assert entry["canonical_memory_ref"] == closed["memory_ref"]
    assert "canonical_memory_pending" not in entry["missing"]
    assert "searchable_memory_pointer_pending_non_live_v2_design" not in entry["missing"]


def test_closed_correction_supersedes_old_memory_from_ordinary_recall(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path, "SW-V2-TEST-CLOSE-SUPERSEDES")
    bank_path = tmp_path / "memory/memory-bank.jsonl"
    append_entry(bank_path, {
        "id": "mem-old-runner-lesson",
        "timestamp": "2026-09-12T12:00:00+03:00",
        "kind": "correction",
        "scope": "assistant-orchestration/runner-recovery",
        "tags": ["slopwall", "regression"],
        "title": "Old runner recovery lesson",
        "text": "Legacy runner recovery trigger lesson that should be superseded.",
        "state": "PROVEN",
        "evidence": ["legacy:runner-recovery"],
        "supersedes": [],
    })
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["memory_candidate"]["supersedes"] = ["mem-old-runner-lesson"]
    replay_path.write_text(json.dumps(replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    closed = close_incident(replay_path, root=tmp_path)
    assert closed["status"] == "CLOSED"
    entries = load_bank(bank_path)
    new_memory = next(item for item in entries if item["id"] == closed["memory_id"])
    assert new_memory["supersedes"] == ["mem-old-runner-lesson"]
    ordinary = search_memory_entries(entries, "Legacy runner recovery trigger lesson", history=False)
    historical = search_memory_entries(entries, "Legacy runner recovery trigger lesson", history=True)
    assert all(item["id"] != "mem-old-runner-lesson" for item in ordinary)
    assert any(item["id"] == "mem-old-runner-lesson" for item in historical)


def test_close_is_idempotent_after_closed_state(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path)
    first = close_incident(replay_path, root=tmp_path)
    provenance_path = tmp_path / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["entries"][0]["missing"].append("searchable_memory_pointer_pending_non_live_v2_design")
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    second = close_incident(replay_path, root=tmp_path)
    assert first["status"] == "CLOSED"
    assert second["status"] == "ALREADY_CLOSED"
    assert second["canonical_memory_written"] is False
    repaired_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert "searchable_memory_pointer_pending_non_live_v2_design" not in repaired_provenance["entries"][0]["missing"]
    assert len(load_bank(tmp_path / "memory/memory-bank.jsonl")) == 1


def test_plan_closure_rejects_oversized_memory_title_before_bank_write(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path, "SW-V2-TEST-CLOSE-TITLE-LIMIT")
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["memory_candidate"]["title"] = "x" * (MAX_TITLE_CHARS + 1)
    replay_path.write_text(json.dumps(replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(BehaviorIncidentCloseError, match=f"memory_candidate.title exceeds {MAX_TITLE_CHARS} characters"):
        plan_closure(replay_path, root=tmp_path)
    assert not (tmp_path / "memory/memory-bank.jsonl").exists()


def test_missing_structured_memory_candidate_fails_before_bank_write(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay.pop("memory_candidate")
    replay_path.write_text(json.dumps(replay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(BehaviorIncidentCloseError, match="structured memory_candidate"):
        close_incident(replay_path, root=tmp_path)
    assert not (tmp_path / "memory/memory-bank.jsonl").exists()


def test_existing_deterministic_memory_conflict_blocks_finalization(tmp_path: Path) -> None:
    _, replay_path = prepared_incident(tmp_path)
    plan = plan_closure(replay_path, root=tmp_path)
    conflicting = dict(plan["memory_values"])
    conflicting["text"] = "Different lesson under the same deterministic incident memory id."
    append_entry(tmp_path / "memory/memory-bank.jsonl", conflicting)

    with pytest.raises(BehaviorIncidentCloseError, match="different content"):
        close_incident(replay_path, root=tmp_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    assert replay["incident_event"]["closure_state"] == "REPAIRED_PENDING_DURABILITY"
    assert len(load_bank(tmp_path / "memory/memory-bank.jsonl")) == 1


def test_memory_survives_finalize_failure_and_rerun_resumes_without_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, replay_path = prepared_incident(tmp_path)
    real_commit = close_mod._commit_updates

    def fail_finalize(updates):
        raise BehaviorIncidentCloseError("simulated repository finalization failure")

    monkeypatch.setattr(close_mod, "_commit_updates", fail_finalize)
    with pytest.raises(BehaviorIncidentCloseError, match="simulated repository finalization failure"):
        close_incident(replay_path, root=tmp_path)

    bank_path = tmp_path / "memory/memory-bank.jsonl"
    assert len(load_bank(bank_path)) == 1
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    assert replay["incident_event"]["closure_state"] == "REPAIRED_PENDING_DURABILITY"

    monkeypatch.setattr(close_mod, "_commit_updates", real_commit)
    resumed = close_incident(replay_path, root=tmp_path)
    assert resumed["status"] == "CLOSED"
    assert resumed["canonical_memory_written"] is False
    assert len(load_bank(bank_path)) == 1


def test_canonical_artifact_check_accepts_worktree_eol_normalization(tmp_path: Path) -> None:
    init_feature_repo_with_origin_main(tmp_path)
    result, replay_path = prepared_incident(tmp_path, "SW-V2-TEST-CLOSE-EOL")
    subprocess.run(["git", "add", result["report_ref"], result["replay_ref"], result["evidence_ref"], result["pending_memory_ref"], "provenance.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "land pending incident"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "core.autocrlf", "true"], cwd=tmp_path, check=True)
    report_path = tmp_path / result["report_ref"]
    canonical_bytes = subprocess.run(["git", "show", f"refs/remotes/origin/main:{result['report_ref']}"] , cwd=tmp_path, check=True, capture_output=True).stdout
    report_path.write_bytes(canonical_bytes.replace(b"\n", b"\r\n"))
    assert report_path.read_bytes() != canonical_bytes
    plan = plan_closure(replay_path, root=tmp_path)
    assert plan["event_id"] == "SW-V2-TEST-CLOSE-EOL"
    closed = close_incident(replay_path, root=tmp_path)
    assert closed["status"] == "CLOSED"


def test_close_requires_exact_incident_artifacts_on_origin_main(tmp_path: Path) -> None:
    init_feature_repo_with_origin_main(tmp_path)
    result, replay_path = prepared_incident(tmp_path, "SW-V2-TEST-CLOSE-CANONICAL")
    with pytest.raises(BehaviorIncidentCloseError, match="not present on origin/main"):
        close_incident(replay_path, root=tmp_path)
    assert not (tmp_path / "memory/memory-bank.jsonl").exists()

    subprocess.run(["git", "add", result["report_ref"], result["replay_ref"], result["evidence_ref"], result["pending_memory_ref"], "provenance.json"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "land pending incident"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp_path, check=True)
    closed = close_incident(replay_path, root=tmp_path)
    assert closed["status"] == "CLOSED"
