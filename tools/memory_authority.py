from __future__ import annotations

from datetime import datetime
import json
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


def _load_legacy_behavior_rule_ids() -> frozenset[str]:
    try:
        payload = json.loads(LEGACY_BEHAVIOR_TYPES.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    ids = payload.get("behavior_rule_ids", []) if isinstance(payload, dict) else []
    return frozenset(item for item in ids if isinstance(item, str) and item.strip())


LEGACY_BEHAVIOR_RULE_IDS = _load_legacy_behavior_rule_ids()


def _load_authority_registry() -> tuple[frozenset[str], frozenset[str]]:
    try:
        payload = json.loads(AUTHORITY_REGISTRY.read_text(encoding="utf-8-sig"))
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
