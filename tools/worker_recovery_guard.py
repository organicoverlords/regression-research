"""Fail-closed authorization for recurring-worker or supervising-chat recovery.

This module deliberately does not mutate ChatGPT scheduler state. It narrows the
boundary immediately before the existing scheduler write by binding either one
canonical worker actor or one supervising-chat partition to one exact canonical
target and the corresponding partition-scoped local fleet evidence.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Callable

try:
    from tools.stack_atlas import (
        CANONICAL_RECURRING_WORKER_PARTITIONS,
        CANONICAL_RECURRING_WORKER_PARTITION_BY_ID,
        _bootstrap_fleet_watch,
    )
except ImportError:
    from stack_atlas import (
        CANONICAL_RECURRING_WORKER_PARTITIONS,
        CANONICAL_RECURRING_WORKER_PARTITION_BY_ID,
        _bootstrap_fleet_watch,
    )

FleetWatch = Callable[..., dict[str, Any]]


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
    """Authorize one exact same-partition recovery target or fail closed."""
    actor = str(actor_worker_id or "").strip().lower()
    target = str(target_worker_id or "").strip().lower()

    actor_partition = CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(actor)
    if actor_partition is None:
        return _deny(actor, target, "ACTOR_NOT_CANONICAL")

    target_partition = CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(target)
    if target_partition is None:
        return _deny(
            actor,
            target,
            "TARGET_NOT_CANONICAL",
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

    if actor_partition != target_partition:
        return _deny(
            actor,
            target,
            "CROSS_PARTITION_RECOVERY_FORBIDDEN",
            actor_partition=actor_partition,
            target_partition=target_partition,
        )

    watch = fleet_watch(worker_id=actor)
    if not isinstance(watch, dict):
        return _deny(
            actor,
            target,
            "FLEET_WATCH_INVALID",
            actor_partition=actor_partition,
            target_partition=target_partition,
        )

    if watch.get("subscription_scope") != actor_partition:
        return _deny(
            actor,
            target,
            "FLEET_WATCH_SCOPE_MISMATCH",
            actor_partition=actor_partition,
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
        return _deny(
            actor,
            target,
            "TARGET_NOT_ACTIONABLE",
            actor_partition=actor_partition,
            target_partition=target_partition,
            fleet_status=watch.get("status"),
        )

    if candidate.get("subscription_partition") != actor_partition:
        return _deny(
            actor,
            target,
            "CANDIDATE_PARTITION_MISMATCH",
            actor_partition=actor_partition,
            target_partition=target_partition,
            candidate_partition=candidate.get("subscription_partition"),
        )

    return {
        "schema": "recurring-worker-recovery-authorization.v1",
        "authorized": True,
        "actor_worker_id": actor,
        "target_worker_id": target,
        "actor_partition": actor_partition,
        "target_partition": target_partition,
        "reason": str(candidate.get("reason") or "RECOVERY_NEEDED"),
        "scheduler_action": {
            "operation": "set_is_enabled",
            "is_enabled": True,
        },
        "scheduler_probe": "not_performed",
        "evidence_authority": watch.get("authority"),
    }


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


def authorize_supervising_chat_recovery(
    supervising_chat_partition: str,
    target_worker_id: str,
    *,
    fleet_watch: FleetWatch = _bootstrap_fleet_watch,
) -> dict[str, Any]:
    """Authorize one exact partition-scoped recovery without worker impersonation."""
    partition = str(supervising_chat_partition or "").strip().upper()
    target = str(target_worker_id or "").strip().lower()

    if partition not in CANONICAL_RECURRING_WORKER_PARTITIONS:
        return _supervisor_deny(partition, target, "SUPERVISING_CHAT_PARTITION_NOT_CANONICAL")

    target_partition = CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(target)
    if target_partition is None:
        return _supervisor_deny(partition, target, "TARGET_NOT_CANONICAL")

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

    return {
        "schema": "recurring-worker-recovery-authorization.v1",
        "authorized": True,
        "actor_mode": "supervising_chat",
        "supervising_chat_partition": partition,
        "target_worker_id": target,
        "target_partition": target_partition,
        "reason": str(candidate.get("reason") or "RECOVERY_NEEDED"),
        "scheduler_action": {
            "operation": "set_is_enabled",
            "is_enabled": True,
        },
        "scheduler_probe": "not_performed",
        "evidence_authority": watch.get("authority"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize one exact recurring-worker recovery from worker- or supervisor-scoped local evidence."
    )
    actor_mode = parser.add_mutually_exclusive_group(required=True)
    actor_mode.add_argument("--actor-worker-id")
    actor_mode.add_argument(
        "--supervising-chat-partition",
        choices=tuple(CANONICAL_RECURRING_WORKER_PARTITIONS),
    )
    parser.add_argument("--target-worker-id", required=True)
    args = parser.parse_args()
    if args.actor_worker_id:
        result = authorize_recovery(args.actor_worker_id, args.target_worker_id)
    else:
        result = authorize_supervising_chat_recovery(
            args.supervising_chat_partition,
            args.target_worker_id,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("authorized") else 3


if __name__ == "__main__":
    raise SystemExit(main())
