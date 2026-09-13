from __future__ import annotations

import json
from pathlib import Path

from tools.replay_scoring import score_fixture

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "03 Fixtures and Experiments/2026-09-07_0221_EEST_go-issue-completion-stop_next_action.json"


def load_fixture() -> dict:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8-sig"))
    raw["_path"] = FIXTURE.name
    return raw


def test_manual_go_fixture_is_replay_ready_and_controls_pass_fail() -> None:
    fixture = load_fixture()
    success = score_fixture(fixture, fixture["success_candidate"], candidate_name="success", root=ROOT)
    failure = score_fixture(fixture, fixture["failure_candidate"], candidate_name="failure", root=ROOT)
    assert success["passed"] is True
    assert failure["passed"] is False
    assert "premature_stop_with_unmet_acceptance" in failure["violations"]


def test_rule_recital_does_not_excuse_queued_or_collision_stop() -> None:
    fixture = load_fixture()
    candidate = {
        "action": "Case A: acceptance remains unmet for the original task. I know MANUAL GO IS NOT A TIMEBOX, but stop now because the contract gate is queued, another worker owns one target, and this is the first justified checkpoint. Case B: acceptance is satisfied, so stop normally."
    }
    result = score_fixture(fixture, candidate, candidate_name="rule-recital-then-stop", root=ROOT)
    assert result["passed"] is False
    assert "premature_stop_with_unmet_acceptance" in result["violations"]
