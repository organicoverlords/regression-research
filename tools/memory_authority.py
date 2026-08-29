from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Iterable

try:
    from .memory_lifecycle import is_expired
    from .memory_classification import classify_entry
except ImportError:
    from memory_lifecycle import is_expired
    from memory_classification import classify_entry

USER_PREFIXES = ("user-instruction:",)
CANONICAL_PREFIXES = (
    "shared-policy:",
    "agents-policy:",
    "docs-policy:",
    "repo-policy:",
    "spec:",
)

ROLE_USER = "USER_EXPLICIT"
ROLE_CANONICAL = "CANONICAL_POLICY"
ROLE_ADVISORY = "ADVISORY_EVIDENCE"
ROLE_INACTIVE = "INACTIVE_HISTORY"
BEHAVIOR_RULE_KINDS = {"preference", "decision", "correction", "lesson"}
ROOT = Path(__file__).resolve().parents[1]
LEGACY_BEHAVIOR_TYPES = ROOT / "memory" / "behavior-rule-types.json"
AUTHORITY_REGISTRY = ROOT / "memory" / "behavior-authority-registry.json"
_ACTIVE_AUTHORITY_REGISTRY = AUTHORITY_REGISTRY


def _load_legacy_behavior_rule_ids() -> frozenset[str]:
    try:
        payload = json.loads(LEGACY_BEHAVIOR_TYPES.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    ids = payload.get("behavior_rule_ids", []) if isinstance(payload, dict) else []
    return frozenset(item for item in ids if isinstance(item, str) and item.strip())


LEGACY_BEHAVIOR_RULE_IDS = _load_legacy_behavior_rule_ids()


def _load_authority_registry(path: Path | None = None) -> tuple[frozenset[str], frozenset[str]]:
    target = Path(path or _ACTIVE_AUTHORITY_REGISTRY)
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return frozenset(), frozenset()
    if not isinstance(payload, dict):
        return frozenset(), frozenset()
    users = payload.get("user_explicit_ids", [])
    policies = payload.get("canonical_policy_ids", [])
    return (
        frozenset(item for item in users if isinstance(item, str) and item.strip()),
        frozenset(item for item in policies if isinstance(item, str) and item.strip()),
    )


VERIFIED_USER_AUTHORITY_IDS, VERIFIED_CANONICAL_AUTHORITY_IDS = _load_authority_registry()


def configure_authority_registry(path: Path | None = None) -> Path:
    """Select and reload the registry used by authority classification in this process."""
    global _ACTIVE_AUTHORITY_REGISTRY, VERIFIED_USER_AUTHORITY_IDS, VERIFIED_CANONICAL_AUTHORITY_IDS
    _ACTIVE_AUTHORITY_REGISTRY = Path(path or AUTHORITY_REGISTRY).resolve()
    VERIFIED_USER_AUTHORITY_IDS, VERIFIED_CANONICAL_AUTHORITY_IDS = _load_authority_registry(_ACTIVE_AUTHORITY_REGISTRY)
    return _ACTIVE_AUTHORITY_REGISTRY


def authority_registry_payload(path: Path | None = None) -> dict[str, Any]:
    target = Path(path or _ACTIVE_AUTHORITY_REGISTRY)
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"authority registry is unreadable: {target}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("authority registry schema_version must be 1")
    for key in ("user_explicit_ids", "canonical_policy_ids"):
        values = payload.get(key)
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError(f"authority registry {key} must be an array of non-empty strings")
        if len(values) != len(set(values)):
            raise ValueError(f"authority registry {key} contains duplicate ids")
    return payload


def _write_authority_registry_local(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".curate-tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temp, path)


def authority_curation_errors(entry: dict[str, Any], role: str) -> list[str]:
    errors: list[str] = []
    ident = str(entry.get("id") or "")
    if role == ROLE_USER:
        if entry.get("state") == "REJECTED":
            errors.append("rejected records cannot be promoted")
        if entry.get("behavior_rule") is not True:
            errors.append("behavior_rule must be true")
        if str(entry.get("kind") or "") not in BEHAVIOR_RULE_KINDS:
            errors.append("kind is not valid for a behavior rule")
        if not _evidence_has_prefix(entry, USER_PREFIXES):
            errors.append("user-instruction provenance is required")
        tags = {str(tag) for tag in entry.get("tags", [])}
        if not {"assistant-recorded", "verbatim-source"}.issubset(tags):
            errors.append("trusted promotion requires assistant-recorded verbatim provenance")
        source_messages = entry.get("source_messages")
        if not isinstance(source_messages, list) or not source_messages or any(not isinstance(item, str) or not item.strip() for item in source_messages):
            errors.append("trusted promotion requires non-empty source_messages")
    elif role == ROLE_CANONICAL:
        if entry.get("state") != "PROVEN":
            errors.append("canonical policy must be PROVEN")
        if not _evidence_has_prefix(entry, CANONICAL_PREFIXES):
            errors.append("canonical policy provenance is required")
    else:
        errors.append(f"unsupported authority role: {role}")
    if not ident:
        errors.append("memory id is required")
    return errors


def curate_authority_registry_local(
    entries: Iterable[dict[str, Any]], memory_id: str, role: str, *, path: Path | None = None
) -> dict[str, Any]:
    target = Path(path or _ACTIVE_AUTHORITY_REGISTRY)
    by_id = {str(entry.get("id")): entry for entry in entries}
    entry = by_id.get(memory_id)
    if entry is None:
        raise ValueError(f"memory id not found: {memory_id}")
    errors = authority_curation_errors(entry, role)
    if errors:
        raise ValueError("; ".join(errors))
    payload = authority_registry_payload(target)
    user_ids = set(payload["user_explicit_ids"] )
    policy_ids = set(payload["canonical_policy_ids"] )
    if role == ROLE_USER:
        if memory_id in policy_ids:
            raise ValueError("memory id is already curated as canonical policy")
        user_ids.add(memory_id)
    else:
        if memory_id in user_ids:
            raise ValueError("memory id is already curated as explicit user behavior")
        policy_ids.add(memory_id)
    payload["user_explicit_ids"] = sorted(user_ids)
    payload["canonical_policy_ids"] = sorted(policy_ids)
    _write_authority_registry_local(target, payload)
    configure_authority_registry(target)
    return payload


def validate_authority_registry(entries: Iterable[dict[str, Any]], *, path: Path | None = None) -> dict[str, Any]:
    target = Path(path or _ACTIVE_AUTHORITY_REGISTRY)
    try:
        payload = authority_registry_payload(target)
    except ValueError as exc:
        return {"status": "REJECTED", "errors": [str(exc)], "user_ids": 0, "policy_ids": 0}
    items = list(entries)
    by_id = {str(entry.get("id")): entry for entry in items}
    errors: list[str] = []
    user_ids = list(payload["user_explicit_ids"] )
    policy_ids = list(payload["canonical_policy_ids"] )
    overlap = sorted(set(user_ids) & set(policy_ids))
    if overlap:
        errors.append("ids present in both authority roles: " + ", ".join(overlap))
    for ident in user_ids:
        entry = by_id.get(ident)
        if entry is None:
            errors.append(f"user authority id missing from bank: {ident}")
            continue
        if not _evidence_has_prefix(entry, USER_PREFIXES):
            errors.append(f"user authority id lacks user provenance: {ident}")
        if str(entry.get("kind") or "") not in BEHAVIOR_RULE_KINDS:
            errors.append(f"user authority id has invalid kind: {ident}")
        if entry.get("behavior_rule") is not True and ident not in LEGACY_BEHAVIOR_RULE_IDS:
            errors.append(f"user authority id lacks behavior type: {ident}")
    for ident in policy_ids:
        entry = by_id.get(ident)
        if entry is None:
            errors.append(f"canonical policy id missing from bank: {ident}")
            continue
        if entry.get("state") != "PROVEN":
            errors.append(f"canonical policy id is not PROVEN: {ident}")
        if not _evidence_has_prefix(entry, CANONICAL_PREFIXES):
            errors.append(f"canonical policy id lacks canonical provenance: {ident}")
    typed_uncurated = sorted(
        str(entry.get("id")) for entry in current_entries(items)
        if entry.get("behavior_rule") is True
        and _evidence_has_prefix(entry, USER_PREFIXES)
        and str(entry.get("id")) not in set(user_ids)
    )
    if typed_uncurated:
        errors.append("current typed user behavior rules are uncurated: " + ", ".join(typed_uncurated))
    return {
        "status": "PROVEN" if not errors else "REJECTED",
        "errors": errors,
        "user_ids": len(user_ids),
        "policy_ids": len(policy_ids),
        "typed_uncurated": typed_uncurated,
    }


def _evidence_has_prefix(entry: dict[str, Any], prefixes: tuple[str, ...]) -> bool:
    return any(
        isinstance(item, str) and item.startswith(prefixes)
        for item in entry.get("evidence", [])
    )


def behavioral_authority(entry: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a stored memory may alter behavior.

    This is intentionally independent from retrieval relevance and factual confidence.
    User provenance authorizes behavior only; it does not prove hidden external causes.
    """
    state = str(entry.get("state") or "")
    if state == "REJECTED":
        return {
            "role": ROLE_INACTIVE,
            "may_change_behavior": False,
            "precedence": 0,
            "basis": "rejected",
            "authority_scope": "none",
        }
    has_user_provenance = _evidence_has_prefix(entry, USER_PREFIXES)
    explicit_behavior_type = entry.get("behavior_rule") is True
    legacy_behavior_type = str(entry.get("id") or "") in LEGACY_BEHAVIOR_RULE_IDS
    is_behavior_rule = explicit_behavior_type or legacy_behavior_type

    if has_user_provenance:
        if not is_behavior_rule:
            return {
                "role": ROLE_ADVISORY,
                "may_change_behavior": False,
                "precedence": 0,
                "basis": "user_provenance_without_behavior_rule_type",
                "authority_scope": "evidence_only",
                "claim_state": state,
            }
        if str(entry.get("kind") or "") not in BEHAVIOR_RULE_KINDS:
            return {
                "role": ROLE_ADVISORY,
                "may_change_behavior": False,
                "precedence": 0,
                "basis": "behavior_rule_type_invalid_for_kind",
                "authority_scope": "evidence_only",
                "claim_state": state,
            }
        if str(entry.get("id") or "") not in VERIFIED_USER_AUTHORITY_IDS:
            return {
                "role": ROLE_ADVISORY,
                "may_change_behavior": False,
                "precedence": 0,
                "basis": "user_behavior_authority_not_curated",
                "authority_scope": "evidence_only",
                "claim_state": state,
            }
        return {
            "role": ROLE_USER,
            "may_change_behavior": True,
            "precedence": 100,
            "basis": "explicit_behavior_rule_type" if explicit_behavior_type else "legacy_behavior_rule_type_registry",
            "authority_scope": "behavior_only",
            "claim_state": state,
        }
    if state != "PROVEN":
        return {
            "role": ROLE_ADVISORY,
            "may_change_behavior": False,
            "precedence": 0,
            "basis": "state_not_proven",
            "authority_scope": "evidence_only",
        }
    if _evidence_has_prefix(entry, CANONICAL_PREFIXES):
        if str(entry.get("id") or "") not in VERIFIED_CANONICAL_AUTHORITY_IDS:
            return {
                "role": ROLE_ADVISORY,
                "may_change_behavior": False,
                "precedence": 0,
                "basis": "canonical_policy_authority_not_curated",
                "authority_scope": "evidence_only",
            }
        return {
            "role": ROLE_CANONICAL,
            "may_change_behavior": True,
            "precedence": 90,
            "basis": "live_canonical_policy",
            "authority_scope": "behavior_only",
        }
    return {
        "role": ROLE_ADVISORY,
        "may_change_behavior": False,
        "precedence": 0,
        "basis": "no_behavioral_authority_provenance",
        "authority_scope": "evidence_only",
    }


def annotate_memory(entry: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(entry)
    annotated["behavioral_authority"] = behavioral_authority(entry)
    annotated["classification"] = classify_entry(entry)
    return annotated


def current_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    items = list(entries)
    superseded = {old for entry in items for old in entry.get("supersedes", [])}
    return [
        entry for entry in items
        if entry.get("state") != "REJECTED"
        and entry.get("id") not in superseded
        and not is_expired(entry)
        and classify_entry(entry)["sensitivity"] != "EXCLUDE"
        and classify_entry(entry)["durability"] not in {"EPHEMERAL", "HISTORICAL"}
    ]


def behavioral_context(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only current memories allowed to alter behavior.

    Relevance must be applied separately. This function is the policy firewall.
    """
    selected: list[tuple[int, datetime, str, dict[str, Any]]] = []
    for entry in current_entries(entries):
        authority = behavioral_authority(entry)
        if not authority["may_change_behavior"]:
            continue
        stamp = datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "+00:00"))
        selected.append((
            int(authority["precedence"]),
            stamp,
            str(entry.get("id") or ""),
            annotate_memory(entry),
        ))
    selected.sort(key=lambda item: (-item[0], -item[1].timestamp(), item[2]))
    return [entry for _, _, _, entry in selected]
