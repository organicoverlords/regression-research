"""Fail-closed authorization for recurring-worker sibling recovery.

This module deliberately does not mutate ChatGPT scheduler state. It narrows the
boundary immediately before the existing scheduler write by binding one actor
worker id to one target worker id and the actor-scoped local fleet evidence.
"""
from __future__ import annotations

import argparse
import json
from typing import Any, Callable

try:
    from tools.stack_atlas import (
        CANONICAL_RECURRING_WORKER_PARTITION_BY_ID,
        _bootstrap_fleet_watch,
    )
except ImportError:
    from stack_atlas import (
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Authorize one exact recurring-worker sibling recovery from actor-scoped local evidence."
    )
    parser.add_argument("--actor-worker-id", required=True)
    parser.add_argument("--target-worker-id", required=True)
    args = parser.parse_args()
    result = authorize_recovery(args.actor_worker_id, args.target_worker_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("authorized") else 3


if __name__ == "__main__":
    raise SystemExit(main())
