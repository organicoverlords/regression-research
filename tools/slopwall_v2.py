from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.replay_scoring import FixtureError, validate_fixture

ROOT = Path(__file__).resolve().parents[1]
TRIGGER_FORMS = {
    "SLOPWALL": {"slopwall", "slop wall"},
    "INCIDENT_REPORT": {"incident report"},
}
CONFIDENCE = {"A", "B", "C", "D"}
SCORE_KEYS = (
    "information_slop",
    "task_displacement",
    "execution_damage",
    "correction_resistance",
    "control_state_pathology",
)


class SlopwallV2Error(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SlopwallV2Error(message)


def validate_slopwall_fixture(raw: dict[str, Any], *, root: Path = ROOT, filename: str = "<fixture>") -> dict[str, Any]:
    """Validate the Slopwall V2 metadata layered onto an ordinary replay fixture.

    This is deliberately a validator only: it does not write reports, memories, rules,
    bootstrap state, or runtime state.
    """
    try:
        validate_fixture(raw, root=root, filename=filename)
    except FixtureError as exc:
        raise SlopwallV2Error(str(exc)) from exc

    event = raw.get("incident_event")
    if event is None:
        event = raw.get("slopwall_event")  # draft compatibility while V2 migrates
    _require(isinstance(event, dict), f"{filename}: incident_event object is required")
    event_id = event.get("event_id")
    _require(isinstance(event_id, str) and event_id.strip(), f"{filename}: event_id is required")
    _require(event.get("occurrence_role") == "CORRECTIVE_INTERVENTION", f"{event_id}: occurrence_role must be CORRECTIVE_INTERVENTION")

    source_message = event.get("source_message")
    _require(isinstance(source_message, str) and source_message.strip(), f"{event_id}: source_message is required")
    capture = event.get("capture")
    _require(isinstance(capture, dict), f"{event_id}: capture object is required")
    _require(capture.get("scope") == "VISIBLE_CONTEXT_ONLY", f"{event_id}: capture.scope must be VISIBLE_CONTEXT_ONLY")
    _require(capture.get("verbatim") is True, f"{event_id}: visible raw evidence must be captured verbatim")
    _require(capture.get("full_conversation_reload") is False, f"{event_id}: full conversation reload/backfill is forbidden")
    _require(capture.get("retrieval_for_capture_only") is False, f"{event_id}: retrieval solely to expand incident capture is forbidden")
    evidence_ref = capture.get("evidence_ref")
    _require(isinstance(evidence_ref, str) and evidence_ref.strip(), f"{event_id}: capture.evidence_ref is required")
    evidence_path = (root / evidence_ref).resolve()
    _require(evidence_path.is_relative_to(root.resolve()), f"{event_id}: capture.evidence_ref must stay inside the Vault checkout")
    _require(evidence_path.is_file(), f"{event_id}: capture.evidence_ref does not exist: {evidence_ref}")
    try:
        evidence_payload = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SlopwallV2Error(f"{event_id}: invalid visible-context evidence: {exc}") from exc
    _require(evidence_payload.get("capture_scope") == "VISIBLE_CONTEXT_ONLY", f"{event_id}: evidence capture_scope must be VISIBLE_CONTEXT_ONLY")
    _require(evidence_payload.get("verbatim") is True, f"{event_id}: evidence must declare verbatim=true")
    _require(evidence_payload.get("full_conversation_reload") is False, f"{event_id}: evidence must declare full_conversation_reload=false")
    items = evidence_payload.get("items")
    _require(isinstance(items, list) and items, f"{event_id}: visible-context evidence must contain at least one item")
    for index, item in enumerate(items):
        _require(isinstance(item, dict) and isinstance(item.get("content"), str) and item["content"], f"{event_id}: evidence item {index} must preserve non-empty verbatim content")
    trigger_kind = event.get("trigger_kind")
    _require(trigger_kind in TRIGGER_FORMS, f"{event_id}: trigger_kind must be SLOPWALL or INCIDENT_REPORT")
    _require(event.get("trigger_intent") == "EXECUTE_CORRECTION_LOOP", f"{event_id}: trigger_intent must confirm an explicit corrective command, not a meta-reference")
    matched_form = str(event.get("matched_form", "")).casefold()
    _require(matched_form in TRIGGER_FORMS[trigger_kind], f"{event_id}: matched_form is invalid for trigger_kind {trigger_kind}")
    _require(matched_form in source_message.casefold(), f"{event_id}: matched_form must occur literally in source_message")
    _require(any(isinstance(item, dict) and item.get("content") == source_message for item in items), f"{event_id}: source_message must be preserved verbatim in visible-context evidence")

    provenance = event.get("provenance")
    _require(isinstance(provenance, list) and provenance, f"{event_id}: provenance is required")
    _require(all(isinstance(item, dict) and isinstance(item.get("ref"), str) and item["ref"].strip() for item in provenance), f"{event_id}: each provenance item requires ref")
    refs = [item["ref"] for item in provenance]
    _require(len(refs) == len(set(refs)), f"{event_id}: duplicate provenance ref")

    parent = event.get("parent_event_id")
    _require(parent is None or (isinstance(parent, str) and parent.strip()), f"{event_id}: parent_event_id must be null or non-empty string")
    _require(parent != event_id, f"{event_id}: parent_event_id cannot self-reference")

    analysis = event.get("analysis")
    _require(isinstance(analysis, dict), f"{event_id}: analysis object is required")
    _require(isinstance(analysis.get("failure_boundary"), str) and analysis["failure_boundary"].strip(), f"{event_id}: analysis.failure_boundary is required")
    _require(isinstance(analysis.get("user_needed"), str) and analysis["user_needed"].strip(), f"{event_id}: analysis.user_needed is required")
    _require(isinstance(analysis.get("assistant_did"), str) and analysis["assistant_did"].strip(), f"{event_id}: analysis.assistant_did is required")
    guidance = analysis.get("governing_guidance")
    _require(isinstance(guidance, list) and guidance, f"{event_id}: analysis.governing_guidance is required")
    allowed_guidance = {"LOADED", "AVAILABLE_NOT_LOADED", "MISSING", "STALE_OR_CONFLICTING", "UNKNOWN"}
    for item in guidance:
        _require(isinstance(item, dict) and isinstance(item.get("source"), str) and item["source"].strip(), f"{event_id}: governing guidance requires source")
        _require(item.get("status") in allowed_guidance, f"{event_id}: invalid governing-guidance status")
    failure_class = analysis.get("failure_class")
    allowed_classes = {"RULE_VIOLATION", "RULE_MISSED", "RULE_CONFLICT", "RULE_GAP", "AUTHORITY_SELECTION", "REASONING_OR_ACTION_SELECTION", "UNKNOWN"}
    _require(failure_class in allowed_classes, f"{event_id}: invalid analysis.failure_class")
    _require(isinstance(analysis.get("correct_counterfactual"), str) and analysis["correct_counterfactual"].strip(), f"{event_id}: analysis.correct_counterfactual is required")
    _require(isinstance(analysis.get("repaired_result"), str) and analysis["repaired_result"].strip(), f"{event_id}: analysis.repaired_result is required")
    recommend_rule_change = analysis.get("rule_change_recommended")
    _require(isinstance(recommend_rule_change, bool), f"{event_id}: analysis.rule_change_recommended must be boolean")
    if recommend_rule_change:
        _require(failure_class in {"RULE_GAP", "RULE_CONFLICT"}, f"{event_id}: rule change requires proven RULE_GAP or RULE_CONFLICT")
        _require(isinstance(analysis.get("rule_change_evidence"), str) and analysis["rule_change_evidence"].strip(), f"{event_id}: rule change requires rule_change_evidence")

    contract_review = analysis.get("behavior_contract_review")
    _require(isinstance(contract_review, dict), f"{event_id}: analysis.behavior_contract_review is required")
    _require(contract_review.get("search_performed") is True, f"{event_id}: behavior-contract search must be performed")
    checked_assertions = contract_review.get("checked_assertions")
    _require(isinstance(checked_assertions, list), f"{event_id}: checked_assertions must be a list")
    _require(all(isinstance(item, str) and item.strip() for item in checked_assertions), f"{event_id}: checked_assertions must contain non-empty names")
    disposition = contract_review.get("disposition")
    _require(disposition in {"REUSE_EXISTING", "PROPOSE_NEW", "NONE"}, f"{event_id}: invalid behavior-contract disposition")
    _require(isinstance(contract_review.get("reason"), str) and contract_review["reason"].strip(), f"{event_id}: behavior-contract review requires reason")
    scoring_names = set(raw.get("scoring", {}))
    if disposition == "REUSE_EXISTING":
        reused = contract_review.get("reused_assertions")
        _require(isinstance(reused, list) and reused, f"{event_id}: REUSE_EXISTING requires reused_assertions")
        _require(set(reused).issubset(set(checked_assertions)), f"{event_id}: reused_assertions must have been checked")
        _require(set(reused).issubset(scoring_names), f"{event_id}: reused_assertions must be bound into fixture scoring")
    elif disposition == "PROPOSE_NEW":
        proposed = contract_review.get("proposed_assertions")
        _require(isinstance(proposed, list) and proposed, f"{event_id}: PROPOSE_NEW requires proposed_assertions")
        _require(all(isinstance(item, str) and item.strip() for item in proposed), f"{event_id}: proposed_assertions must contain non-empty names")
        _require(set(proposed).issubset(scoring_names), f"{event_id}: proposed assertions must be bound into fixture scoring")
    memory_ref = event.get("memory_ref")
    _require(isinstance(memory_ref, str) and memory_ref.strip(), f"{event_id}: memory_ref is required for closure")

    confidence = event.get("evidence_confidence")
    _require(confidence in CONFIDENCE, f"{event_id}: invalid evidence_confidence")
    scores = event.get("scores")
    severity = event.get("severity_100")
    if confidence == "D":
        _require(scores is None, f"{event_id}: D-confidence must remain unscored")
        _require(severity is None, f"{event_id}: D-confidence severity must be null/UNSCORABLE")
    else:
        _require(isinstance(scores, dict), f"{event_id}: A/B/C evidence requires scores")
        for key in SCORE_KEYS:
            value = scores.get(key)
            _require(isinstance(value, int) and 0 <= value <= 5, f"{event_id}: invalid score {key}")
        expected = sum(scores[key] for key in SCORE_KEYS) * 4
        _require(severity == expected, f"{event_id}: severity_100 must equal score sum * 4 ({expected})")

    closure = event.get("closure_state")
    _require(closure in {"OPEN", "REPAIRED_PENDING_DURABILITY", "CLOSED"}, f"{event_id}: invalid closure_state")
    if closure == "CLOSED":
        _require(bool(raw.get("source_report")), f"{event_id}: CLOSED event requires source_report")
        _require(bool(memory_ref), f"{event_id}: CLOSED event requires memory_ref")
        _require(raw.get("replay_ready", True) is not False, f"{event_id}: CLOSED event cannot have replay_ready=false")

    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a non-live Slopwall V2 replay/event fixture")
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    raw = json.loads(args.fixture.read_text(encoding="utf-8-sig"))
    validate_slopwall_fixture(raw, root=ROOT, filename=args.fixture.name)
    event = raw.get("incident_event") or raw["slopwall_event"]
    print(json.dumps({"status": "VALID", "event_id": event["event_id"], "closure_state": event["closure_state"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

