"""Mutable operational bindings for stable recurring-worker slots.

Slots are durable fleet capacity identities (S1/1..S1/5 and S2/1..S2/5).
ChatGPT automation IDs and display names are mutable bindings.  The registry is
machine-local operational state under worker-reports/.supervision and is not
liveness evidence by itself.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "recurring-worker-slot-bindings.v1"
REGISTRY_RELATIVE_PATH = Path("worker-reports") / ".supervision" / "recurring-slot-bindings.json"
RECURRING_WORKER_SLOTS = {
    "S1": tuple(f"S1/{index}" for index in range(1, 6)),
    "S2": tuple(f"S2/{index}" for index in range(1, 6)),
}
_SLOT_TO_PARTITION = {
    slot_id: partition
    for partition, slot_ids in RECURRING_WORKER_SLOTS.items()
    for slot_id in slot_ids
}
_AUTOMATION_ID_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def registry_path(root: Path | None = None) -> Path:
    return (root or _default_root()) / REGISTRY_RELATIVE_PATH


def _empty_payload() -> dict[str, Any]:
    return {
        "schema": REGISTRY_SCHEMA,
        "updated_at": None,
        "authority": "MUTABLE_OPERATIONAL_SLOT_BINDINGS_NOT_LIVENESS",
        "bindings": {},
    }


def _normalize_binding(slot_id: str, raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, f"binding for {slot_id} must be an object"
    automation_id = str(raw.get("automation_id") or "").strip().lower()
    if not _AUTOMATION_ID_RE.fullmatch(automation_id):
        return None, f"binding for {slot_id} has invalid automation_id"
    label = str(raw.get("label") or "").strip() or None
    bound_at = str(raw.get("bound_at") or "").strip() or None
    first_expected_start_at = str(raw.get("first_expected_start_at") or "").strip() or None
    return {
        "slot_id": slot_id,
        "partition": _SLOT_TO_PARTITION[slot_id],
        "automation_id": automation_id,
        "label": label,
        "bound_at": bound_at,
        "first_expected_start_at": first_expected_start_at,
    }, None


def load_slot_snapshot(root: Path | None = None) -> dict[str, Any]:
    """Read and validate current bindings without mutating anything."""
    path = registry_path(root)
    payload = _empty_payload()
    status = "MISSING"
    error = None
    try:
        candidate = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(candidate, dict):
            raise ValueError("registry root must be an object")
        payload = candidate
        status = "OK"
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        status = "INVALID"
        error = str(exc)

    raw_bindings = payload.get("bindings") if isinstance(payload.get("bindings"), dict) else {}
    if status == "OK" and payload.get("schema") != REGISTRY_SCHEMA:
        status = "INVALID"
        error = f"expected schema {REGISTRY_SCHEMA}"

    bindings_by_slot: dict[str, dict[str, Any] | None] = {
        slot_id: None for slot_id in _SLOT_TO_PARTITION
    }
    automation_to_slot: dict[str, str] = {}
    if status == "OK":
        unknown_slots = sorted(set(raw_bindings) - set(_SLOT_TO_PARTITION))
        if unknown_slots:
            status = "INVALID"
            error = f"unknown slot ids: {', '.join(unknown_slots)}"
        else:
            for slot_id in _SLOT_TO_PARTITION:
                binding, binding_error = _normalize_binding(slot_id, raw_bindings.get(slot_id))
                if binding_error:
                    status = "INVALID"
                    error = binding_error
                    break
                bindings_by_slot[slot_id] = binding
                if binding is not None:
                    automation_id = binding["automation_id"]
                    if automation_id in automation_to_slot:
                        status = "INVALID"
                        error = (
                            f"automation_id {automation_id} bound to both "
                            f"{automation_to_slot[automation_id]} and {slot_id}"
                        )
                        break
                    automation_to_slot[automation_id] = slot_id

    if status != "OK":
        bindings_by_slot = {slot_id: None for slot_id in _SLOT_TO_PARTITION}
        automation_to_slot = {}

    partitions: dict[str, dict[str, Any]] = {}
    for partition, slot_ids in RECURRING_WORKER_SLOTS.items():
        slot_rows = []
        for slot_id in slot_ids:
            binding = bindings_by_slot[slot_id]
            slot_rows.append({
                "slot_id": slot_id,
                "binding": binding,
                "bound": binding is not None,
            })
        partitions[partition] = {
            "slot_capacity": len(slot_ids),
            "bound_count": sum(1 for row in slot_rows if row["bound"]),
            "unbound_count": sum(1 for row in slot_rows if not row["bound"]),
            "slots": slot_rows,
        }

    bound_workers = [binding for binding in bindings_by_slot.values() if binding is not None]
    return {
        "schema": REGISTRY_SCHEMA,
        "status": status,
        "path": str(path),
        "authority": "MUTABLE_OPERATIONAL_SLOT_BINDINGS_NOT_LIVENESS",
        "updated_at": payload.get("updated_at") if isinstance(payload, dict) else None,
        "error": error,
        "partitions": partitions,
        "bindings_by_slot": bindings_by_slot,
        "automation_to_slot": automation_to_slot,
        "bound_workers": bound_workers,
        "bound_count": len(bound_workers),
        "slot_capacity_total": sum(len(slots) for slots in RECURRING_WORKER_SLOTS.values()),
        "semantics": "unbound_or_missing_binding_is_not_worker_liveness_failure_and_never_authorizes_scheduler_mutation",
    }


def _write_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def bind_slot(
    slot_id: str,
    automation_id: str,
    *,
    label: str | None = None,
    replace_current: bool = False,
    first_expected_start_at: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    slot = str(slot_id or "").strip().upper()
    automation = str(automation_id or "").strip().lower()
    if slot not in _SLOT_TO_PARTITION:
        return {"ok": False, "status": "INVALID_SLOT", "slot_id": slot}
    if not _AUTOMATION_ID_RE.fullmatch(automation):
        return {"ok": False, "status": "INVALID_AUTOMATION_ID", "slot_id": slot, "automation_id": automation}

    snapshot = load_slot_snapshot(root)
    if snapshot["status"] not in {"OK", "MISSING"}:
        return {"ok": False, "status": "REGISTRY_INVALID", "error": snapshot.get("error")}

    current = snapshot["bindings_by_slot"].get(slot)
    existing_slot = snapshot["automation_to_slot"].get(automation)
    if existing_slot is not None and existing_slot != slot:
        return {
            "ok": False,
            "status": "AUTOMATION_ALREADY_BOUND",
            "automation_id": automation,
            "existing_slot": existing_slot,
        }
    if current is not None and current.get("automation_id") != automation and not replace_current:
        return {
            "ok": False,
            "status": "SLOT_OCCUPIED",
            "slot_id": slot,
            "current_binding": current,
            "hint": "retry with --replace-current only when this is the intended worker replacement",
        }

    path = registry_path(root)
    raw = _empty_payload()
    if snapshot["status"] == "OK":
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {"ok": False, "status": "REGISTRY_CHANGED_DURING_BIND"}
    bindings = raw.setdefault("bindings", {})
    now = datetime.now(timezone.utc).isoformat()
    previous = bindings.get(slot)
    bindings[slot] = {
        "automation_id": automation,
        "label": str(label or "").strip() or None,
        "bound_at": now,
        "first_expected_start_at": str(first_expected_start_at or "").strip() or None,
    }
    raw["schema"] = REGISTRY_SCHEMA
    raw["authority"] = "MUTABLE_OPERATIONAL_SLOT_BINDINGS_NOT_LIVENESS"
    raw["updated_at"] = now
    _write_payload(path, raw)
    result = load_slot_snapshot(root)
    return {
        "ok": result["status"] == "OK",
        "status": "BOUND" if result["status"] == "OK" else "POST_WRITE_INVALID",
        "slot_id": slot,
        "partition": _SLOT_TO_PARTITION[slot],
        "previous_binding": previous,
        "binding": result["bindings_by_slot"].get(slot),
        "registry_path": str(path),
    }


def clear_slot(
    slot_id: str,
    *,
    expected_automation_id: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    slot = str(slot_id or "").strip().upper()
    if slot not in _SLOT_TO_PARTITION:
        return {"ok": False, "status": "INVALID_SLOT", "slot_id": slot}
    snapshot = load_slot_snapshot(root)
    if snapshot["status"] != "OK":
        return {"ok": False, "status": "REGISTRY_NOT_READY", "registry_status": snapshot["status"]}
    current = snapshot["bindings_by_slot"].get(slot)
    if current is None:
        return {"ok": True, "status": "ALREADY_UNBOUND", "slot_id": slot}
    expected = str(expected_automation_id or "").strip().lower() or None
    if expected is not None and current.get("automation_id") != expected:
        return {
            "ok": False,
            "status": "EXPECTED_BINDING_MISMATCH",
            "slot_id": slot,
            "expected_automation_id": expected,
            "current_binding": current,
        }
    path = registry_path(root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "status": "REGISTRY_CHANGED_DURING_CLEAR"}
    raw.setdefault("bindings", {}).pop(slot, None)
    raw["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_payload(path, raw)
    return {"ok": True, "status": "UNBOUND", "slot_id": slot, "previous_binding": current, "registry_path": str(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage mutable bindings for stable recurring-worker slots.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    bind = sub.add_parser("bind")
    bind.add_argument("--slot", required=True, choices=tuple(_SLOT_TO_PARTITION))
    bind.add_argument("--automation-id", required=True)
    bind.add_argument("--label")
    bind.add_argument("--replace-current", action="store_true")
    bind.add_argument("--first-expected-start-at")
    clear = sub.add_parser("clear")
    clear.add_argument("--slot", required=True, choices=tuple(_SLOT_TO_PARTITION))
    clear.add_argument("--expected-automation-id")
    args = parser.parse_args()
    if args.command == "list":
        result = load_slot_snapshot()
    elif args.command == "bind":
        result = bind_slot(args.slot, args.automation_id, label=args.label, replace_current=args.replace_current, first_expected_start_at=args.first_expected_start_at)
    else:
        result = clear_slot(args.slot, expected_automation_id=args.expected_automation_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", result.get("status") in {"OK", "MISSING"}) else 1


if __name__ == "__main__":
    raise SystemExit(main())
