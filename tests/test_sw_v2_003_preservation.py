from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPLAY_003 = ROOT / "03 Fixtures and Experiments/SW-V2-20260913-003_replay.json"
REPLAY_004 = ROOT / "03 Fixtures and Experiments/SW-V2-20260913-004_replay.json"
PROVENANCE = ROOT / "provenance.json"


def test_sw_v2_003_is_preserved_but_marked_superseded() -> None:
    replay = json.loads(REPLAY_003.read_text(encoding="utf-8-sig"))
    event = replay["incident_event"]
    assert event["event_id"] == "SW-V2-20260913-003"
    assert event["closure_state"] == "CLOSED"  # historical state is preserved, not rewritten
    assert "normalize/start RR-KONE-02" in replay["success_candidate"]["action"]

    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8-sig"))
    entry = next(item for item in provenance["entries"] if item.get("incident_id") == "SW-V2-20260913-003")
    assert entry["duplicate_status"] == "superseded"
    assert entry["superseded_by"] == "SW-V2-20260913-004"
    assert "authority_proof_absent_for_runner_mutation" in entry["missing"]
    assert "closed PR #1117" in entry["notes"]


def test_sw_v2_004_supersedes_the_bad_003_memory_lesson_without_deleting_history() -> None:
    replay = json.loads(REPLAY_004.read_text(encoding="utf-8-sig"))
    memory = replay["memory_candidate"]
    assert memory["supersedes"] == ["mem-sw-v2-20260913-003"]
    assert "Corrective triggers never substitute for normal control-plane authority" in memory["text"]
    assert replay["incident_event"]["repair_authority"] == {"mode": "NOT_REQUIRED"}


def test_sw_v2_003_artifact_chain_exists_for_historical_evidence() -> None:
    for rel in (
        "01 Reports/SW-V2-20260913-003_incident.md",
        "02 Evidence/SW-V2-20260913-003_visible-context.json",
        "03 Fixtures and Experiments/SW-V2-20260913-003_replay.json",
        "memory/reports/SW-V2-20260913-003_pending-memory.md",
    ):
        assert (ROOT / rel).is_file(), rel
