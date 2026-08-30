from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

CURRENT_EXECUTION_KINDS = {
    "running_automation",
    "running_run",
    "running_session",
    "running_process",
    "in_flight_tool",
    "in_flight_command",
}

ACTUAL_WORK_KINDS = {
    "command_completed",
    "tool_completed",
    "test_completed",
    "commit_created",
    "artifact_written",
    "pull_request_updated",
}


def summarize_live_worker_status(
    evidence: Iterable[dict[str, Any]],
    *,
    execution_visibility: bool = True,
) -> dict[str, Any]:
    rows = list(evidence)
    current = [
        row
        for row in rows
        if row.get("kind") in CURRENT_EXECUTION_KINDS
        and row.get("current") is True
        and row.get("scope_match", True) is True
    ]
    completed = [
        row
        for row in rows
        if row.get("kind") in ACTUAL_WORK_KINDS
        and row.get("within_claim_window") is True
        and row.get("scope_match", True) is True
    ]
    counts = dict(sorted(Counter(str(row.get("kind")) for row in completed).items()))
    timestamps = sorted(str(row.get("at")) for row in completed if row.get("at"))
    if current:
        status, working_now = "working", True
    elif execution_visibility:
        status, working_now = "not_working", False
    else:
        status, working_now = "unverified", False
    return {
        "status": status,
        "working_now": working_now,
        "current_execution_count": len(current),
        "work_events_in_claim_window": len(completed),
        "work_by_kind": counts,
        "last_work_at": timestamps[-1] if timestamps else None,
        "basis": [row.get("kind") for row in current],
    }
