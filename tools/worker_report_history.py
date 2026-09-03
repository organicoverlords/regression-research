from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TARGET_RUN_MINUTES = 24.0
SHORT_RUN_UTILIZATION_PCT = 75.0
NEAR_TARGET_UTILIZATION_PCT = 90.0
STOP_REASON_ALIASES = {
    "TIME_LIMIT": "TIME_WINDOW", "TIMEOUT": "TIME_WINDOW", "TARGET_WINDOW": "TIME_WINDOW",
    "WAITING_CI": "WAITING_EXTERNAL", "WAITING_CHECK": "WAITING_EXTERNAL",
    "TOOL_DROP": "TOOL_BLOCKED", "TOOLS_BLOCKED": "TOOL_BLOCKED",
    "RESOURCE_WAIT": "RESOURCE_BLOCKED", "USER_STOP": "INTERRUPTED",
}
VALID_STOP_REASONS = {
    "TIME_WINDOW", "SCOPE_COMPLETE", "WAITING_EXTERNAL", "TOOL_BLOCKED",
    "RESOURCE_BLOCKED", "NO_SAFE_WORK", "INTERRUPTED", "OTHER",
}
VALID_TOOL_DROP_EFFECTS = {"RECOVERED_CONTINUED", "CONTRIBUTED_TO_STOP", "BLOCKED_REQUIRED_ROUTE"}
CLASSIFIED_FAILURE_FIELDS = ("transport_drops", "binding_drops", "safety_blocks", "other_tool_failures")


def _fields(raw: bytes) -> dict[str, str]:
    text = raw.decode("utf-8", errors="replace")
    result: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lstrip("\ufeff").lower()
        if key and key.replace("_", "").isalnum():
            result[key] = value.strip()
    return result


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()

def _int_field(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _gate_classes(value: Any) -> list[str]:
    text = str(value or "").strip().casefold()
    if not text or text in {"none", "n/a", "na", "no gate"}:
        return []
    classes: list[str] = []
    checks = (
        ("TOOL", ("tool", "plugin", "mcp", "commander", "route")),
        ("RESOURCE", ("disk", "build slot", "resource", "memory", "vram", "lock")),
        ("PROOF", ("proof", "render", "visual", "capture", "acceptance")),
        ("EXTERNAL", ("hosted", "ci", "check", "workflow", "approval", "review")),
        ("MERGE", ("merge", "conflict", "landing")),
    )
    for label, tokens in checks:
        if any(token in text for token in tokens):
            classes.append(label)
    return classes or ["OTHER"]


def _run_analytics(item: dict[str, Any]) -> dict[str, Any]:
    util = item.get("target_utilization_pct")
    util_value = float(util) if isinstance(util, (int, float)) else None
    reported = str(item.get("reported_stop_reason") or item.get("stop_reason") or "").strip().upper()
    reported = reported.replace("-", "_").replace(" ", "_")
    explicit = bool(reported) and reported not in {"UNEXPLAINED", "UNSPECIFIED"}
    normalized = STOP_REASON_ALIASES.get(reported, reported) if explicit else ""
    if normalized and normalized not in VALID_STOP_REASONS:
        normalized = "OTHER"

    remaining_gate = item.get("remaining_gate")
    state = str(item.get("state") or "").upper()
    if explicit:
        stop_reason = normalized
        stop_reason_source = "WORKER_REPORTED"
    elif util_value is not None and util_value >= NEAR_TARGET_UTILIZATION_PCT:
        stop_reason = "TIME_WINDOW"
        stop_reason_source = "DERIVED_DURATION"
    elif state == "COMPLETE" and not _gate_classes(remaining_gate):
        stop_reason = "SCOPE_COMPLETE"
        stop_reason_source = "DERIVED_STATE"
    elif util_value is not None and util_value < SHORT_RUN_UTILIZATION_PCT:
        stop_reason = "UNEXPLAINED"
        stop_reason_source = "DERIVED_ABSENCE"
    else:
        stop_reason = "UNSPECIFIED"
        stop_reason_source = "DERIVED_ABSENCE"

    classified_present = any(item.get(field) not in (None, "") for field in CLASSIFIED_FAILURE_FIELDS)
    transport_drops = _int_field(item.get("transport_drops")) or 0
    binding_drops = _int_field(item.get("binding_drops")) or 0
    safety_blocks = _int_field(item.get("safety_blocks")) or 0
    other_tool_failures = _int_field(item.get("other_tool_failures")) or 0
    explicit_legacy = _int_field(item.get("legacy_unclassified_tool_drops"))
    legacy_tool_drops = explicit_legacy if explicit_legacy is not None else (0 if classified_present else (_int_field(item.get("tool_drops")) or 0))
    tool_failures_total = transport_drops + binding_drops + safety_blocks + other_tool_failures + legacy_tool_drops
    effect = str(item.get("tool_failure_effect") or item.get("tool_drop_effect") or "").strip().upper()
    effect = effect.replace("-", "_").replace(" ", "_")
    if tool_failures_total == 0:
        effect = "NONE"
    elif effect not in VALID_TOOL_DROP_EFFECTS:
        effect = "UNSPECIFIED"

    early = util_value is not None and util_value < SHORT_RUN_UTILIZATION_PCT
    return {
        "reported_stop_reason": reported or None,
        "stop_reason": stop_reason,
        "stop_reason_source": stop_reason_source,
        "stop_detail": item.get("stop_detail"),
        "pending_gate_classes": _gate_classes(remaining_gate),
        "transport_drops": transport_drops,
        "binding_drops": binding_drops,
        "safety_blocks": safety_blocks,
        "other_tool_failures": other_tool_failures,
        "legacy_unclassified_tool_drops": legacy_tool_drops,
        "tool_failures_total": tool_failures_total,
        "tool_failure_effect": effect,
        # Legacy aliases remain readable, but no longer feed the headline transport metric.
        "tool_drops": legacy_tool_drops,
        "tool_drop_effect": effect,
        "early_stop": early,
        "early_stop_unexplained": bool(early and stop_reason in {"UNEXPLAINED", "UNSPECIFIED"}),
    }


def _derived_metadata(fields: dict[str, str], *, digest: str, archive_path: Path) -> dict[str, Any]:
    started_at = fields.get("started_at")
    finished_at = fields.get("finished_at") or fields.get("last_activity_at")
    started = _parse_time(started_at)
    finished = _parse_time(finished_at)
    duration_seconds = None
    if started is not None and finished is not None:
        seconds = (finished - started).total_seconds()
        if seconds >= 0:
            duration_seconds = round(seconds, 3)
    duration_minutes = round(duration_seconds / 60, 2) if duration_seconds is not None else None
    utilization = round(duration_minutes / TARGET_RUN_MINUTES * 100, 1) if duration_minutes is not None else None
    base: dict[str, Any] = {
        "schema": "worker-report-history.v5",
        "report_sha256": digest,
        "automation_id": fields.get("automation_id"),
        "display_label": fields.get("display_label") or fields.get("worker"),
        "worker": fields.get("display_label") or fields.get("worker") or "unknown",
        "state": fields.get("state"),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "target_run_minutes": TARGET_RUN_MINUTES,
        "target_utilization_pct": utilization,
        "repo": fields.get("repo"),
        "scope": fields.get("scope"),
        "why_priority": fields.get("why_priority"),
        "outcome": fields.get("outcome"),
        "mutation": fields.get("mutation"),
        "validation": fields.get("validation"),
        "last_event": fields.get("last_event"),
        "remaining_gate": fields.get("remaining_gate"),
        "reported_stop_reason": fields.get("stop_reason"),
        "stop_detail": fields.get("stop_detail"),
        "transport_drops": _int_field(fields.get("transport_drops")),
        "binding_drops": _int_field(fields.get("binding_drops")),
        "safety_blocks": _int_field(fields.get("safety_blocks")),
        "other_tool_failures": _int_field(fields.get("other_tool_failures")),
        "legacy_unclassified_tool_drops": _int_field(fields.get("legacy_unclassified_tool_drops")),
        "tool_failure_effect": fields.get("tool_failure_effect"),
        "tool_drops": _int_field(fields.get("tool_drops")),
        "tool_drop_effect": fields.get("tool_drop_effect"),
        "visual_proof_run": fields.get("visual_proof_run"),
        "visual_proof_claim": fields.get("visual_proof_claim"),
        "visual_proof_review": fields.get("visual_proof_review"),
        "visual_proof_reviewed_json": fields.get("visual_proof_reviewed_json"),
        "archived_at": datetime.now().astimezone().isoformat(),
        "archive_path": str(archive_path),
    }
    base.update(_run_analytics(base))
    return base

def load_history_metadata(history_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    canonical_root = history_root / "_reports"
    if not canonical_root.exists():
        return records
    for path in sorted(canonical_root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("schema") or "").startswith("worker-report-history.v"):
            records.append(payload)
    return records


def summarize_history(history_root: Path, *, hours: float = 24.0) -> dict[str, Any]:
    now = datetime.now().astimezone()
    cutoff = now - timedelta(hours=max(0.01, float(hours)))
    records: list[dict[str, Any]] = []
    for raw in load_history_metadata(history_root):
        finished = _parse_time(raw.get("finished_at") or raw.get("archived_at"))
        if finished is not None and finished >= cutoff:
            item = dict(raw)
            item.update(_run_analytics(item))
            records.append(item)

    durations = [float(x["duration_minutes"]) for x in records if isinstance(x.get("duration_minutes"), (int, float))]
    utils = [float(x["target_utilization_pct"]) for x in records if isinstance(x.get("target_utilization_pct"), (int, float))]
    stop_counts = Counter(str(x["stop_reason"]) for x in records)
    early_records = [x for x in records if x.get("early_stop")]
    early_stop_counts = Counter(str(x["stop_reason"]) for x in early_records)
    gate_counts = Counter(label for x in records for label in x.get("pending_gate_classes", []))
    transport_drop_runs = [x for x in records if int(x.get("transport_drops") or 0) > 0]
    binding_drop_runs = [x for x in records if int(x.get("binding_drops") or 0) > 0]
    safety_block_runs = [x for x in records if int(x.get("safety_blocks") or 0) > 0]
    other_tool_failure_runs = [x for x in records if int(x.get("other_tool_failures") or 0) > 0]
    legacy_tool_drop_runs = [x for x in records if int(x.get("legacy_unclassified_tool_drops") or 0) > 0]
    tool_failure_stop_runs = [
        x for x in records
        if int(x.get("tool_failures_total") or 0) > 0
        and (x.get("tool_failure_effect") in {"CONTRIBUTED_TO_STOP", "BLOCKED_REQUIRED_ROUTE"} or x.get("stop_reason") == "TOOL_BLOCKED")
    ]
    transport_or_binding_runs = [x for x in records if int(x.get("transport_drops") or 0) > 0 or int(x.get("binding_drops") or 0) > 0]
    transport_or_binding_stop_runs = [x for x in transport_or_binding_runs if x in tool_failure_stop_runs]

    def record_sort_key(item: dict[str, Any]) -> float:
        parsed = _parse_time(item.get("finished_at") or item.get("archived_at"))
        return parsed.timestamp() if parsed is not None else float("-inf")

    ordered_records = sorted(records, key=record_sort_key)

    total_minutes = round(sum(durations), 2)
    window_minutes = hours * 60.0
    return {
        "schema": "worker-report-metrics.v4",
        "generated_at": now.isoformat(),
        "window_hours": float(hours),
        "target_run_minutes": TARGET_RUN_MINUTES,
        "captured_runs": len(records),
        "runs_with_duration": len(durations),
        "average_duration_minutes": round(statistics.mean(durations), 2) if durations else None,
        "median_duration_minutes": round(statistics.median(durations), 2) if durations else None,
        "average_target_utilization_pct": round(statistics.mean(utils), 1) if utils else None,
        "short_runs_under_75pct": len(early_records),
        "early_stops_unexplained": sum(1 for x in early_records if x.get("early_stop_unexplained")),
        "stop_reason_counts": dict(sorted(stop_counts.items())),
        "early_stop_reason_counts": dict(sorted(early_stop_counts.items())),
        "pending_gate_counts": dict(sorted(gate_counts.items())),
        # Backward headline now means classified callable-route loss only; safety and legacy values are separate.
        "tool_drop_runs": len(transport_or_binding_runs),
        "tool_drops_total": sum(int(x.get("transport_drops") or 0) + int(x.get("binding_drops") or 0) for x in transport_or_binding_runs),
        "tool_drop_stop_runs": len(transport_or_binding_stop_runs),
        "transport_drop_runs": len(transport_drop_runs),
        "transport_drops_total": sum(int(x.get("transport_drops") or 0) for x in transport_drop_runs),
        "binding_drop_runs": len(binding_drop_runs),
        "binding_drops_total": sum(int(x.get("binding_drops") or 0) for x in binding_drop_runs),
        "safety_block_runs": len(safety_block_runs),
        "safety_blocks_total": sum(int(x.get("safety_blocks") or 0) for x in safety_block_runs),
        "other_tool_failure_runs": len(other_tool_failure_runs),
        "other_tool_failures_total": sum(int(x.get("other_tool_failures") or 0) for x in other_tool_failure_runs),
        "legacy_unclassified_tool_drop_runs": len(legacy_tool_drop_runs),
        "legacy_unclassified_tool_drops_total": sum(int(x.get("legacy_unclassified_tool_drops") or 0) for x in legacy_tool_drop_runs),
        "tool_failure_stop_runs": len(tool_failure_stop_runs),
        "worker_minutes": total_minutes,
        "equivalent_continuous_workers": round(total_minutes / window_minutes, 3) if window_minutes else None,
        "capacity_pct_of_one_continuous_worker": round(total_minutes / window_minutes * 100.0, 1) if window_minutes else None,
        # Names are display labels, not identity keys. This ordered list is the supervisor's
        # rename-safe discovery surface; report_sha256 is the immutable report identity.
        "latest_reports": [
            {
                "report_sha256": item.get("report_sha256"),
                "automation_id": item.get("automation_id"),
                "display_label": item.get("display_label") or item.get("worker"),
                "finished_at": item.get("finished_at"),
                "duration_minutes": item.get("duration_minutes"),
                "repo": item.get("repo"),
                "scope": item.get("scope"),
                "state": item.get("state"),
                "stop_reason": item.get("stop_reason"),
                "archive_path": item.get("archive_path"),
            }
            for item in reversed(ordered_records[-20:])
        ],
    }

def _project_from_repo(repo: str | None) -> str | None:
    if not repo:
        return None
    name = str(repo).replace("\\", "/").rstrip("/").split("/")[-1].casefold()
    return {
        "p3": "p3",
        "tiny3d": "tiny3d",
        "lowvram3d-studio": "lowvram",
        "regression-research": "regression-research",
    }.get(name, name or None)


def worker_history_events(history_root: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for raw in load_history_metadata(history_root):
        item = dict(raw)
        item.update(_run_analytics(item))
        event_at = item.get("finished_at") or item.get("archived_at")
        if not event_at:
            continue
        display_label = str(item.get("display_label") or item.get("worker") or "worker")
        scope = str(item.get("scope") or "")
        outcome = str(item.get("outcome") or item.get("state") or "report")
        events.append({
            "id": f"worker:{item.get('report_sha256') or event_at}",
            "source_type": "WORKER_REPORT",
            "authority": "DERIVED_WORKER_HISTORY",
            "event_at": event_at,
            "recorded_at": item.get("archived_at") or event_at,
            "project": _project_from_repo(item.get("repo")),
            "automation_id": item.get("automation_id"),
            "display_label": display_label,
            "worker": display_label,
            "title": f"{display_label}: {outcome}" + (f" - {scope}" if scope else ""),
            "summary": item.get("last_event") or item.get("mutation") or "",
            "kind": "worker_report",
            "scope": scope,
            "state": item.get("state"),
            "outcome": item.get("outcome"),
            "duration_minutes": item.get("duration_minutes"),
            "target_run_minutes": item.get("target_run_minutes"),
            "target_utilization_pct": item.get("target_utilization_pct"),
            "stop_reason": item.get("stop_reason"),
            "stop_reason_source": item.get("stop_reason_source"),
            "stop_detail": item.get("stop_detail"),
            "early_stop": item.get("early_stop"),
            "pending_gate_classes": item.get("pending_gate_classes"),
            "transport_drops": item.get("transport_drops"),
            "binding_drops": item.get("binding_drops"),
            "safety_blocks": item.get("safety_blocks"),
            "other_tool_failures": item.get("other_tool_failures"),
            "legacy_unclassified_tool_drops": item.get("legacy_unclassified_tool_drops"),
            "tool_failures_total": item.get("tool_failures_total"),
            "tool_failure_effect": item.get("tool_failure_effect"),
            "tool_drops": item.get("tool_drops"),
            "tool_drop_effect": item.get("tool_drop_effect"),
            "mutation": item.get("mutation"),
            "validation": item.get("validation"),
            "remaining_gate": item.get("remaining_gate"),
            "visual_proof_run": item.get("visual_proof_run"),
            "visual_proof_review": item.get("visual_proof_review"),
            "refs": [value for value in (scope, item.get("mutation")) if value],
        })
    return events

def write_metrics_projection(history_root: Path, output: Path | None = None, *, hours: float = 24.0) -> dict[str, Any]:
    summary = summarize_history(history_root, hours=hours)
    target = output or history_root.parent / "metrics.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def archive_finalized_report(report: Path, history_root: Path) -> dict[str, Any]:
    raw = report.read_bytes()
    fields = _fields(raw)
    # Older/current worker writers sometimes use `outcome: COMPLETE` without a separate
    # `state:` field. Treat a terminal delivery token in either field as finalized.
    state = (fields.get("state") or fields.get("outcome") or "").upper()
    if state not in {"COMPLETE", "WAITING", "BLOCKED", "DONE"}:
        raise ValueError(f"report is not finalized: state={state or 'MISSING'}")
    worker = fields.get("worker") or report.stem
    fields.setdefault("worker", worker)
    fields.setdefault("state", state)
    digest = hashlib.sha256(raw).hexdigest()
    # Canonical archive identity is content-addressed, never the mutable display name.
    # This prevents renames or name reuse from hiding/overwriting report history.
    target_dir = history_root / "_reports"
    target = target_dir / f"{digest}.md"
    metadata_path = target_dir / f"{digest}.json"
    target_dir.mkdir(parents=True, exist_ok=True)
    archived = not target.exists()
    if target.exists() and target.read_bytes() != raw:
        raise RuntimeError(f"history hash collision at {target}")
    if archived:
        target.write_bytes(raw)
    metadata_created = not metadata_path.exists()
    if metadata_created:
        metadata = _derived_metadata(fields, digest=digest, archive_path=target)
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.update(_run_analytics(metadata))
    metrics = write_metrics_projection(history_root)
    return {
        "ok": True,
        "archived": archived,
        "deduplicated": not archived,
        "metadata_created": metadata_created,
        "sha256": digest,
        "path": str(target),
        "metadata_path": str(metadata_path),
        "duration_minutes": metadata.get("duration_minutes"),
        "target_run_minutes": metadata.get("target_run_minutes"),
        "target_utilization_pct": metadata.get("target_utilization_pct"),
        "stop_reason": metadata.get("stop_reason"),
        "early_stop": metadata.get("early_stop"),
        "transport_drops": metadata.get("transport_drops"),
        "binding_drops": metadata.get("binding_drops"),
        "safety_blocks": metadata.get("safety_blocks"),
        "other_tool_failures": metadata.get("other_tool_failures"),
        "legacy_unclassified_tool_drops": metadata.get("legacy_unclassified_tool_drops"),
        "tool_failures_total": metadata.get("tool_failures_total"),
        "tool_failure_effect": metadata.get("tool_failure_effect"),
        "tool_drops": metadata.get("tool_drops"),
        "fleet_metrics_path": str(history_root.parent / "metrics.json"),
        "fleet_average_utilization_pct": metrics.get("average_target_utilization_pct"),
        "fleet_early_stops_unexplained": metrics.get("early_stops_unexplained"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preserve finalized worker reports and derive useful run metrics automatically.")
    sub = parser.add_subparsers(dest="command", required=True)
    archive = sub.add_parser("archive")
    archive.add_argument("--report", type=Path, required=True)
    archive.add_argument("--history-root", type=Path)
    summary = sub.add_parser("summary")
    summary.add_argument("--history-root", type=Path, required=True)
    summary.add_argument("--hours", type=float, default=24.0)
    summary.add_argument("--write", type=Path)
    return parser


def _default_history_root(report: Path) -> Path:
    parent = report.parent
    if parent.name.casefold() == "current":
        return parent.parent / "history"
    return parent / "history"


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "archive":
            history_root = args.history_root or _default_history_root(args.report)
            result = archive_finalized_report(args.report, history_root)
        else:
            result = write_metrics_projection(args.history_root, args.write, hours=args.hours) if args.write else summarize_history(args.history_root, hours=args.hours)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
