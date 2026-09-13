"""Fail-closed authorization boundary for recurring-worker recovery.

This module never mutates ChatGPT scheduler state. Recurring-worker actor mode is
denial-only: workers may observe and hand off evidence but can never receive a
scheduler-write authorization. Only supervising-chat mode may authorize one exact
canonical target from fleet-scoped local evidence.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any, Callable

try:
    from tools.stack_atlas import (
        ATLAS_LIVE_ROOT,
        BOOTSTRAP_RECURRING_CADENCE_GRACE_MINUTES,
        _bootstrap_fleet_watch,
    )
    from tools.recurring_slot_registry import RECURRING_WORKER_SLOTS, load_slot_snapshot
except ImportError:
    from stack_atlas import (
        ATLAS_LIVE_ROOT,
        BOOTSTRAP_RECURRING_CADENCE_GRACE_MINUTES,
        _bootstrap_fleet_watch,
    )
    from recurring_slot_registry import RECURRING_WORKER_SLOTS, load_slot_snapshot

FleetWatch = Callable[..., dict[str, Any]]


def _binding_partition_map() -> tuple[dict[str, str], dict[str, Any]]:
    snapshot = load_slot_snapshot(ATLAS_LIVE_ROOT)
    if snapshot.get("status") != "OK":
        return {}, snapshot
    mapping = {
        binding["automation_id"]: binding["partition"]
        for binding in snapshot.get("bound_workers", [])
    }
    return mapping, snapshot


def _deny(actor: str, target: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": "recurring-worker-recovery-authorization.v1",
        "authorized": False,
        "actor_worker_id": actor,
        "target_worker_id": target,
        "reason": reason,
        **extra,
    }


def authorize_recovery(
    actor_worker_id: str,
    target_worker_id: str,
    *,
    fleet_watch: FleetWatch = _bootstrap_fleet_watch,
) -> dict[str, Any]:
    """Fail closed for worker actors; recurring workers never administer scheduler state."""
    actor = str(actor_worker_id or "").strip().lower()
    target = str(target_worker_id or "").strip().lower()
    _ = fleet_watch  # compatibility parameter; worker mode intentionally performs no fleet read

    partition_by_id, slot_snapshot = _binding_partition_map()
    if slot_snapshot.get("status") != "OK":
        return _deny(actor, target, "SLOT_REGISTRY_UNAVAILABLE", slot_registry_status=slot_snapshot.get("status"))
    actor_partition = partition_by_id.get(actor)
    if actor_partition is None:
        return _deny(actor, target, "ACTOR_NOT_BOUND_TO_RECURRING_SLOT")

    target_partition = partition_by_id.get(target)
    if target_partition is None:
        return _deny(
            actor,
            target,
            "TARGET_NOT_BOUND_TO_RECURRING_SLOT",
            actor_partition=actor_partition,
        )

    if actor == target:
        return _deny(
            actor,
            target,
            "SELF_ADMINISTRATION_FORBIDDEN",
            actor_partition=actor_partition,
            target_partition=target_partition,
        )

    return _deny(
        actor,
        target,
        "WORKER_SCHEDULER_ADMINISTRATION_FORBIDDEN",
        actor_partition=actor_partition,
        target_partition=target_partition,
    )


def _supervisor_deny(partition: str, target: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": "recurring-worker-recovery-authorization.v1",
        "authorized": False,
        "actor_mode": "supervising_chat",
        "supervising_chat_partition": partition,
        "target_worker_id": target,
        "reason": reason,
        **extra,
    }


def _parse_scheduler_time(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def authorize_supervising_chat_recovery(
    supervising_chat_partition: str,
    target_worker_id: str,
    *,
    scheduler_enabled: bool | None = None,
    scheduler_last_run_at: str | None = None,
    fleet_watch: FleetWatch = _bootstrap_fleet_watch,
) -> dict[str, Any]:
    """Authorize one exact partition-scoped recovery only after a live scheduler probe."""
    partition = str(supervising_chat_partition or "").strip().upper()
    target = str(target_worker_id or "").strip().lower()

    if partition not in RECURRING_WORKER_SLOTS:
        return _supervisor_deny(partition, target, "SUPERVISING_CHAT_PARTITION_NOT_CANONICAL")

    partition_by_id, slot_snapshot = _binding_partition_map()
    if slot_snapshot.get("status") != "OK":
        return _supervisor_deny(
            partition, target, "SLOT_REGISTRY_UNAVAILABLE", slot_registry_status=slot_snapshot.get("status")
        )
    target_partition = partition_by_id.get(target)
    if target_partition is None:
        return _supervisor_deny(partition, target, "TARGET_NOT_BOUND_TO_RECURRING_SLOT")

    # Validate the target boundary before reading any fleet state. A supervising
    # chat is scoped to exactly one subscription partition and cannot inspect a
    # different partition as a side effect of a recovery request.
    if target_partition != partition:
        return _supervisor_deny(
            partition,
            target,
            "CROSS_PARTITION_RECOVERY_FORBIDDEN",
            target_partition=target_partition,
        )

    watch = fleet_watch(partition=partition)
    if not isinstance(watch, dict):
        return _supervisor_deny(
            partition,
            target,
            "FLEET_WATCH_INVALID",
            target_partition=target_partition,
        )

    if watch.get("subscription_scope") != partition:
        return _supervisor_deny(
            partition,
            target,
            "FLEET_WATCH_SCOPE_MISMATCH",
            target_partition=target_partition,
            observed_subscription_scope=watch.get("subscription_scope"),
        )

    candidates = {
        str(item.get("automation_id") or "").strip().lower(): item
        for item in watch.get("recovery_candidates", [])
        if isinstance(item, dict)
    }
    candidate = candidates.get(target)
    if candidate is None:
        return _supervisor_deny(
            partition,
            target,
            "TARGET_NOT_ACTIONABLE",
            target_partition=target_partition,
            fleet_status=watch.get("status"),
        )

    if candidate.get("subscription_partition") != partition:
        return _supervisor_deny(
            partition,
            target,
            "CANDIDATE_PARTITION_MISMATCH",
            target_partition=target_partition,
            candidate_partition=candidate.get("subscription_partition"),
        )

    if scheduler_enabled is None:
        return _supervisor_deny(
            partition,
            target,
            "LIVE_SCHEDULER_PROBE_REQUIRED",
            target_partition=target_partition,
            candidate_reason=str(candidate.get("reason") or "LOCAL_CADENCE_GAP"),
            scheduler_probe="required",
            evidence_authority=watch.get("authority"),
        )

    scheduler_probe = "verified_disabled" if scheduler_enabled is False else "verified_enabled"
    scheduler_last_run = _parse_scheduler_time(scheduler_last_run_at)
    scheduler_age_minutes = None
    if scheduler_last_run is not None:
        scheduler_age_minutes = max(0.0, (datetime.now(timezone.utc) - scheduler_last_run).total_seconds() / 60.0)

    if scheduler_enabled is True:
        if scheduler_last_run is None:
            return _supervisor_deny(
                partition,
                target,
                "SCHEDULER_ENABLED_LAST_RUN_REQUIRED",
                target_partition=target_partition,
                scheduler_probe=scheduler_probe,
                candidate_reason=str(candidate.get("reason") or "LOCAL_CADENCE_GAP"),
                evidence_authority=watch.get("authority"),
            )
        if scheduler_age_minutes <= BOOTSTRAP_RECURRING_CADENCE_GRACE_MINUTES:
            return _supervisor_deny(
                partition,
                target,
                "LOCAL_EVIDENCE_STALE_SCHEDULER_CURRENT",
                target_partition=target_partition,
                scheduler_probe=scheduler_probe,
                scheduler_last_run_at=scheduler_last_run.isoformat(),
                scheduler_last_run_age_minutes=round(scheduler_age_minutes, 1),
                candidate_reason=str(candidate.get("reason") or "LOCAL_CADENCE_GAP"),
                evidence_authority=watch.get("authority"),
            )
        scheduler_probe = "verified_enabled_missed_cadence"

    return {
        "schema": "recurring-worker-recovery-authorization.v1",
        "authorized": True,
        "actor_mode": "supervising_chat",
        "supervising_chat_partition": partition,
        "target_worker_id": target,
        "target_partition": target_partition,
        "reason": (
            "SCHEDULER_DISABLED_RECOVERY"
            if scheduler_enabled is False
            else "ENABLED_BUT_MISSED_SCHEDULER_CADENCE_REARM"
        ),
        "local_candidate_reason": str(candidate.get("reason") or "LOCAL_CADENCE_GAP"),
        "scheduler_action": {
            "operation": "set_is_enabled",
            "is_enabled": True,
        },
        "scheduler_probe": scheduler_probe,
        "scheduler_last_run_at": scheduler_last_run.isoformat() if scheduler_last_run is not None else None,
        "scheduler_last_run_age_minutes": round(scheduler_age_minutes, 1) if scheduler_age_minutes is not None else None,
        "evidence_authority": f"{watch.get('authority')}+live_scheduler_probe",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize one exact recurring-worker recovery from supervisor-scoped local evidence; worker actor mode is denial-only."
    )
    actor_mode = parser.add_mutually_exclusive_group(required=True)
    actor_mode.add_argument("--actor-worker-id")
    actor_mode.add_argument(
        "--supervising-chat-partition",
        choices=tuple(RECURRING_WORKER_SLOTS),
    )
    parser.add_argument("--target-worker-id", required=True)
    parser.add_argument("--scheduler-enabled", choices=("true", "false"))
    parser.add_argument("--scheduler-last-run-at")
    args = parser.parse_args()
    if args.actor_worker_id:
        result = authorize_recovery(args.actor_worker_id, args.target_worker_id)
    else:
        scheduler_enabled = None
        if args.scheduler_enabled is not None:
            scheduler_enabled = args.scheduler_enabled == "true"
        result = authorize_supervising_chat_recovery(
            args.supervising_chat_partition,
            args.target_worker_id,
            scheduler_enabled=scheduler_enabled,
            scheduler_last_run_at=args.scheduler_last_run_at,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("authorized") else 3


if __name__ == "__main__":
    raise SystemExit(main())
