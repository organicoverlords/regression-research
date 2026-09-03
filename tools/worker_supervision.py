from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "worker-reports"
DEFAULT_BUSY = Path(os.environ.get("LOCALAPPDATA", "")) / "BusyCoordinator" / "busy-python.cmd"


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso_now() -> str:
    return _now().isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_report(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key and key.replace("_", "").isalnum() and (key[0].isalpha() or key[0] == "_"):
            fields[key.lower()] = value.strip()
    activity = fields.get("last_activity_at")
    parsed = _parse_time(activity)
    age_minutes = None
    if parsed is not None:
        age_minutes = round((_now().astimezone(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 60, 1)
    return {
        "automation_id": fields.get("automation_id"),
        "display_label": fields.get("display_label") or fields.get("worker") or path.stem,
        "worker": fields.get("display_label") or fields.get("worker") or path.stem,
        "state": fields.get("state"),
        "outcome": fields.get("outcome"),
        "repo": fields.get("repo"),
        "scope": fields.get("scope"),
        "last_activity_at": activity,
        "activity_age_minutes": age_minutes,
        "last_event": fields.get("last_event"),
        "mutation": fields.get("mutation"),
        "validation": fields.get("validation"),
        "remaining_gate": fields.get("remaining_gate"),
        "stop_reason": fields.get("stop_reason"),
        "stop_detail": fields.get("stop_detail"),
        "transport_drops": fields.get("transport_drops"),
        "binding_drops": fields.get("binding_drops"),
        "safety_blocks": fields.get("safety_blocks"),
        "other_tool_failures": fields.get("other_tool_failures"),
        "legacy_unclassified_tool_drops": fields.get("legacy_unclassified_tool_drops"),
        "tool_failure_effect": fields.get("tool_failure_effect"),
        "tool_drops": fields.get("tool_drops"),
        "tool_drop_effect": fields.get("tool_drop_effect"),
        "report_path": str(path),
        "report_sha256": hashlib.sha256(raw).hexdigest(),
    }


def _safe_worker(worker: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in worker).strip("-")
    return cleaned or "worker"


def event_id(event_kind: str, report_sha256: str) -> str:
    material = f"{event_kind}\n{report_sha256}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def receipt_path(report_dir: Path, event: str) -> Path:
    return report_dir / ".supervision" / "handled" / f"{event}.json"


def candidate_events(report: dict[str, Any], *, stale_minutes: float) -> list[dict[str, Any]]:
    state = (report.get("state") or "").upper()
    primary_kind = "blocked" if state == "BLOCKED" else "completed" if state in {"DONE", "COMPLETE"} else "report_update"
    kinds = [primary_kind]
    age = report.get("activity_age_minutes")
    if state == "RUNNING" and isinstance(age, (int, float)) and age > stale_minutes:
        kinds.append("stale_running")
    return [
        {**report, "event_kind": kind, "event_id": event_id(kind, str(report["report_sha256"]))}
        for kind in kinds
    ]


def _busy_call(busy: Path, args: list[str]) -> tuple[int, dict[str, Any] | None, str]:
    proc = subprocess.run([str(busy), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    raw = (proc.stdout or proc.stderr or "").strip()
    parsed = None
    if raw:
        try:
            parsed = json.loads(raw.splitlines()[-1])
        except json.JSONDecodeError:
            pass
    return proc.returncode, parsed, raw


def claim_events(report_dir: Path, *, actor: str, busy: Path, stale_minutes: float, lease_seconds: int, scope_prefix: str) -> dict[str, Any]:
    claimed: list[dict[str, Any]] = []
    claimed_elsewhere = 0
    already_handled = 0
    reports = []
    if report_dir.exists():
        reports.extend(report_dir.glob("*.md"))  # legacy display-name snapshots
        current_dir = report_dir / "current"
        if current_dir.exists():
            reports.extend(current_dir.glob("*.md"))  # automation-ID keyed current snapshots
        reports = sorted(reports, key=lambda p: p.stat().st_mtime, reverse=True)
    for path in reports:
        report = parse_report(path)
        for event in candidate_events(report, stale_minutes=stale_minutes):
            receipt = receipt_path(report_dir, event["event_id"])
            if receipt.exists():
                already_handled += 1
                continue
            scope = f"{scope_prefix}:{event['event_kind']}:{event['event_id'][:16]}"
            checkpoint = f"supervise report {event['report_sha256'][:12]} {event['event_kind']} ({event.get('display_label') or 'unlabeled'})"
            code, payload, _ = _busy_call(busy, ["claim", "--lease-seconds", str(lease_seconds), "--checkpoint", checkpoint, actor, scope])
            if code == 0 and payload and payload.get("ok"):
                claimed.append({**event, "claim_actor": actor, "claim_scope": scope, "receipt_path": str(receipt)})
            else:
                claimed_elsewhere += 1
    return {
        "ok": True,
        "actor": actor,
        "report_dir": str(report_dir),
        "claimed_count": len(claimed),
        "claimed_elsewhere_count": claimed_elsewhere,
        "already_handled_count": already_handled,
        "events": claimed,
    }


def acknowledge_event(report_dir: Path, *, event: str, event_kind: str, worker: str, report_sha256: str, claim_actor: str, claim_scope: str, busy: Path, disposition: str, note: str | None) -> dict[str, Any]:
    code, payload, raw = _busy_call(busy, ["inspect", claim_actor, claim_scope])
    claim = payload.get("claim") if payload else None
    if code != 0 or not payload or not payload.get("ok") or not claim or claim.get("actor") != claim_actor:
        raise RuntimeError(f"supervision event is not owned by {claim_actor}: {raw}")
    receipt = receipt_path(report_dir, event)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": "worker-supervision-handled.v1",
        "event_id": event,
        "event_kind": event_kind,
        "worker": worker,
        "report_sha256": report_sha256,
        "handled_at": _iso_now(),
        "handled_by": claim_actor,
        "claim_scope": claim_scope,
        "disposition": disposition,
        "note": note,
    }
    tmp = receipt.with_suffix(receipt.suffix + f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, receipt)
    release_code, release_payload, release_raw = _busy_call(busy, ["release", claim_actor, claim_scope])
    return {
        "ok": release_code == 0 and bool(release_payload and release_payload.get("ok")),
        "receipt": str(receipt),
        "released": release_payload,
        "release_raw": None if release_code == 0 else release_raw,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collision-safe recurring worker supervision receipts.")
    sub = parser.add_subparsers(dest="command", required=True)
    claim = sub.add_parser("claim", help="Claim unseen worker-report events through BusyCoordinator.")
    claim.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    claim.add_argument("--busy", type=Path, default=DEFAULT_BUSY)
    claim.add_argument("--actor")
    claim.add_argument("--stale-minutes", type=float, default=20.0)
    claim.add_argument("--lease-seconds", type=int, default=900)
    claim.add_argument("--scope-prefix", default="worker-supervision")
    ack = sub.add_parser("ack", help="Mark a claimed supervision event handled, then release it.")
    ack.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    ack.add_argument("--busy", type=Path, default=DEFAULT_BUSY)
    ack.add_argument("--event-id", required=True)
    ack.add_argument("--event-kind", required=True)
    ack.add_argument("--worker", required=True)
    ack.add_argument("--report-sha256", required=True)
    ack.add_argument("--claim-actor", required=True)
    ack.add_argument("--claim-scope", required=True)
    ack.add_argument("--disposition", default="handled")
    ack.add_argument("--note")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "claim":
        actor = args.actor or f"ChatGPT-supervisor-{uuid.uuid4().hex[:12]}"
        result = claim_events(args.report_dir, actor=actor, busy=args.busy, stale_minutes=args.stale_minutes, lease_seconds=args.lease_seconds, scope_prefix=args.scope_prefix)
    else:
        result = acknowledge_event(args.report_dir, event=args.event_id, event_kind=args.event_kind, worker=args.worker, report_sha256=args.report_sha256, claim_actor=args.claim_actor, claim_scope=args.claim_scope, busy=args.busy, disposition=args.disposition, note=args.note)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
