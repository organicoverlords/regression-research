from __future__ import annotations

from typing import Any, Iterable

from tools.busy_authority import admit_operation
from tools.capability_routing import load_policy as load_capability_policy
from tools.capability_routing import select_adapter, validate_policy as validate_capability_policy
from tools.instruction_provenance import partition_request, resolve_directive


class StackAcceptanceError(ValueError):
    pass


def _part_outcome(
    part: dict[str, Any],
    *,
    actor: str,
    available_roles: dict[str, list[str]],
    failed_roles: dict[str, list[str]],
    role_providers: dict[str, dict[str, list[str]]],
    live_claims: Iterable[dict[str, Any]],
    projections: Iterable[dict[str, Any]],
    coordination_available: bool,
    explicit_user_authorization: bool,
    capability_policy: dict[str, Any],
) -> dict[str, Any]:
    capability = part.get("capability")
    operation = part.get("operation")
    scope = part.get("scope")
    if not all(isinstance(value, str) and value for value in (capability, operation, scope)):
        raise StackAcceptanceError(f"part {part.get('id', '<unknown>')} missing capability/operation/scope")

    if capability == "memory_write":
        required = capability_policy["capabilities"]["memory_write"].get("requires")
        if required == "explicit_user_authorization" and not explicit_user_authorization:
            return {
                "id": part.get("id"),
                "disposition": "authorization_required",
                "capability": capability,
                "operation": operation,
                "scope": scope,
                "route": None,
                "ownership": None,
            }

    route = select_adapter(
        capability,
        available_roles.get(capability, []),
        failed_roles=failed_roles.get(capability, []),
        role_providers=role_providers.get(capability, {}),
        policy=capability_policy,
    )
    if route["status"] != "selected":
        return {
            "id": part.get("id"),
            "disposition": "degraded",
            "capability": capability,
            "operation": operation,
            "scope": scope,
            "route": route,
            "ownership": None,
        }

    ownership = admit_operation(
        actor,
        scope,
        operation,
        live_claims,
        projections,
        coordination_available=coordination_available,
    )
    disposition_by_decision = {
        "allow": "execute",
        "defer_shared_mutation": "defer_shared_mutation",
        "claim_required": "claim_required",
        "yield": "yield",
    }
    decision = ownership.get("decision")
    if decision not in disposition_by_decision:
        raise StackAcceptanceError(f"unknown ownership decision: {decision}")
    return {
        "id": part.get("id"),
        "disposition": disposition_by_decision[decision],
        "capability": capability,
        "operation": operation,
        "scope": scope,
        "route": route,
        "ownership": ownership,
    }


_RETRYABLE_WORK_DISPOSITIONS = {
    "yield",
    "defer_shared_mutation",
    "degraded",
    "authorization_required",
}


def _plan_work_cycle(allowed_outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    execute_now = [item["id"] for item in allowed_outcomes if item["disposition"] == "execute"]
    claim_now = [item["id"] for item in allowed_outcomes if item["disposition"] == "claim_required"]
    queued = [
        item["id"]
        for item in allowed_outcomes
        if item["disposition"] in _RETRYABLE_WORK_DISPOSITIONS
    ]

    if execute_now:
        action = "execute_available"
    elif claim_now:
        action = "claim_then_execute"
    elif queued:
        action = "redirect_to_next_job"
    else:
        action = "no_runnable_work"

    return {
        "action": action,
        "execute_now": execute_now,
        "claim_now": claim_now,
        "queued": queued,
        "redirect_after_current": bool(queued and (execute_now or claim_now)),
    }


def plan_request(
    *,
    actor: str,
    directives: Iterable[dict[str, Any]],
    parts: Iterable[dict[str, Any]],
    constraints: Iterable[dict[str, Any]] = (),
    available_roles: dict[str, list[str]] | None = None,
    failed_roles: dict[str, list[str]] | None = None,
    role_providers: dict[str, dict[str, list[str]]] | None = None,
    live_claims: Iterable[dict[str, Any]] = (),
    projections: Iterable[dict[str, Any]] = (),
    coordination_available: bool = True,
    explicit_user_authorization: bool = False,
) -> dict[str, Any]:
    if not isinstance(actor, str) or not actor:
        raise StackAcceptanceError("actor is required")

    directives = list(directives)
    parts = list(parts)
    constraints = list(constraints)
    live_claims = list(live_claims)
    projections = list(projections)
    available_roles = dict(available_roles or {})
    failed_roles = dict(failed_roles or {})
    role_providers = dict(role_providers or {})

    current_directive = resolve_directive(directives)
    partition = partition_request(parts, constraints)
    capability_policy = validate_capability_policy(load_capability_policy())

    allowed_outcomes = [
        _part_outcome(
            part,
            actor=actor,
            available_roles=available_roles,
            failed_roles=failed_roles,
            role_providers=role_providers,
            live_claims=live_claims,
            projections=projections,
            coordination_available=coordination_available,
            explicit_user_authorization=explicit_user_authorization,
            capability_policy=capability_policy,
        )
        for part in partition["allowed"]
    ]
    blocked_outcomes = [
        {
            "id": part.get("id"),
            "disposition": "blocked",
            "blocked_by": list(part.get("blocked_by") or []),
        }
        for part in partition["blocked"]
    ]

    dispositions = [item["disposition"] for item in allowed_outcomes]
    if allowed_outcomes and all(value == "execute" for value in dispositions) and not blocked_outcomes:
        overall = "execute_all"
    elif "execute" in dispositions:
        overall = "partial_progress"
    elif allowed_outcomes:
        overall = "degraded_without_total_refusal"
    else:
        overall = "blocked_all" if blocked_outcomes else "no_work"

    return {
        "current_directive": current_directive,
        "allowed": allowed_outcomes,
        "blocked": blocked_outcomes,
        "overall": overall,
        "work_cycle": _plan_work_cycle(allowed_outcomes),
    }
