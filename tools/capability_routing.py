from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "tests" / "fixtures" / "capability-routing-policy.json"
REQUIRED_CAPABILITIES = {
    "coordination",
    "source_read",
    "repository_mutate",
    "runtime_validate",
    "connected_account_action",
    "artifact_create",
    "schedule",
    "memory_read",
    "memory_write",
}
FORBIDDEN_PROVIDER_TOKENS = {
    "github",
    "mcp",
    "chatgpt",
    "opencode",
    "claude",
    "codex",
    "traycer",
    "command-code",
}


class CapabilityRoutingError(ValueError):
    pass


def load_policy(path: Path = DEFAULT_POLICY) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if policy.get("schema_version") != "1.0":
        raise CapabilityRoutingError("unsupported capability-routing schema")
    invariants = policy.get("invariants")
    capabilities = policy.get("capabilities")
    if not isinstance(invariants, dict) or not isinstance(capabilities, dict):
        raise CapabilityRoutingError("policy must contain invariants and capabilities")
    missing = REQUIRED_CAPABILITIES - set(capabilities)
    if missing:
        raise CapabilityRoutingError(f"missing capabilities: {', '.join(sorted(missing))}")
    if invariants.get("failure_scope") != "capability_local":
        raise CapabilityRoutingError("route failures must stay capability-local")
    if invariants.get("transport_is_not_permission") is not True:
        raise CapabilityRoutingError("transport must not be treated as permission")
    if invariants.get("duplicate_authority_forbidden") is not True:
        raise CapabilityRoutingError("duplicate authority must be forbidden")
    if invariants.get("unrelated_capabilities_continue") is not True:
        raise CapabilityRoutingError("unrelated capabilities must continue")
    if invariants.get("visible_surface_is_not_capability_boundary") is not True:
        raise CapabilityRoutingError("visible tool surface must not define capability availability")

    for name, capability in capabilities.items():
        roles = capability.get("ordered_adapter_roles")
        if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or not role for role in roles):
            raise CapabilityRoutingError(f"{name}: ordered_adapter_roles must be a non-empty string list")
        if len(set(roles)) != len(roles):
            raise CapabilityRoutingError(f"{name}: duplicate adapter role")
        if not isinstance(capability.get("when_unavailable"), str) or not capability["when_unavailable"]:
            raise CapabilityRoutingError(f"{name}: when_unavailable is required")
        if capability.get("fallback_mode") not in {"ordered_supported_fallback", "none", "no_second_authority"}:
            raise CapabilityRoutingError(f"{name}: invalid fallback_mode")
        for role in roles:
            lowered = role.casefold()
            if any(token in lowered for token in FORBIDDEN_PROVIDER_TOKENS):
                raise CapabilityRoutingError(f"{name}: provider/tool name leaked into core routing role: {role}")

    coordination = capabilities["coordination"]
    if coordination.get("fallback_mode") != "no_second_authority" or coordination["ordered_adapter_roles"] != ["live_ownership"]:
        raise CapabilityRoutingError("coordination must have exactly one authority and no authority fallback")
    if capabilities["memory_read"].get("side_effects") != "forbidden":
        raise CapabilityRoutingError("memory reads must be side-effect free")
    if capabilities["memory_write"].get("requires") != "explicit_user_authorization":
        raise CapabilityRoutingError("memory writes must require explicit user authorization")
    return policy


def _normalize_role_iterable(roles: Iterable[str], *, label: str) -> list[str]:
    if isinstance(roles, (str, bytes)):
        raise CapabilityRoutingError(f"{label} must be an iterable of role strings, not a string")
    normalized = list(roles)
    if any(not isinstance(role, str) or not role for role in normalized):
        raise CapabilityRoutingError(f"{label} must contain only non-empty strings")
    return normalized


def resolve_reachable_roles(
    available_roles: Iterable[str],
    *,
    role_providers: Mapping[str, Iterable[str]] | None = None,
    failed_roles: Iterable[str] = (),
) -> set[str]:
    failed = set(_normalize_role_iterable(failed_roles, label="failed_roles"))
    available = _normalize_role_iterable(available_roles, label="available_roles")
    reachable = {role for role in available if role not in failed}

    providers: dict[str, list[str]] = {}
    for provider, provided_roles in (role_providers or {}).items():
        if not isinstance(provider, str) or not provider:
            raise CapabilityRoutingError("role provider names must be non-empty strings")
        providers[provider] = _normalize_role_iterable(
            provided_roles,
            label=f"{provider}: provided roles",
        )

    changed = True
    while changed:
        changed = False
        for provider, provided_roles in providers.items():
            if provider not in reachable:
                continue
            for role in provided_roles:
                if role in failed or role in reachable:
                    continue
                reachable.add(role)
                changed = True
    return reachable


def select_adapter(
    capability: str,
    available_roles: Iterable[str],
    *,
    failed_roles: Iterable[str] = (),
    role_providers: Mapping[str, Iterable[str]] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = validate_policy(policy or load_policy())
    capabilities = policy["capabilities"]
    if capability not in capabilities:
        raise CapabilityRoutingError(f"unknown capability: {capability}")
    failed = set(_normalize_role_iterable(failed_roles, label="failed_roles"))
    available = resolve_reachable_roles(
        available_roles,
        role_providers=role_providers,
        failed_roles=failed,
    )
    spec = capabilities[capability]
    for role in spec["ordered_adapter_roles"]:
        if role in available and role not in failed:
            return {
                "status": "selected",
                "capability": capability,
                "adapter_role": role,
                "failure_scope": "capability_local",
            }
    return {
        "status": "degraded",
        "capability": capability,
        "adapter_role": None,
        "failure_scope": "capability_local",
        "next_action": spec["when_unavailable"],
        "fallback_mode": spec["fallback_mode"],
    }
