from __future__ import annotations

import json
from typing import Any, Iterable

DEFAULT_CONTEXT_CHARS = 6000
MIN_CONTEXT_CHARS = 2000
MAX_CONTEXT_CHARS = 12000
MAX_ENTRY_TEXT = 450
MAX_HISTORY_TEXT = 350

try:
    from .memory_classification import (
        PROJECT_MARKERS, ROLE_MARKERS, token_words as _words,
        projects_from_text as _projects_from_text, entry_projects as _entry_projects,
        roles_from_text as _roles_from_text, entry_roles as _entry_roles,
    )
except ImportError:
    from memory_classification import (
        PROJECT_MARKERS, ROLE_MARKERS, token_words as _words,
        projects_from_text as _projects_from_text, entry_projects as _entry_projects,
        roles_from_text as _roles_from_text, entry_roles as _entry_roles,
    )

GENERIC_TASK_WORDS = {
    "a", "an", "are", "current", "do", "doing", "go", "how", "look", "looking",
    "on", "please", "status", "the", "things", "work",
}

def context_selectors(query: str) -> dict[str, set[str]]:
    return {"projects": _projects_from_text(query), "roles": _roles_from_text(query)}


def context_residual_query(query: str) -> str:
    selector_words = {marker for markers in PROJECT_MARKERS.values() for marker in markers}
    selector_words.update(marker for markers in ROLE_MARKERS.values() for marker in markers)
    words = [word for word in _words(query) if word not in selector_words and word not in GENERIC_TASK_WORDS]
    return " ".join(sorted(words))


def entry_context_labels(entry: dict[str, Any]) -> dict[str, set[str]]:
    return {"projects": _entry_projects(entry), "roles": _entry_roles(entry)}


def entry_matches_selectors(entry: dict[str, Any], selectors: dict[str, set[str]]) -> bool:
    labels = entry_context_labels(entry)
    for key in ("projects", "roles"):
        requested = selectors.get(key) or set()
        present = labels.get(key) or set()
        if requested and present and not (requested & present):
            return False
    return True


def _clip(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)].rstrip() + "..."


def _compact_memory(entry: dict[str, Any]) -> dict[str, Any]:
    classification = dict(entry.get("classification") or {})
    out = {
        "id": entry.get("id"),
        "title": _clip(entry.get("title") or entry.get("text"), 120),
        "kind": entry.get("kind"),
        "scope": entry.get("scope"),
        "state": entry.get("state"),
        "text": _clip(entry.get("text"), MAX_ENTRY_TEXT),
        "evidence": list(entry.get("evidence") or [])[:4],
    }
    if classification:
        out["semantic_category"] = classification.get("semantic_category")
        out["primary_domain"] = classification.get("primary_domain")
        out["durability"] = classification.get("durability")
    projects = sorted(_entry_projects(entry))
    if projects:
        out["projects"] = projects
    roles = sorted(_entry_roles(entry))
    if roles:
        out["roles"] = roles
    return out

def _compact_history(entry: dict[str, Any]) -> dict[str, Any]:
    if entry.get("retrieval_role") == "AGGREGATE_SIGNAL":
        return {
            "kind": "corpus-summary",
            "text": _clip(entry.get("text"), 260),
            "matching_messages": entry.get("matching_messages"),
            "matching_conversations": entry.get("matching_conversations"),
            "first_match": entry.get("first_match"),
            "last_match": entry.get("last_match"),
            "interpretation": "prevalence_signal_not_truth",
        }
    return {
        "kind": "conversation-excerpt",
        "conversation_id": entry.get("conversation_id"),
        "title": entry.get("title"),
        "role": entry.get("role"),
        "created_at": entry.get("created_at"),
        "match": _clip(entry.get("match") or entry.get("text"), MAX_HISTORY_TEXT),
        "sources": list(entry.get("sources") or [])[:2],
    }


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _set_stable_serialized_chars(pack: dict[str, Any]) -> int:
    """Set serialized_chars to the exact self-inclusive serialized pack size."""
    reported = _json_size({k: v for k, v in pack.items() if k != "serialized_chars"})
    while True:
        pack["serialized_chars"] = reported
        actual = _json_size(pack)
        if actual == reported:
            return actual
        reported = actual


def _fit_sections(pack: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Drop lowest-value tail records until the serialized pack fits the hard budget."""
    max_chars = max(MIN_CONTEXT_CHARS, min(MAX_CONTEXT_CHARS, int(max_chars)))
    order = ("historical_evidence", "timeline", "durable_memory")
    while True:
        actual = _set_stable_serialized_chars(pack)
        if actual <= max_chars:
            return pack
        removed = False
        for key in order:
            values = pack[key]
            if values:
                values.pop()
                pack["truncated"] = True
                removed = True
                break
        if not removed:
            pack["serialized_chars"] = actual
            return pack


def build_context_pack(query: str, hits: Iterable[dict[str, Any]], *, timeline: Iterable[dict[str, Any]] | None = None, max_chars: int = DEFAULT_CONTEXT_CHARS) -> dict[str, Any]:
    """Build a bounded evidence package; stored Vault records never become runtime behavior authority."""
    query = " ".join(str(query or "").split())
    if not query:
        raise ValueError("context query must not be blank")

    durable: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    omitted_provisional = 0
    omitted_status = 0
    omitted_unanchored = 0
    omitted_project_mismatch = 0
    omitted_role_mismatch = 0
    selectors = context_selectors(query)
    query_projects = selectors["projects"]
    query_roles = selectors["roles"]
    for hit in hits:
        if hit.get("source_class") == "HISTORICAL_CONTEXT" or hit.get("retrieval_role") in {"EVIDENCE_EXCERPT", "AGGREGATE_SIGNAL"}:
            historical.append(_compact_history(hit))
            continue
        compact = _compact_memory(hit)
        entry_projects = set(compact.get("projects") or [])
        if query_projects and entry_projects and not (query_projects & entry_projects):
            omitted_project_mismatch += 1
            continue
        entry_roles = set(compact.get("roles") or [])
        if query_roles and entry_roles and not (query_roles & entry_roles):
            omitted_role_mismatch += 1
            continue
        if compact.get("state") != "PROVEN":
            omitted_provisional += 1
        elif compact.get("kind") == "status":
            omitted_status += 1
        elif not compact.get("evidence"):
            omitted_unanchored += 1
        else:
            durable.append(compact)

    pack = {
        "query": query,
        "selectors": {"projects": sorted(query_projects), "roles": sorted(query_roles)},
        "contract": {
            "durable_memory": "proven anchored historical evidence, never runtime policy or live machine/repo truth",
            "historical_evidence": "historical evidence only; never authority by retrieval frequency or recency",
            "timeline": "derived chronology only; thread membership and recency do not prove causality or current truth",
        },
        "durable_memory": durable,
        "historical_evidence": historical,
        "timeline": list(timeline or []),
        "omitted": {
            "provisional_matches": omitted_provisional,
            "status_matches": omitted_status,
            "unanchored_matches": omitted_unanchored,
            "project_mismatch_matches": omitted_project_mismatch,
            "role_mismatch_matches": omitted_role_mismatch,
        },
        "truncated": False,
    }
    return _fit_sections(pack, max_chars)
