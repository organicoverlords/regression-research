from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "tests" / "fixtures" / "busy-ownership-policy.json"


class BusyAuthorityError(ValueError):
    pass


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if policy.get("schema_version") != "1.0":
        raise BusyAuthorityError("unsupported BUSY ownership schema")
    if policy.get("live_authority") != "standalone_busy_coordinator":
        raise BusyAuthorityError("standalone BusyCoordinator must be the live authority")
    projections = policy.get("projection_surfaces")
    if not isinstance(projections, list) or not projections:
        raise BusyAuthorityError("projection surfaces are required")
    invariants = policy.get("invariants")
    required = {
        "one_live_authority",
        "projection_never_creates_ownership",
        "stale_projection_non_blocking",
        "read_only_requires_claim",
        "shared_mutation_requires_exact_live_claim",
        "other_owner_claim_requires_yield",
        "coordination_outage_creates_no_fallback_authority",
        "read_only_and_independent_work_continue_during_coordination_outage",
        "ownership_claim_never_proves_worker_execution",
    }
    if not isinstance(invariants, dict) or required - set(invariants):
        raise BusyAuthorityError("missing BUSY invariants")
    for name in required - {"read_only_requires_claim"}:
        if invariants[name] is not True:
            raise BusyAuthorityError(f"{name} must be true")
    if invariants["read_only_requires_claim"] is not False:
        raise BusyAuthorityError("read-only work must not require a claim")
    return policy


def resolve_scope(
    scope: str,
    live_claims: Iterable[dict[str, Any]],
    projections: Iterable[dict[str, Any]] = (),
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = validate_policy(policy or load_policy())
    claims = [
        claim for claim in live_claims
        if claim.get("scope") == scope and claim.get("live") is True
    ]
    if len(claims) > 1:
        raise BusyAuthorityError(f"multiple live claims for exact scope: {scope}")

    matching_projections = [projection for projection in projections if projection.get("scope") == scope]
    if claims:
        claim = claims[0]
        owner = claim.get("owner")
        if not isinstance(owner, str) or not owner:
            raise BusyAuthorityError("live claim missing owner")
        consistent = [p for p in matching_projections if p.get("owner") == owner]
        stale = [p for p in matching_projections if p.get("owner") != owner]
        return {
            "state": "owned",
            "scope": scope,
            "owner": owner,
            "authority": policy["live_authority"],
            "authority_scope": "ownership_only",
            "proves_worker_execution": False,
            "consistent_projections": consistent,
            "stale_projections": stale,
        }

    return {
        "state": "unclaimed",
        "scope": scope,
        "owner": None,
        "authority": policy["live_authority"],
        "authority_scope": "ownership_only",
        "proves_worker_execution": False,
        "consistent_projections": [],
        "stale_projections": matching_projections,
    }


def admit_operation(
    actor: str,
    scope: str,
    operation: str,
    live_claims: Iterable[dict[str, Any]],
    projections: Iterable[dict[str, Any]] = (),
    *,
    coordination_available: bool = True,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = validate_policy(policy or load_policy())
    if operation not in {"read_only", "substantive_investigation", "independent_mutation", "shared_mutation"}:
        raise BusyAuthorityError(f"unknown operation: {operation}")

    if operation in {"read_only", "substantive_investigation", "independent_mutation"}:
        return {
            "decision": "allow",
            "reason": "claim_not_required",
            "scope": scope,
            "operation": operation,
        }

    if not coordination_available:
        return {
            "decision": "defer_shared_mutation",
            "reason": "coordination_unavailable_no_fallback_authority",
            "scope": scope,
            "operation": operation,
        }

    state = resolve_scope(scope, live_claims, projections, policy=policy)
    if state["state"] == "unclaimed":
        return {
            "decision": "claim_required",
            "reason": "shared_scope_unclaimed",
            "scope": scope,
            "operation": operation,
            "stale_projections": state["stale_projections"],
        }
    if state["owner"] == actor:
        return {
            "decision": "allow",
            "reason": "actor_holds_exact_live_claim",
            "scope": scope,
            "operation": operation,
        }
    return {
        "decision": "yield",
        "reason": "another_actor_holds_exact_live_claim",
        "scope": scope,
        "operation": operation,
        "owner": state["owner"],
    }
