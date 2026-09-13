from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.behavior_incident_close as close_mod
from tests.test_behavior_incident_capture import capture_spec
from tools.behavior_incident_capture import materialize_capture
from tools.behavior_incident_close import BehaviorIncidentCloseError, close_incident, plan_closure
from tools.memory_bank import append_entry, load_bank
from tools.slopwall_v2 import validate_slopwall_fixture


def prepared_incident(tmp_path: Path, event_id: str = "SW-V2-TEST-CLOSE-001") -> tuple[dict, Path]:
    result = materialize_capture(capture_spec(event_id), root=tmp_path)
    replay_path = tmp_path / result["replay_ref"]
    return result, replay_path


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
