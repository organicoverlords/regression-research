from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

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
BEHAVIOR_KINDS = {"preference", "decision", "correction"}


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
    if str(entry.get("kind") or "") not in BEHAVIOR_KINDS:
        return {
            "role": ROLE_ADVISORY,
            "may_change_behavior": False,
            "precedence": 0,
            "basis": "kind_not_behavioral",
            "authority_scope": "evidence_only",
        }
    if _evidence_has_prefix(entry, USER_PREFIXES):
        return {
            "role": ROLE_USER,
            "may_change_behavior": True,
            "precedence": 100,
            "basis": "explicit_user_instruction",
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
    return annotated


def current_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    items = list(entries)
    superseded = {old for entry in items for old in entry.get("supersedes", [])}
    return [
        entry for entry in items
        if entry.get("state") != "REJECTED" and entry.get("id") not in superseded
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
