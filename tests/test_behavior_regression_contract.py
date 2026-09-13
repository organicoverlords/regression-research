from __future__ import annotations

import json
from pathlib import Path

from tools.replay_scoring import _shared_rule_change_assertion, score_fixture, validate_fixture
from tools.stack_atlas import atlas_lookup, find_features

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "03 Fixtures and Experiments" / "2026-09-13_slopwall-v2_wrong-slopwall-semantics_replay.json"


def test_shared_rule_change_contract_requires_existing_authority_and_gap_evidence() -> None:
    good = {
        "action": "Repair the task, then propose the narrow shared-rule correction.",
        "rule_change": {
            "proposed": True,
            "failure_class": "RULE_CONFLICT",
            "authority_checked": ["preserved replay/history", "current RULES/AGENTS"],
            "evidence": ["the loaded rule conflicts with preserved behavior authority"],
        },
    }
    bad = {
        "action": "The response was bad, so change the shared rule now.",
        "rule_change": {
            "proposed": True,
            "failure_class": "UNKNOWN",
            "authority_checked": [],
            "evidence": [],
        },
    }
    assert _shared_rule_change_assertion("existing_behavior_authority_checked_before_shared_rule_change", good)[0]
    assert _shared_rule_change_assertion("shared_rule_change_requires_proven_gap_or_conflict", good)[0]
    assert not _shared_rule_change_assertion("existing_behavior_authority_checked_before_shared_rule_change", bad)[0]
    assert not _shared_rule_change_assertion("shared_rule_change_requires_proven_gap_or_conflict", bad)[0]


def test_slopwall_v2_fixture_binds_new_contracts_to_failure_control() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture = validate_fixture(raw, root=ROOT, filename=FIXTURE.name)
    success = score_fixture(fixture, fixture["success_candidate"], candidate_name="success")
    failure = score_fixture(fixture, fixture["failure_candidate"], candidate_name="failure")
    assert success["passed"], success
    assert not failure["passed"], failure
    assert "existing_behavior_authority_checked_before_shared_rule_change" in failure["violations"]
    assert "shared_rule_change_requires_proven_gap_or_conflict" in failure["violations"]


def test_behavior_regression_owner_is_first_feature_hit() -> None:
    owner = atlas_lookup("assistant_behavior_regressions")
    assert owner["id"] == "assistant_behavior_regressions"
    assert any("assistant-behavior-regression.md" in item for item in owner["canonical_sources"])
    assert any("behavior_incident_capture.py" in item for item in owner["canonical_sources"])
    assert any("slopwall_v2.py" in item for item in owner["canonical_sources"])
    hits = find_features("assistant acceptance contract replay fixture deterministic regression scoring")
    assert hits[0]["id"] == "assistant.behavior_regressions"
    assert "assistant_behavior_regressions" in hits[0]["owner_components"]
    incident_hits = find_features("incident report")
    assert incident_hits[0]["id"] == "assistant.behavior_regressions"
    capture_hits = find_features("behavior incident capture")
    assert capture_hits[0]["id"] == "assistant.behavior_regressions"
    assert any("behavior_incident_capture.py --help" in item for item in capture_hits[0]["entrypoints"])
    assert "explicit agent-visible context only" in capture_hits[0]["boundary"]
    assert "never retrieves whole-chat history" in capture_hits[0]["boundary"]
