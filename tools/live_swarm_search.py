from __future__ import annotations

import re
from typing import Any, Mapping


_STOPWORDS = frozenset({"a", "an", "and", "for", "in", "is", "of", "the", "to", "work"})


def _terms(text: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9]+", str(text).casefold())
        if term and term not in _STOPWORDS
    }


def _matched_terms(query_terms: set[str], values: list[tuple[int, str]]) -> set[str]:
    matched: set[str] = set()
    for _, value in values:
        normalized = str(value).casefold()
        tokens = _terms(value)
        matched.update(term for term in query_terms if term in tokens or term in normalized)
    return matched


def _matched_fields(query_terms: set[str], fields: Mapping[str, str]) -> dict[str, list[str]]:
    matched: dict[str, list[str]] = {}
    for name, value in fields.items():
        terms = sorted(_matched_terms(query_terms, [(1, value)]))
        if terms:
            matched[name] = terms
    return matched


def _minimum_query_term_matches(query_terms: set[str]) -> int:
    return 1 if len(query_terms) <= 1 else 2


def _match_score(query_terms: set[str], values: list[tuple[int, str]]) -> int:
    score = 0
    for weight, value in values:
        normalized = str(value).casefold()
        tokens = _terms(value)
        score += weight * sum(1 for term in query_terms if term in tokens or term in normalized)
    return score


def search_live_swarm(snapshot: Mapping[str, Any], query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search one live-swarm snapshot without collapsing coordination into liveness.

    Busy rows are coordination/handoff only; caller rows are runtime activity. Callers provide one already-collected
    live-swarm snapshot, so search never performs another runtime probe or becomes
    a queue/scheduler surface.
    """
    query_terms = _terms(query)
    numeric_terms = {term for term in query_terms if term.isdigit()}
    if not query_terms or limit <= 0:
        return []

    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for lane in snapshot.get("lanes", []) if isinstance(snapshot, Mapping) else []:
        if not isinstance(lane, Mapping):
            continue
        workspace = str(lane.get("workspace") or "")
        worktree = lane.get("worktree") if isinstance(lane.get("worktree"), Mapping) else {}
        branch = str(worktree.get("branch") or "")
        path = str(worktree.get("path") or "")

        for busy in lane.get("busy", []) if isinstance(lane.get("busy"), list) else []:
            if not isinstance(busy, Mapping):
                continue
            owner = str(busy.get("owner") or "")
            checkpoint = str(busy.get("checkpoint") or "")
            scopes = [str(scope) for scope in busy.get("scopes", []) if str(scope).strip()]
            values = [
                (6, checkpoint),
                (5, " ".join(scopes)),
                (4, owner),
                (2, workspace),
                (2, branch),
                (1, path),
            ]
            matched_terms = _matched_terms(query_terms, values)
            if numeric_terms and not (numeric_terms & matched_terms):
                continue
            if len(matched_terms) < _minimum_query_term_matches(query_terms):
                continue
            score = _match_score(query_terms, values)
            if score:
                matched_fields = _matched_fields(query_terms, {
                    "checkpoint": checkpoint,
                    "scopes": " ".join(scopes),
                    "owner": owner,
                    "workspace": workspace,
                    "branch": branch,
                    "path": path,
                })
                item = {
                    "id": f"live_swarm.busy:{owner or lane.get('lane_id', 'unknown')}",
                    "kind": "busy_handoff",
                    "authority": "BUSY_COORDINATION_EVIDENCE",
                    "liveness_semantics": "not_worker_liveness_or_progress",
                    "matched_terms": sorted(matched_terms),
                    "matched_fields": matched_fields,
                    "match_semantics": "query_matched_coordination_handoff_fields_not_worker_activity",
                    "owner": owner or None,
                    "workspace": workspace or None,
                    "branch": branch or None,
                    "scopes": scopes,
                    "checkpoint": checkpoint or None,
                    "last_update_age_seconds": busy.get("last_update_age_seconds"),
                }
                ranked.append((score, item["id"], item))

        for caller in lane.get("callers", []) if isinstance(lane.get("callers"), list) else []:
            if not isinstance(caller, Mapping):
                continue
            caller_id = str(caller.get("caller_id") or "")
            command = str(caller.get("command") or "")
            caller_workspace = str(caller.get("workspace") or workspace)
            caller_worktree = caller.get("worktree") if isinstance(caller.get("worktree"), Mapping) else worktree
            caller_branch = str(caller_worktree.get("branch") or "")
            caller_path = str(caller_worktree.get("path") or "")
            values = [
                (4, command),
                (4, caller_branch),
                (3, caller_id),
                (2, caller_workspace),
                (1, caller_path),
            ]
            matched_terms = _matched_terms(query_terms, values)
            if numeric_terms and not (numeric_terms & matched_terms):
                continue
            if len(matched_terms) < _minimum_query_term_matches(query_terms):
                continue
            score = _match_score(query_terms, values)
            if score:
                matched_fields = _matched_fields(query_terms, {
                    "activity": command,
                    "caller_id": caller_id,
                    "workspace": caller_workspace,
                    "branch": caller_branch,
                    "path": caller_path,
                })
                activity_match = bool(matched_fields.get("activity"))
                item = {
                    "id": f"live_swarm.caller:{caller_id or lane.get('lane_id', 'unknown')}",
                    "kind": "caller_activity",
                    "authority": "LIVE_MCP_RUNTIME_EVIDENCE",
                    "liveness_semantics": "recent_caller_activity_within_snapshot_window",
                    "matched_terms": sorted(matched_terms),
                    "matched_fields": matched_fields,
                    "match_semantics": ("query_matched_activity_command" if activity_match else "query_matched_execution_surface_or_identity_not_activity_command"),
                    "caller_id": caller_id or None,
                    "workspace": caller_workspace or None,
                    "branch": caller_branch or None,
                    "activity": command or None,
                    "last_activity_age_seconds": caller.get("last_activity_age_seconds"),
                }
                ranked.append((score, item["id"], item))

    for source in snapshot.get("transport_sources", []) if isinstance(snapshot.get("transport_sources"), list) else []:
        if not isinstance(source, Mapping):
            continue
        instance = str(source.get("instance") or "")
        local_port = source.get("local_port")
        server_pid = source.get("server_pid")
        values = [
            (6, instance),
            (4, f"port {local_port}" if local_port is not None else ""),
            (2, f"pid {server_pid}" if server_pid is not None else ""),
        ]
        matched_terms = _matched_terms(query_terms, values)
        if numeric_terms and not (numeric_terms & matched_terms):
            continue
        if len(matched_terms) < _minimum_query_term_matches(query_terms):
            continue
        score = _match_score(query_terms, values)
        matched_fields = _matched_fields(query_terms, {
            "instance": instance,
            "port": f"port {local_port}" if local_port is not None else "",
            "pid": f"pid {server_pid}" if server_pid is not None else "",
        })
        item = {
            "id": f"live_swarm.transport:{instance or local_port or server_pid or 'unknown'}",
            "kind": "transport_source",
            "authority": "LIVE_MCP_TRANSPORT_SOURCE_EVIDENCE",
            "liveness_semantics": "transport_observation_source_not_worker_liveness_or_progress",
            "matched_terms": sorted(matched_terms),
            "matched_fields": matched_fields,
            "match_semantics": "query_matched_transport_source_identity",
            "instance": instance or None,
            "local_port": local_port,
            "server_pid": server_pid,
            "latest_event_at": source.get("latest_event_at"),
            "activity_window_complete": source.get("activity_window_complete"),
            "observation_window_complete": source.get("observation_window_complete"),
        }
        ranked.append((score, item["id"], item))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in ranked[:limit]]
