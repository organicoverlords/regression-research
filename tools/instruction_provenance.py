from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "tests" / "fixtures" / "instruction-provenance-policy.json"


class InstructionProvenanceError(ValueError):
    pass


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if policy.get("schema_version") != "1.0":
        raise InstructionProvenanceError("unsupported instruction-provenance schema")
    sources = policy.get("instruction_sources")
    invariants = policy.get("invariants")
    data_classes = policy.get("data_classes")
    if not isinstance(sources, dict) or not isinstance(invariants, dict) or not isinstance(data_classes, dict):
        raise InstructionProvenanceError("policy missing structured source/data/invariant sections")
    required_sources = {
        "current_user",
        "current_personal_instructions",
        "live_repo_policy",
        "durable_context",
        "historical_context",
        "retrieved_content",
        "assistant_generated",
    }
    missing = required_sources - set(sources)
    if missing:
        raise InstructionProvenanceError(f"missing instruction sources: {', '.join(sorted(missing))}")
    for name, spec in sources.items():
        if not isinstance(spec.get("rank"), int) or not isinstance(spec.get("can_direct"), bool):
            raise InstructionProvenanceError(f"{name}: invalid instruction-source definition")
    if sources["current_user"]["rank"] <= sources["durable_context"]["rank"]:
        raise InstructionProvenanceError("current user must outrank durable context")
    if sources["current_user"]["rank"] <= sources["historical_context"]["rank"]:
        raise InstructionProvenanceError("current user must outrank historical context")
    if sources["current_user"]["rank"] <= sources["current_personal_instructions"]["rank"]:
        raise InstructionProvenanceError("current user must outrank current personal instructions")
    if sources["current_personal_instructions"]["rank"] <= sources["live_repo_policy"]["rank"]:
        raise InstructionProvenanceError("current personal instructions must outrank live repo policy")
    if sources["current_personal_instructions"]["rank"] <= sources["durable_context"]["rank"]:
        raise InstructionProvenanceError("current personal instructions must outrank durable context")
    if sources["retrieved_content"]["can_direct"] or sources["retrieved_content"]["rank"] != 0:
        raise InstructionProvenanceError("retrieved content must not become instruction authority by default")
    if data_classes.get("protected_internal") != "non_disclosable_placeholder_only":
        raise InstructionProvenanceError("protected internal class must remain non-disclosable")
    required_invariants = {
        "current_explicit_instruction_beats_stale_context",
        "retrieved_text_is_not_instruction_by_default",
        "constraints_apply_only_to_affected_parts",
        "allowed_parts_survive_mixed_requests",
        "protected_internal_content_not_required_for_testing",
        "behavior_attribution_preserves_multiple_sources",
        "current_personal_instructions_beat_repo_and_stale_context",
        "current_explicit_instruction_beats_personal_instructions",
        "source_specific_claim_requires_inspected_primary_source",
        "uninspected_contextual_inference_must_be_labeled",
        "saved_context_review_before_correction",
    }
    if any(invariants.get(name) is not True for name in required_invariants):
        raise InstructionProvenanceError("all provenance invariants must be enabled")
    return policy


def resolve_directive(
    candidates: Iterable[dict[str, Any]],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    policy = validate_policy(policy or load_policy())
    sources = policy["instruction_sources"]
    eligible: list[tuple[int, int, dict[str, Any]]] = []
    for index, candidate in enumerate(candidates):
        source_class = candidate.get("source_class")
        if source_class not in sources:
            raise InstructionProvenanceError(f"unknown source class: {source_class}")
        spec = sources[source_class]
        if candidate.get("directive") is True and spec["can_direct"]:
            eligible.append((spec["rank"], index, candidate))
    if not eligible:
        return None
    # Later candidate wins only inside the same authority rank.
    _, _, winner = max(eligible, key=lambda item: (item[0], item[1]))
    return winner


def partition_request(
    parts: Iterable[dict[str, Any]],
    constraints: Iterable[dict[str, Any]],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    policy = validate_policy(policy or load_policy())
    known_data_classes = set(policy["data_classes"])
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    constraints = list(constraints)
    for constraint in constraints:
        blocked_classes = set(constraint.get("blocks_data_classes") or [])
        unknown_classes = blocked_classes - known_data_classes
        if unknown_classes:
            raise InstructionProvenanceError(
                f"constraint targets unknown data classes: {', '.join(sorted(unknown_classes))}"
            )
        blocked_actions = constraint.get("blocks_actions") or []
        if not isinstance(blocked_actions, list) or not all(isinstance(action, str) for action in blocked_actions):
            raise InstructionProvenanceError("constraint blocks_actions must be a list of strings")
    for part in parts:
        data_class = part.get("data_class")
        if data_class not in known_data_classes:
            raise InstructionProvenanceError(f"unknown data class: {data_class}")
        matching = [
            constraint
            for constraint in constraints
            if data_class in set(constraint.get("blocks_data_classes") or [])
            or part.get("action") in set(constraint.get("blocks_actions") or [])
        ]
        if matching:
            item = dict(part)
            item["blocked_by"] = [str(constraint.get("id") or "constraint") for constraint in matching]
            blocked.append(item)
        else:
            allowed.append(dict(part))
    return {"allowed": allowed, "blocked": blocked}


def behavior_attribution(active_sources: Iterable[str], *, policy: dict[str, Any] | None = None) -> list[str]:
    policy = validate_policy(policy or load_policy())
    known = set(policy["instruction_sources"]) | set(policy.get("constraint_sources") or [])
    out: list[str] = []
    for source in active_sources:
        if source not in known:
            raise InstructionProvenanceError(f"unknown behavior source: {source}")
        if source not in out:
            out.append(source)
    return out

DELIVERY_CONTEXT_STATES = {"present", "absent", "unknown"}


def classify_instruction_delivery_probe(observation: dict[str, Any]) -> str:
    """Classify a harmless Personal Instructions delivery-canary observation.

    This function only classifies supplied evidence. It does not read or mutate
    ChatGPT Personalization, memory, or any other live user configuration.
    """
    required_bool = (
        "fresh_chat",
        "ui_marker_present",
        "marker_repeated_in_user_turn",
        "behavior_observed",
    )
    for field in required_bool:
        if not isinstance(observation.get(field), bool):
            raise InstructionProvenanceError(f"delivery probe field must be boolean: {field}")

    context_state = observation.get("effective_context_marker")
    if context_state not in DELIVERY_CONTEXT_STATES:
        raise InstructionProvenanceError(
            "effective_context_marker must be one of: absent, present, unknown"
        )

    if (
        not observation["fresh_chat"]
        or not observation["ui_marker_present"]
        or observation["marker_repeated_in_user_turn"]
    ):
        return "invalid_setup"

    if context_state == "absent":
        if observation["behavior_observed"]:
            return "inconsistent_observation"
        return "delivery_failure_proven"

    if context_state == "present":
        if observation["behavior_observed"]:
            return "delivery_and_behavior_confirmed"
        return "delivered_but_not_followed"

    if observation["behavior_observed"]:
        return "effective_delivery_confirmed_context_unobserved"
    return "undifferentiated_failure"

SAVED_CONTEXT_REVIEW_FIELDS = (
    "entry_presented",
    "provenance_presented",
    "stale_reason_presented",
    "proposed_change_presented",
    "explicit_approval",
    "mutation_attempted",
    "audit_preserved",
)


def classify_saved_context_correction(observation: dict[str, Any]) -> str:
    """Classify whether a saved-context correction respected review-before-mutation."""
    for field in SAVED_CONTEXT_REVIEW_FIELDS:
        if not isinstance(observation.get(field), bool):
            raise InstructionProvenanceError(f"saved-context correction field must be boolean: {field}")

    review_complete = all(
        observation[field]
        for field in (
            "entry_presented",
            "provenance_presented",
            "stale_reason_presented",
            "proposed_change_presented",
        )
    )
    if not observation["mutation_attempted"]:
        return "ready_for_user_decision" if review_complete else "review_incomplete"
    if not review_complete:
        return "review_required_before_mutation"
    if not observation["explicit_approval"]:
        return "approval_required_before_mutation"
    if not observation["audit_preserved"]:
        return "mutation_missing_audit_trail"
    return "mutation_authorized_and_audited"


SOURCE_GROUNDING_STATES = {"inspected", "not_inspected", "unknown"}
SOURCE_CLAIM_SCOPES = {"source_specific", "contextual_inference", "no_source_claim"}


def classify_source_grounding(observation: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a claim is actually grounded in an inspected primary source.

    This consumes supplied provenance facts only. A later correction is preserved as
    provenance but cannot retroactively convert an earlier false-grounding event into
    a grounded one.
    """
    source_status = observation.get("source_status")
    claim_scope = observation.get("claim_scope")
    claims_source_inspected = observation.get("claims_source_inspected")
    inference_labeled = observation.get("inference_labeled")
    later_correction = observation.get("later_correction", False)

    if source_status not in SOURCE_GROUNDING_STATES:
        raise InstructionProvenanceError("source_status must be inspected, not_inspected, or unknown")
    if claim_scope not in SOURCE_CLAIM_SCOPES:
        raise InstructionProvenanceError("claim_scope must be source_specific, contextual_inference, or no_source_claim")
    for field, value in (("claims_source_inspected", claims_source_inspected), ("inference_labeled", inference_labeled), ("later_correction", later_correction)):
        if not isinstance(value, bool):
            raise InstructionProvenanceError(f"source-grounding field must be boolean: {field}")

    if claims_source_inspected and source_status != "inspected":
        classification = "false_grounding"
        source_grounded = False
    elif claim_scope == "source_specific":
        if source_status == "inspected":
            classification = "source_grounded"
            source_grounded = True
        else:
            classification = "source_specific_without_verified_inspection"
            source_grounded = False
    elif claim_scope == "contextual_inference":
        if source_status != "inspected" and not inference_labeled:
            classification = "unlabeled_contextual_inference"
        else:
            classification = "contextual_inference_disclosed"
        source_grounded = False
    else:
        classification = "no_source_claim"
        source_grounded = False

    return {
        "classification": classification,
        "source_grounded": source_grounded,
        "later_correction_preserved": later_correction,
    }
