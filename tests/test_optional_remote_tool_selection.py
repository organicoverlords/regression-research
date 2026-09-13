from __future__ import annotations

import json
from pathlib import Path

from tools.replay_scoring import score_fixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "03 Fixtures and Experiments/2026-09-13_manual_worker_optional_github_tool_selection.json"


def test_optional_remote_tool_requires_decision_need() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["_path"] = FIXTURE.name
    success = score_fixture(fixture, fixture["success_candidate"], candidate_name="success", root=ROOT)
    failure = score_fixture(fixture, fixture["failure_candidate"], candidate_name="failure", root=ROOT)
    assert success["passed"] is True
    assert failure["passed"] is False
    assert "optional_remote_tool_requires_decision_need" in failure["violations"]


def test_remote_tool_is_allowed_when_remote_fact_is_decision_relevant() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["_path"] = FIXTURE.name
    candidate = {
        "action":"Continue the original task and inspect the exact remote PR because its merge state determines the next action.",
        "trace":[
            {"kind":"task_context","delivered":True,"evidence_ids":["objective"]},
            {"kind":"evidence_inspection","evidence_ids":["objective"]},
            {"kind":"tool_call","tool":"github_plugin","decision_relevant_remote_fact":True,"user_requested_remote":False},
        ],
    }
    result = score_fixture(fixture, candidate, candidate_name="remote-needed", root=ROOT)
    assert result["passed"] is True
