from __future__ import annotations

import json
from pathlib import Path

from tools.replay_scoring import score_fixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "03 Fixtures and Experiments/2026-09-13_headless_tool_commentary_boundary.json"


def load_fixture() -> dict:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["_path"] = FIXTURE.name
    return fixture


def test_routine_headless_commentary_fails_and_silent_control_passes() -> None:
    fixture = load_fixture()
    success = score_fixture(fixture, fixture["success_candidate"], candidate_name="success", root=ROOT)
    failure = score_fixture(fixture, fixture["failure_candidate"], candidate_name="failure", root=ROOT)
    assert success["passed"] is True
    assert failure["passed"] is False
    assert "routine_headless_tool_commentary_absent" in failure["violations"]


def test_foreground_or_material_notice_remains_allowed() -> None:
    fixture = load_fixture()
    candidate = {
        "action":"Continue the original task; announce the visible foreground browser navigation because the user session will change, then perform the required action.",
        "trace":[
            {"kind":"task_context","delivered":True,"evidence_ids":["objective"]},
            {"kind":"evidence_inspection","evidence_ids":["objective"]},
            {"kind":"commentary","reason":"foreground_notice","text":"I am about to navigate the visible browser tab."},
            {"kind":"tool_call","tool":"foreground_ui_tool"},
        ],
    }
    result = score_fixture(fixture, candidate, candidate_name="foreground-notice", root=ROOT)
    assert result["passed"] is True
