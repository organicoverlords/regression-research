from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
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
DEFAULT_ACTIVITY_WINDOW_SECONDS = 300


def _parse_at(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def summarize_live_worker_status(
    evidence: Iterable[dict[str, Any]],
    *,
    execution_visibility: bool = True,
    now: datetime | None = None,
    activity_window_seconds: int = DEFAULT_ACTIVITY_WINDOW_SECONDS,
) -> dict[str, Any]:
    rows = list(evidence)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    current = [
        row
        for row in rows
        if row.get("kind") in CURRENT_EXECUTION_KINDS
        and row.get("current") is True
        and row.get("scope_match", True) is True
    ]
    recent = []
    for row in rows:
        if row.get("kind") not in ACTUAL_WORK_KINDS:
            continue
        if row.get("scope_match", True) is not True:
            continue
        at = _parse_at(row.get("at"))
        if at is None:
            continue
        age_seconds = (
            now.astimezone(timezone.utc) - at.astimezone(timezone.utc)
        ).total_seconds()
        if 0 <= age_seconds <= activity_window_seconds:
            recent.append(row)

    completed = [
        row
        for row in rows
        if row.get("kind") in ACTUAL_WORK_KINDS
        and row.get("within_claim_window") is True
        and row.get("scope_match", True) is True
    ]
    counts = dict(sorted(Counter(str(row.get("kind")) for row in completed).items()))
    timestamps = sorted(str(row.get("at")) for row in completed if row.get("at"))
    if current or recent:
        status, working_now = "working", True
    elif execution_visibility:
        status, working_now = "not_working", False
    else:
        status, working_now = "unverified", False
    return {
        "status": status,
        "working_now": working_now,
        "current_execution_count": len(current),
        "recent_activity_count": len(recent),
        "activity_window_seconds": activity_window_seconds,
        "work_events_in_claim_window": len(completed),
        "work_by_kind": counts,
        "last_work_at": timestamps[-1] if timestamps else None,
        "basis": [row.get("kind") for row in current + recent],
    }
