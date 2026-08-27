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
