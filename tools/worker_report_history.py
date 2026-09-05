from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TARGET_RUN_MINUTES = 24.0
MIN_RUN_FINISH_UTILIZATION_PCT = 80.0
LOCAL_CONTENTION_STOP_MARKERS = (
    "occupied", "collision ownership", "ownership was unavailable", "resource-dependent",
    "resource dependent", "heavy runtime", "runtime lane", "build lane", "unreal lane",
    "unreal/runtime", "pending ci", "pending proof",
)
USER_END_MARKERS = ("user interrupt", "user supersed")
PROVEN_NO_SAFE_WORK_MARKERS = (
    "task-level blocker", "safe existing execution surfaces", "independent useful work", "exhausted",
)
CURRENT_REPORT_REQUIRED_FIELDS = (
    "automation_id", "started_at", "last_activity_at", "repo", "scope", "state",
    "outcome", "mutation", "validation", "remaining_gate",
)



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


def _validate_current_report(report: Path, fields: dict[str, str]) -> None:
    """Fail closed on malformed stable current/<automation-id>.md reports."""
    if report.parent.name.casefold() != "current":
        return
    missing = [key for key in CURRENT_REPORT_REQUIRED_FIELDS if not fields.get(key, "").strip()]
    if missing:
        raise ValueError("current report missing required canonical field(s): " + ", ".join(missing))
    automation_id = fields["automation_id"].strip()
    if report.stem.casefold() != automation_id.casefold():
        raise ValueError(f"current report automation_id does not match filename: {automation_id} != {report.stem}")
    started = _parse_time(fields["started_at"])
    last_activity = _parse_time(fields["last_activity_at"])
    if started is None:
        raise ValueError("current report started_at is not a valid ISO-8601 timestamp")
    if last_activity is None:
        raise ValueError("current report last_activity_at is not a valid ISO-8601 timestamp")
    if last_activity < started:
        raise ValueError("current report last_activity_at precedes started_at")


def _validate_run_finished(fields: dict[str, str]) -> None:
    if str(fields.get("state") or "").strip().upper() != "RUN_FINISHED":
        return
    started = _parse_time(fields.get("started_at"))
    finished = _parse_time(fields.get("last_activity_at"))
    if started is None or finished is None:
        return
    duration_minutes = (finished - started).total_seconds() / 60.0
    utilization_pct = duration_minutes / TARGET_RUN_MINUTES * 100.0
    if utilization_pct >= MIN_RUN_FINISH_UTILIZATION_PCT:
        return

    reason = str(fields.get("stop_reason") or "").strip().casefold()
    if any(marker in reason for marker in USER_END_MARKERS):
        return
    if reason and all(marker in reason for marker in PROVEN_NO_SAFE_WORK_MARKERS):
        return

    evidence = " ".join((reason, str(fields.get("remaining_gate") or "").casefold()))
    if any(marker in evidence for marker in LOCAL_CONTENTION_STOP_MARKERS):
        raise ValueError(
            "premature RUN_FINISHED rejected: this run is NOT finished and this report was NOT archived. "
            "DO NOT end/final-answer the worker turn. Local contention is not a task-level stop reason; "
            "continue useful P3 work through another safe non-conflicting scope and retry finalization only "
            "after >=80% utilization or user interruption/supersession"
        )
    raise ValueError(
        "premature RUN_FINISHED rejected: this run is NOT finished and this report was NOT archived. "
        "DO NOT end/final-answer the worker turn. Under 80% utilization, continue useful P3 work unless "
        "the user interrupted/superseded the run or the documented true no-safe-work condition applies"
    )


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
    display_label = fields.get("display_label") or fields.get("worker")
    return {
        "schema": "worker-report-history.v6",
        "report_sha256": digest,
        "automation_id": fields.get("automation_id"),
        "display_label": display_label,
        "worker": display_label or "unknown",
        "state": fields.get("state"),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "target_run_minutes": TARGET_RUN_MINUTES,
        "target_utilization_pct": utilization,
        "repo": fields.get("repo"),
        "scope": fields.get("scope"),
        "outcome": fields.get("outcome"),
        "mutation": fields.get("mutation") or fields.get("mutations"),
        "validation": fields.get("validation"),
        "last_event": fields.get("last_event"),
        "remaining_gate": fields.get("remaining_gate") or fields.get("remaining_heavy_gate"),
        "stop_reason": fields.get("stop_reason"),
        "visual_proof_run": fields.get("visual_proof_run"),
        "visual_proof_claim": fields.get("visual_proof_claim"),
        "visual_proof_review": fields.get("visual_proof_review"),
        "visual_proof_reviewed_json": fields.get("visual_proof_reviewed_json"),
        "reported_fields": fields,
        "archived_at": datetime.now().astimezone().isoformat(),
        "archive_path": str(archive_path),
    }


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


def build_metrics_projection(history_root: Path, *, hours: float = 24.0) -> dict[str, Any]:
    now = datetime.now().astimezone()
    cutoff = now - timedelta(hours=hours)
    records: list[dict[str, Any]] = []
    for item in load_history_metadata(history_root):
        archived = _parse_time(item.get("archived_at"))
        if archived is not None and archived >= cutoff:
            records.append(item)

    durations = [float(item["duration_minutes"]) for item in records if isinstance(item.get("duration_minutes"), (int, float))]
    utilizations = [float(item["target_utilization_pct"]) for item in records if isinstance(item.get("target_utilization_pct"), (int, float))]
    records.sort(key=lambda item: _parse_time(item.get("archived_at")) or datetime.min.astimezone())
    latest = [
        {
            "report_sha256": item.get("report_sha256"),
            "automation_id": item.get("automation_id"),
            "display_label": item.get("display_label") or item.get("worker"),
            "archived_at": item.get("archived_at"),
            "finished_at": item.get("finished_at"),
            "duration_minutes": item.get("duration_minutes"),
            "target_utilization_pct": item.get("target_utilization_pct"),
            "repo": item.get("repo"),
            "scope": item.get("scope"),
            "state": item.get("state"),
            "outcome": item.get("outcome"),
            "stop_reason": item.get("reported_stop_reason") or item.get("stop_reason"),
        }
        for item in reversed(records[-20:])
    ]
    return {
        "schema": "worker-report-metrics.v1",
        "generated_at": now.isoformat(),
        "window_hours": hours,
        "reports": len(records),
        "runs_with_duration": len(durations),
        "average_duration_minutes": round(statistics.mean(durations), 2) if durations else None,
        "median_duration_minutes": round(statistics.median(durations), 2) if durations else None,
        "average_target_utilization_pct": round(statistics.mean(utilizations), 1) if utilizations else None,
        "latest_reports": latest,
    }


def write_metrics_projection(history_root: Path, *, hours: float = 24.0) -> tuple[Path, dict[str, Any]]:
    metrics = build_metrics_projection(history_root, hours=hours)
    target = history_root.parent / "metrics.json"
    target.write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target, metrics


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
    for item in load_history_metadata(history_root):
        event_at = item.get("finished_at") or item.get("archived_at")
        if not event_at:
            continue
        display_label = str(item.get("display_label") or item.get("worker") or "worker")
        scope = str(item.get("scope") or "")
        outcome = str(item.get("outcome") or item.get("state") or "report")
        mutation = item.get("mutation")
        stop_reason = item.get("reported_stop_reason") or item.get("stop_reason")
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
            "summary": item.get("last_event") or mutation or "",
            "kind": "worker_report",
            "scope": scope,
            "state": item.get("state"),
            "outcome": item.get("outcome"),
            "duration_minutes": item.get("duration_minutes"),
            "target_run_minutes": item.get("target_run_minutes"),
            "target_utilization_pct": item.get("target_utilization_pct"),
            "stop_reason": stop_reason,
            "mutation": mutation,
            "validation": item.get("validation"),
            "remaining_gate": item.get("remaining_gate"),
            "visual_proof_run": item.get("visual_proof_run"),
            "visual_proof_review": item.get("visual_proof_review"),
            "refs": [value for value in (scope, mutation) if value],
        })
    return events


def archive_finalized_report(report: Path, history_root: Path) -> dict[str, Any]:
    raw = report.read_bytes()
    fields = _fields(raw)
    _validate_current_report(report, fields)
    try:
        _validate_run_finished(fields)
    except ValueError:
        # A rejected premature finalization means the live run is still active. Keep the
        # canonical current report truthful even if RUN_FINISHED was written first.
        if report.parent.name.casefold() == "current" and str(fields.get("state") or "").strip().upper() == "RUN_FINISHED":
            marker = b"state: RUN_FINISHED"
            if marker in raw:
                tmp = report.with_name(report.name + ".continuation.tmp")
                try:
                    tmp.write_bytes(raw.replace(marker, b"state: RUNNING", 1))
                    tmp.replace(report)
                except OSError:
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass
        raise
    state = (fields.get("state") or fields.get("outcome") or "").upper()
    if state not in {"RUN_FINISHED", "COMPLETE", "WAITING", "BLOCKED", "DONE"}:
        raise ValueError(f"report is not finalized: state={state or 'MISSING'}")
    fields.setdefault("worker", fields.get("display_label") or report.stem)
    fields.setdefault("state", state)
    digest = hashlib.sha256(raw).hexdigest()
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
    metrics_path, metrics = write_metrics_projection(history_root)
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
        "stop_reason": metadata.get("reported_stop_reason") or metadata.get("stop_reason"),
        "metrics_path": str(metrics_path),
        "fleet_average_utilization_pct": metrics.get("average_target_utilization_pct"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preserve finalized worker reports as immutable content-addressed history.")
    sub = parser.add_subparsers(dest="command", required=True)
    archive = sub.add_parser("archive")
    archive.add_argument("--report", type=Path, required=True)
    archive.add_argument("--history-root", type=Path)
    return parser


def _default_history_root(report: Path) -> Path:
    parent = report.parent
    if parent.name.casefold() == "current":
        return parent.parent / "history"
    return parent / "history"


def main() -> int:
    args = build_parser().parse_args()
    try:
        history_root = args.history_root or _default_history_root(args.report)
        result = archive_finalized_report(args.report, history_root)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
