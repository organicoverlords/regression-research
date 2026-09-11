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
            score = _match_score(query_terms, [
                (6, checkpoint),
                (5, " ".join(scopes)),
                (4, owner),
                (2, workspace),
                (2, branch),
                (1, path),
            ])
            if score:
                item = {
                    "id": f"live_swarm.busy:{owner or lane.get('lane_id', 'unknown')}",
                    "kind": "busy_handoff",
                    "authority": "BUSY_COORDINATION_EVIDENCE",
                    "liveness_semantics": "not_worker_liveness_or_progress",
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
            score = _match_score(query_terms, [
                (4, command),
                (4, caller_branch),
                (3, caller_id),
                (2, caller_workspace),
                (1, caller_path),
            ])
            if score:
                item = {
                    "id": f"live_swarm.caller:{caller_id or lane.get('lane_id', 'unknown')}",
                    "kind": "caller_activity",
                    "authority": "LIVE_MCP_RUNTIME_EVIDENCE",
                    "liveness_semantics": "recent_caller_activity_within_snapshot_window",
                    "caller_id": caller_id or None,
                    "workspace": caller_workspace or None,
                    "branch": caller_branch or None,
                    "activity": command or None,
                    "last_activity_age_seconds": caller.get("last_activity_age_seconds"),
                }
                ranked.append((score, item["id"], item))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in ranked[:limit]]
