from __future__ import annotations

import json
from typing import Any, Iterable

DEFAULT_CONTEXT_CHARS = 6000
MIN_CONTEXT_CHARS = 2000
MAX_CONTEXT_CHARS = 12000
MAX_ENTRY_TEXT = 450
MAX_HISTORY_TEXT = 350

PROJECT_MARKERS = {
    "p3": ("p3",),
    "tiny3d": ("tiny3d",),
    "lowvram": ("lowvram", "lowvram3d"),
}
ROLE_MARKERS = {
    "orchestrator": ("orchestrator",),
    "worker": ("worker", "workers"),
}
GENERIC_TASK_WORDS = {
    "a", "an", "are", "current", "do", "doing", "go", "how", "look", "looking",
    "on", "please", "status", "the", "things", "work",
}


def _words(value: Any) -> set[str]:
    import re
    return set(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _projects_from_text(value: Any) -> set[str]:
    words = _words(value)
    found: set[str] = set()
    for project, markers in PROJECT_MARKERS.items():
        if any(marker in words for marker in markers):
            found.add(project)
    return found


def _entry_projects(entry: dict[str, Any]) -> set[str]:
    explicit = str(entry.get("project") or "").strip().casefold()
    if explicit:
        return {explicit}
    # Infer project only from descriptors. Body text can mention another project as
    # an example and must not silently re-scope a global rule.
    fields = [entry.get("scope"), entry.get("title"), *(entry.get("tags") or [])]
    found: set[str] = set()
    for field in fields:
        found.update(_projects_from_text(field))
    return found


def _roles_from_text(value: Any) -> set[str]:
    words = _words(value)
    found: set[str] = set()
    for role, markers in ROLE_MARKERS.items():
        if any(marker in words for marker in markers):
            found.add(role)
    return found


def _entry_roles(entry: dict[str, Any]) -> set[str]:
    # Restrict role inference to descriptors, not the memory body. Incident bodies
    # often mention both actors and would otherwise over-classify everything.
    fields = [entry.get("scope"), entry.get("title"), *(entry.get("tags") or [])]
    found: set[str] = set()
    for field in fields:
        found.update(_roles_from_text(field))
    return found


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
    authority = dict(entry.get("behavioral_authority") or {})
    out = {
        "id": entry.get("id"),
        "title": entry.get("title") or _clip(entry.get("text"), 120),
        "kind": entry.get("kind"),
        "scope": entry.get("scope"),
        "state": entry.get("state"),
        "text": _clip(entry.get("text"), MAX_ENTRY_TEXT),
        "authority": authority.get("role", "ADVISORY_EVIDENCE"),
        "may_change_behavior": bool(authority.get("may_change_behavior", False)),
        "authority_scope": authority.get("authority_scope", "evidence_only"),
        "evidence": list(entry.get("evidence") or [])[:4],
    }
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
        "authority": "ADVISORY_EVIDENCE",
    }


def _json_size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _fit_sections(pack: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Drop lowest-value tail records until the serialized pack fits the hard budget."""
    max_chars = max(MIN_CONTEXT_CHARS, min(MAX_CONTEXT_CHARS, int(max_chars)))
    order = ("historical_evidence", "durable_memory", "behavior_authority")
    while True:
        pack["serialized_chars"] = _json_size({k: v for k, v in pack.items() if k != "serialized_chars"})
        actual = _json_size(pack)
        if actual <= max_chars:
            pack["serialized_chars"] = actual
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


def build_context_pack(query: str, hits: Iterable[dict[str, Any]], *, max_chars: int = DEFAULT_CONTEXT_CHARS) -> dict[str, Any]:
    """Build a task-scoped context package without promoting history into authority.

    The caller owns retrieval. This function only separates source roles and applies
    a hard prompt-size budget. It never changes canonical memory or source state.
    """
    query = " ".join(str(query or "").split())
    if not query:
        raise ValueError("context query must not be blank")

    behavior: list[dict[str, Any]] = []
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
        if compact["may_change_behavior"]:
            behavior.append(compact)
        elif compact.get("state") != "PROVEN":
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
            "behavior_authority": "only explicitly authorized stored behavior; current user instruction still wins",
            "durable_memory": "proven durable/advisory memory, not live machine/repo truth",
            "historical_evidence": "historical evidence only; never authority by retrieval frequency or recency",
        },
        "behavior_authority": behavior,
        "durable_memory": durable,
        "historical_evidence": historical,
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
