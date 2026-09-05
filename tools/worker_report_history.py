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
MIN_RUN_FINISH_UTILIZATION_PCT = 80.0
LOCAL_CONTENTION_STOP_MARKERS = (
    "occupied", "collision ownership", "ownership was unavailable", "resource-dependent",
    "resource dependent", "heavy runtime", "runtime lane", "build lane", "unreal lane",
    "unreal/runtime", "pending ci", "pending proof",
)
USER_END_MARKERS = ("user interrupt", "user supersed")
CONTINUATION_STOP_REASON = "premature finalization rejected; run continuing"
MAX_FUTURE_ACTIVITY_SKEW_SECONDS = 60.0
START_RECEIPT_SCHEMA = "worker-run-start.v1"
START_RECEIPT_DIRNAME = ".supervision"
PROVEN_NO_SAFE_WORK_MARKERS = (
    "task-level blocker", "safe existing execution surfaces", "independent useful work", "exhausted",
)
CURRENT_REPORT_REQUIRED_FIELDS = (
    "automation_id", "started_at", "last_activity_at", "repo", "scope", "state",
    "outcome", "mutation", "validation", "remaining_gate",
)
MANUAL_CURRENT_REPORT_REQUIRED_FIELDS = (
    "run_id", "started_at", "last_activity_at", "repo", "scope", "state",
    "outcome", "mutation", "validation", "remaining_gate",
)
ALLOWED_FINDING_TAGS = frozenset({
    "bug", "error", "regression", "wrapper_anomaly", "route_problem", "contention",
    "performance", "improvement", "tooling", "ci", "build", "proof", "resource", "other",
})



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


def _duplicate_field_names(raw: bytes) -> list[str]:
    text = raw.decode("utf-8", errors="replace")
    seen: set[str] = set()
    duplicates: set[str] = set()
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _ = line.split(":", 1)
        key = key.strip().lstrip("\ufeff").lower()
        if not key or not key.replace("_", "").isalnum():
            continue
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return sorted(duplicates)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _report_population(*, report: Path | None = None, history_root: Path | None = None) -> str:
    if report is not None and report.parent.name.casefold() == "current" and report.parent.parent.name.casefold() == "manual":
        return "manual"
    if history_root is not None and history_root.parent.name.casefold() == "manual":
        return "manual"
    return "timed"


def _metadata_population(item: dict[str, Any]) -> str:
    population = str(item.get("population") or "timed").strip().casefold()
    return population if population in {"timed", "manual"} else "timed"


def _timed_start_receipt_path(report: Path) -> Path:
    return report.parent.parent / START_RECEIPT_DIRNAME / f"{report.stem}.start.json"


def begin_timed_run(report: Path) -> dict[str, Any]:
    raw = report.read_bytes()
    fields = _fields(raw)
    _validate_current_report(report, fields, raw)
    if _report_population(report=report) != "timed" or report.parent.name.casefold() != "current":
        raise ValueError("timed run begin requires worker-reports/current/<automation-id>.md")
    if str(fields.get("state") or "").strip().upper() != "RUNNING":
        raise ValueError("timed run begin requires state: RUNNING")
    now = datetime.now().astimezone()
    reported_started = _parse_time(fields.get("started_at"))
    if reported_started is None:
        raise ValueError("timed run begin requires a valid started_at")
    if reported_started > now + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
        raise ValueError("timed run begin rejected: started_at is in the future")
    receipt_path = _timed_start_receipt_path(report)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": START_RECEIPT_SCHEMA,
        "automation_id": fields.get("automation_id"),
        "observed_started_at": now.isoformat(),
        "reported_started_at": fields.get("started_at"),
        "initial_report_sha256": hashlib.sha256(raw).hexdigest(),
    }
    tmp = receipt_path.with_name(receipt_path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(receipt_path)
    return {
        "ok": True,
        "automation_id": fields.get("automation_id"),
        "observed_started_at": payload["observed_started_at"],
        "receipt_path": str(receipt_path),
    }


def _load_timed_start_receipt(report: Path, fields: dict[str, str]) -> tuple[datetime, Path]:
    receipt_path = _timed_start_receipt_path(report)
    if not receipt_path.exists():
        raise ValueError(
            "timed RUN_FINISHED requires machine start evidence; run begin was not registered with worker_report_history.py begin"
        )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if payload.get("schema") != START_RECEIPT_SCHEMA:
        raise ValueError("timed run start receipt schema is invalid")
    if str(payload.get("automation_id") or "").casefold() != report.stem.casefold():
        raise ValueError("timed run start receipt automation_id does not match current report")
    observed_started = _parse_time(str(payload.get("observed_started_at") or ""))
    reported_started = _parse_time(fields.get("started_at"))
    if observed_started is None or reported_started is None:
        raise ValueError("timed run start receipt contains invalid chronology")
    now = datetime.now().astimezone()
    if observed_started > now + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
        raise ValueError("timed run start receipt is in the future")
    if reported_started > observed_started + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
        raise ValueError(
            "timed run start receipt is stale for this generation: reported started_at is later than observed start"
        )
    return observed_started, receipt_path


def _parse_finding_tags(fields: dict[str, str]) -> list[str]:
    raw = str(fields.get("finding_tags") or "").strip()
    if not raw or raw.casefold() == "none":
        return []
    tags = sorted({part.strip().casefold().replace("-", "_").replace(" ", "_") for part in raw.split(",") if part.strip()})
    invalid = [tag for tag in tags if tag not in ALLOWED_FINDING_TAGS]
    if invalid:
        raise ValueError("unknown finding_tags: " + ", ".join(invalid))
    return tags


def _validate_current_report(report: Path, fields: dict[str, str], raw: bytes) -> None:
    """Fail closed on malformed stable current reports for timed and manual populations."""
    if report.parent.name.casefold() != "current":
        return
    duplicates = _duplicate_field_names(raw)
    if duplicates:
        raise ValueError("current report contains duplicate canonical field(s): " + ", ".join(duplicates))
    population = _report_population(report=report)
    required_fields = MANUAL_CURRENT_REPORT_REQUIRED_FIELDS if population == "manual" else CURRENT_REPORT_REQUIRED_FIELDS
    missing = [key for key in required_fields if not fields.get(key, "").strip()]
    if missing:
        raise ValueError("current report missing required canonical field(s): " + ", ".join(missing))
    identity_field = "run_id" if population == "manual" else "automation_id"
    report_id = fields[identity_field].strip()
    if report.stem.casefold() != report_id.casefold():
        raise ValueError(f"current report {identity_field} does not match filename: {report_id} != {report.stem}")
    _parse_finding_tags(fields)
    started = _parse_time(fields["started_at"])
    last_activity = _parse_time(fields["last_activity_at"])
    if started is None:
        raise ValueError("current report started_at is not a valid ISO-8601 timestamp")
    if last_activity is None:
        raise ValueError("current report last_activity_at is not a valid ISO-8601 timestamp")
    if last_activity < started:
        raise ValueError("current report last_activity_at precedes started_at")


def _validate_run_finished(fields: dict[str, str], *, report: Path | None = None) -> datetime | None:
    if str(fields.get("state") or "").strip().upper() != "RUN_FINISHED":
        return None
    population = _report_population(report=report)
    started = _parse_time(fields.get("started_at"))
    last_activity = _parse_time(fields.get("last_activity_at"))
    now = datetime.now().astimezone()
    if last_activity is not None and last_activity > now + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
        raise ValueError(
            "premature RUN_FINISHED blocked: last_activity_at is in the future; "
            "this run is NOT finished and future time cannot satisfy utilization"
        )
    if report is not None and report.parent.name.casefold() == "current":
        report_written = datetime.fromtimestamp(report.stat().st_mtime).astimezone()
        for field_name, claimed_at in (("started_at", started), ("last_activity_at", last_activity)):
            if claimed_at is not None and claimed_at > report_written + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
                raise ValueError(
                    f"premature RUN_FINISHED blocked: {field_name} occurs after report file write time; "
                    "this run is NOT finished and activity not yet evidenced by the report file cannot satisfy utilization"
                )
    if population == "manual":
        return None
    if report is None or report.parent.name.casefold() != "current":
        observed_started = started
    else:
        observed_started, _ = _load_timed_start_receipt(report, fields)
    finished = last_activity
    if observed_started is None or finished is None:
        return observed_started
    duration_minutes = (finished - observed_started).total_seconds() / 60.0
    utilization_pct = duration_minutes / TARGET_RUN_MINUTES * 100.0
    if utilization_pct >= MIN_RUN_FINISH_UTILIZATION_PCT:
        return observed_started

    reason = str(fields.get("stop_reason") or "").strip().casefold()
    if any(marker in reason for marker in USER_END_MARKERS):
        return observed_started
    if reason and all(marker in reason for marker in PROVEN_NO_SAFE_WORK_MARKERS):
        if started is not None and observed_started <= started + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
            return observed_started
        raise ValueError(
            "premature RUN_FINISHED rejected: a true no-safe-work exception requires machine start evidence "
            "registered near run start; late begin cannot establish early-stop eligibility"
        )

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


def _derived_metadata(fields: dict[str, str], *, digest: str, archive_path: Path, population: str, observed_started_at: datetime | None = None) -> dict[str, Any]:
    started_at = fields.get("started_at")
    finished_at = fields.get("finished_at") or fields.get("last_activity_at")
    reported_started = _parse_time(started_at)
    started = observed_started_at or reported_started
    finished = _parse_time(finished_at)
    duration_seconds = None
    if started is not None and finished is not None:
        seconds = (finished - started).total_seconds()
        if seconds >= 0:
            duration_seconds = round(seconds, 3)
    duration_minutes = round(duration_seconds / 60, 2) if duration_seconds is not None else None
    display_label = fields.get("display_label") or fields.get("worker")
    metadata: dict[str, Any] = {
        "schema": "worker-report-history.v6",
        "population": population,
        "report_sha256": digest,
        "automation_id": fields.get("automation_id"),
        "run_id": fields.get("run_id"),
        "display_label": display_label,
        "worker": display_label or fields.get("run_id") or "unknown",
        "state": fields.get("state"),
        "started_at": started_at,
        "observed_started_at": observed_started_at.isoformat() if observed_started_at is not None else None,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "repo": fields.get("repo"),
        "scope": fields.get("scope"),
        "outcome": fields.get("outcome"),
        "mutation": fields.get("mutation") or fields.get("mutations"),
        "validation": fields.get("validation"),
        "last_event": fields.get("last_event"),
        "remaining_gate": fields.get("remaining_gate") or fields.get("remaining_heavy_gate"),
        "stop_reason": fields.get("stop_reason"),
        "finding_tags": _parse_finding_tags(fields),
        "findings": fields.get("findings"),
        "visual_proof_run": fields.get("visual_proof_run"),
        "visual_proof_claim": fields.get("visual_proof_claim"),
        "visual_proof_review": fields.get("visual_proof_review"),
        "visual_proof_reviewed_json": fields.get("visual_proof_reviewed_json"),
        "reported_fields": fields,
        "archived_at": datetime.now().astimezone().isoformat(),
        "archive_path": str(archive_path),
    }
    if population == "timed":
        metadata["target_run_minutes"] = TARGET_RUN_MINUTES
        metadata["target_utilization_pct"] = (
            round(duration_minutes / TARGET_RUN_MINUTES * 100, 1) if duration_minutes is not None else None
        )
    return metadata


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


def _history_chronology_is_plausible(item: dict[str, Any]) -> bool:
    finished = _parse_time(item.get("finished_at"))
    archived = _parse_time(item.get("archived_at"))
    if finished is None or archived is None:
        return True
    return finished <= archived + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS)


def build_metrics_projection(history_root: Path, *, hours: float = 24.0) -> dict[str, Any]:
    population = _report_population(history_root=history_root)
    now = datetime.now().astimezone()
    cutoff = now - timedelta(hours=hours)
    records: list[dict[str, Any]] = []
    for item in load_history_metadata(history_root):
        if _metadata_population(item) != population:
            continue
        archived = _parse_time(item.get("archived_at"))
        if archived is not None and archived >= cutoff and _history_chronology_is_plausible(item):
            records.append(item)

    durations = [float(item["duration_minutes"]) for item in records if isinstance(item.get("duration_minutes"), (int, float))]
    tag_counts: Counter[str] = Counter()
    for item in records:
        for tag in item.get("finding_tags") or []:
            tag_counts[str(tag)] += 1
    records.sort(key=lambda item: _parse_time(item.get("archived_at")) or datetime.min.astimezone())
    latest = []
    for item in reversed(records[-20:]):
        row = {
            "report_sha256": item.get("report_sha256"),
            "population": population,
            "automation_id": item.get("automation_id"),
            "run_id": item.get("run_id"),
            "display_label": item.get("display_label") or item.get("worker"),
            "archived_at": item.get("archived_at"),
            "finished_at": item.get("finished_at"),
            "duration_minutes": item.get("duration_minutes"),
            "repo": item.get("repo"),
            "scope": item.get("scope"),
            "state": item.get("state"),
            "outcome": item.get("outcome"),
            "stop_reason": item.get("reported_stop_reason") or item.get("stop_reason"),
            "finding_tags": item.get("finding_tags") or [],
            "findings": item.get("findings"),
        }
        if population == "timed":
            row["target_utilization_pct"] = item.get("target_utilization_pct")
        latest.append(row)

    metrics: dict[str, Any] = {
        "schema": "worker-report-metrics.v1" if population == "timed" else "manual-worker-report-metrics.v1",
        "population": population,
        "generated_at": now.isoformat(),
        "window_hours": hours,
        "reports": len(records),
        "runs_with_duration": len(durations),
        "total_duration_minutes": round(sum(durations), 2) if durations else 0.0,
        "average_duration_minutes": round(statistics.mean(durations), 2) if durations else None,
        "median_duration_minutes": round(statistics.median(durations), 2) if durations else None,
        "min_duration_minutes": round(min(durations), 2) if durations else None,
        "max_duration_minutes": round(max(durations), 2) if durations else None,
        "finding_tag_counts": dict(sorted(tag_counts.items())),
        "latest_reports": latest,
    }
    if population == "timed":
        utilizations = [float(item["target_utilization_pct"]) for item in records if isinstance(item.get("target_utilization_pct"), (int, float))]
        metrics["average_target_utilization_pct"] = round(statistics.mean(utilizations), 1) if utilizations else None
    return metrics


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
    population = _report_population(history_root=history_root)
    events: list[dict[str, Any]] = []
    for item in load_history_metadata(history_root):
        if _metadata_population(item) != population:
            continue
        if not _history_chronology_is_plausible(item):
            continue
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
            "population": population,
            "automation_id": item.get("automation_id"),
            "run_id": item.get("run_id"),
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
            "finding_tags": item.get("finding_tags") or [],
            "findings": item.get("findings"),
            "visual_proof_run": item.get("visual_proof_run"),
            "visual_proof_review": item.get("visual_proof_review"),
            "refs": [value for value in (scope, mutation) if value],
        })
    return events


def archive_finalized_report(report: Path, history_root: Path) -> dict[str, Any]:
    population = _report_population(report=report)
    history_population = _report_population(history_root=history_root)
    if report.parent.name.casefold() == "current" and population != history_population:
        raise ValueError(f"report/history population mismatch: report={population} history={history_population}")
    raw = report.read_bytes()
    fields = _fields(raw)
    _validate_current_report(report, fields, raw)
    observed_started_at: datetime | None = None
    try:
        observed_started_at = _validate_run_finished(fields, report=report)
    except ValueError:
        # A rejected premature finalization means the live run is still active. Keep the
        # canonical current report truthful even if RUN_FINISHED was written first.
        if report.parent.name.casefold() == "current" and str(fields.get("state") or "").strip().upper() == "RUN_FINISHED":
            marker = b"state: RUN_FINISHED"
            if marker in raw:
                tmp = report.with_name(report.name + ".continuation.tmp")
                try:
                    updated = raw.replace(marker, b"state: RUNNING", 1)
                    lines = updated.splitlines(keepends=True)
                    for index, line in enumerate(lines):
                        if line.startswith(b"stop_reason:"):
                            ending = b"\r\n" if line.endswith(b"\r\n") else (b"\n" if line.endswith(b"\n") else b"")
                            lines[index] = b"stop_reason: " + CONTINUATION_STOP_REASON.encode("utf-8") + ending
                            break
                    tmp.write_bytes(b"".join(lines))
                    tmp.replace(report)
                except OSError:
                    try:
                        tmp.unlink(missing_ok=True)
                    except OSError:
                        pass
        raise
    if (
        str(fields.get("state") or "").strip().upper() == "RUN_FINISHED"
        and str(fields.get("stop_reason") or "").strip().casefold() == CONTINUATION_STOP_REASON.casefold()
    ):
        raise ValueError(
            "RUN_FINISHED report still has the continuation stop_reason sentinel; "
            "replace it with a truthful terminal stop_reason before archiving"
        )
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
        metadata = _derived_metadata(
            fields, digest=digest, archive_path=target, population=population, observed_started_at=observed_started_at
        )
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metrics_path, metrics = write_metrics_projection(history_root)
    if observed_started_at is not None and report.parent.name.casefold() == "current":
        _timed_start_receipt_path(report).unlink(missing_ok=True)
    result = {
        "ok": True,
        "population": population,
        "archived": archived,
        "deduplicated": not archived,
        "metadata_created": metadata_created,
        "sha256": digest,
        "path": str(target),
        "metadata_path": str(metadata_path),
        "duration_minutes": metadata.get("duration_minutes"),
        "finding_tags": metadata.get("finding_tags") or [],
        "stop_reason": metadata.get("reported_stop_reason") or metadata.get("stop_reason"),
        "metrics_path": str(metrics_path),
    }
    if population == "timed":
        result["target_run_minutes"] = metadata.get("target_run_minutes")
        result["target_utilization_pct"] = metadata.get("target_utilization_pct")
        result["fleet_average_utilization_pct"] = metrics.get("average_target_utilization_pct")
    else:
        result["manual_average_duration_minutes"] = metrics.get("average_duration_minutes")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preserve finalized worker reports as immutable content-addressed history.")
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("begin")
    begin.add_argument("--report", type=Path, required=True)
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
        if args.command == "begin":
            result = begin_timed_run(args.report)
        else:
            history_root = args.history_root or _default_history_root(args.report)
            result = archive_finalized_report(args.report, history_root)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
