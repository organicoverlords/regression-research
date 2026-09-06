from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
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
IN_SCOPE_FINISH_MARKERS = ("selected acceptance complete", "no in-scope work remains")
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
    "run_id", "started_at", "last_activity_at", "repo", "state", "outcome",
)
ALLOWED_FINDING_TAGS = frozenset({
    "bug", "error", "regression", "wrapper_anomaly", "route_problem", "contention",
    "performance", "improvement", "tooling", "ci", "build", "proof", "resource", "other",
})
FINDING_TAG_ALIASES = {
    "collision": "contention",
    "resource_issue": "resource",
    "proof_gap": "proof",
    "convergence": "improvement",
    "product": "other",
}

MANUAL_SANITY_BASELINE_PATH = Path(__file__).resolve().parents[1] / "04 Operating Contracts" / "manual-worker-sanity-baseline.json"
MANUAL_SANITY_TRANSCRIPT_FIELDS = ("scope", "mutation", "validation", "remaining_gate")
MANUAL_SANITY_LIFECYCLE_RE = re.compile(
    r"opened late|created late|left tool_interval_open|incorrectly left|not opened before|lifecycle gap|report creation occurred after",
    re.IGNORECASE,
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
    receipt_reported_started = _parse_time(str(payload.get("reported_started_at") or ""))
    reported_started = _parse_time(fields.get("started_at"))
    if observed_started is None or receipt_reported_started is None or reported_started is None:
        raise ValueError("timed run start receipt contains invalid chronology")
    receipt_written = datetime.fromtimestamp(receipt_path.stat().st_mtime).astimezone()
    if abs((observed_started - receipt_written).total_seconds()) > MAX_FUTURE_ACTIVITY_SKEW_SECONDS:
        raise ValueError("timed run start receipt observed time does not match receipt file write time")
    if abs((reported_started - receipt_reported_started).total_seconds()) > MAX_FUTURE_ACTIVITY_SKEW_SECONDS:
        raise ValueError("reported started_at changed after timed run begin")
    now = datetime.now().astimezone()
    if observed_started > now + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
        raise ValueError("timed run start receipt is in the future")
    if reported_started > observed_started + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
        raise ValueError(
            "timed run start receipt is stale for this generation: reported started_at is later than observed start"
        )
    return observed_started, receipt_path


def _proof_navigation_scalar(value: str | None) -> str | None:
    """Decode quoted report scalars for navigation while preserving ordinary values."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith('"') and raw.endswith('"'):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError:
            decoded = raw[1:-1]
        if isinstance(decoded, str) and decoded.strip():
            return decoded.strip()
    return raw


def _proof_artifact_fields(fields: dict[str, str]) -> tuple[str | None, str | None]:
    """Normalize report-owned proof artifact navigation without implying acceptance."""
    artifact = _proof_navigation_scalar(
        fields.get("proof_artifact") or fields.get("proof_index") or fields.get("video_manifest")
    )
    sha256 = _proof_navigation_scalar(fields.get("proof_artifact_sha256") or fields.get("proof_index_sha256"))
    return artifact, sha256


def _parse_finding_tags(fields: dict[str, str]) -> list[str]:
    raw = str(fields.get("finding_tags") or "").strip()
    if not raw or raw.casefold() == "none":
        return []
    normalized = {part.strip().casefold().replace("-", "_").replace(" ", "_") for part in raw.split(",") if part.strip()}
    tags = sorted({FINDING_TAG_ALIASES.get(tag, tag) for tag in normalized})
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
    if reason and any(marker in reason for marker in IN_SCOPE_FINISH_MARKERS):
        if started is not None and observed_started <= started + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS):
            return observed_started
        raise ValueError(
            "premature RUN_FINISHED rejected: early in-scope completion requires machine start evidence "
            "registered near run start; late begin cannot establish early-stop eligibility"
        )
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
            "Local contention alone is not an early-finish reason. Continue only work already required by the selected acceptance, "
            "or use a truthful terminal stop_reason containing 'no in-scope work remains' when that acceptance has no remaining in-scope action. "
            "Do not switch to adjacent work merely to reach the utilization target."
        )
    raise ValueError(
        "premature RUN_FINISHED rejected: this run is NOT finished and this report was NOT archived. "
        "Under 80% utilization, continue only the already-selected in-scope acceptance. If that acceptance is complete or has no remaining "
        "in-scope work, use a truthful terminal stop_reason containing 'selected acceptance complete' or 'no in-scope work remains'. "
        "Do not select adjacent work merely to satisfy utilization."
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
    proof_artifact, proof_artifact_sha256 = _proof_artifact_fields(fields)
    metadata: dict[str, Any] = {
        "schema": "worker-report-history.v6",
        "population": population,
        "report_sha256": digest,
        "automation_id": fields.get("automation_id"),
        "run_id": fields.get("run_id"),
        "run_mode": fields.get("run_mode"),
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
        "proof_artifact": proof_artifact,
        "proof_artifact_sha256": proof_artifact_sha256,
        "visual_proof_run": fields.get("visual_proof_run"),
        "visual_proof_claim": fields.get("visual_proof_claim"),
        "visual_proof_review": fields.get("visual_proof_review"),
        "visual_proof_reviewed_json": fields.get("visual_proof_reviewed_json"),
        "reported_fields": fields,
        "report_bytes": archive_path.stat().st_size if archive_path.exists() else None,
        "report_lines": len(archive_path.read_bytes().splitlines()) if archive_path.exists() else None,
        "manual_transcript_field_count": sum(bool(str(fields.get(key) or "").strip()) for key in MANUAL_SANITY_TRANSCRIPT_FIELDS) if population == "manual" else None,
        "archived_at": datetime.now().astimezone().isoformat(),
        "archive_path": str(archive_path),
    }
    if population == "timed":
        metadata["target_run_minutes"] = TARGET_RUN_MINUTES
        metadata["target_utilization_pct"] = (
            round(duration_minutes / TARGET_RUN_MINUTES * 100, 1) if duration_minutes is not None else None
        )
    return metadata


def load_history_metadata(history_root: Path, *, since: datetime | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    canonical_root = history_root / "_reports"
    if not canonical_root.exists():
        return records
    cutoff = since.timestamp() if since is not None else None
    for path in sorted(canonical_root.glob("*.json")):
        if cutoff is not None:
            try:
                if path.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("schema") or "").startswith("worker-report-history.v"):
            reported_fields = payload.get("reported_fields")
            if isinstance(reported_fields, dict):
                proof_artifact, proof_artifact_sha256 = _proof_artifact_fields(reported_fields)
                if proof_artifact and not payload.get("proof_artifact"):
                    payload["proof_artifact"] = proof_artifact
                if proof_artifact_sha256 and not payload.get("proof_artifact_sha256"):
                    payload["proof_artifact_sha256"] = proof_artifact_sha256
            records.append(payload)
    return records


def _history_chronology_is_plausible(item: dict[str, Any]) -> bool:
    finished = _parse_time(item.get("finished_at"))
    archived = _parse_time(item.get("archived_at"))
    if finished is None or archived is None:
        return True
    return finished <= archived + timedelta(seconds=MAX_FUTURE_ACTIVITY_SKEW_SECONDS)


def _dedupe_manual_run_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one deterministic newest valid archive per logical manual run_id."""
    selected: dict[str, dict[str, Any]] = {}
    anonymous: list[dict[str, Any]] = []
    for item in records:
        run_id = str(item.get("run_id") or "").strip().casefold()
        if not run_id:
            anonymous.append(item)
            continue
        previous = selected.get(run_id)
        if previous is None:
            selected[run_id] = item
            continue
        item_key = (_parse_time(item.get("archived_at")) or datetime.min.replace(tzinfo=timezone.utc), str(item.get("report_sha256") or ""))
        previous_key = (_parse_time(previous.get("archived_at")) or datetime.min.replace(tzinfo=timezone.utc), str(previous.get("report_sha256") or ""))
        if item_key > previous_key:
            selected[run_id] = item
    return anonymous + list(selected.values())


def _load_manual_sanity_baseline(path: Path = MANUAL_SANITY_BASELINE_PATH) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _manual_report_shape(item: dict[str, Any]) -> dict[str, Any]:
    fields = item.get("reported_fields") if isinstance(item.get("reported_fields"), dict) else {}
    transcript_count = sum(bool(str(fields.get(key) or "").strip()) for key in MANUAL_SANITY_TRANSCRIPT_FIELDS)
    report_bytes = item.get("report_bytes")
    report_lines = item.get("report_lines")
    archive_path = item.get("archive_path")
    raw = b""
    if archive_path and (not isinstance(report_bytes, (int, float)) or not isinstance(report_lines, (int, float))):
        try:
            raw = Path(str(archive_path)).read_bytes()
        except OSError:
            raw = b""
    if not isinstance(report_bytes, (int, float)):
        report_bytes = len(raw) if raw else None
    if not isinstance(report_lines, (int, float)):
        report_lines = len(raw.splitlines()) if raw else None
    text = " ".join(
        [str(item.get("outcome") or ""), str(item.get("findings") or ""), *[str(value or "") for value in fields.values()]]
    )
    duration = item.get("duration_minutes")
    return {
        "report_bytes": float(report_bytes) if isinstance(report_bytes, (int, float)) else None,
        "report_lines": float(report_lines) if isinstance(report_lines, (int, float)) else None,
        "transcript_field_count": float(transcript_count),
        "self_reported_lifecycle_anomaly": bool(MANUAL_SANITY_LIFECYCLE_RE.search(text)),
        "duration_minutes": float(duration) if isinstance(duration, (int, float)) else None,
    }


def _manual_sanity_observation(records: list[dict[str, Any]]) -> dict[str, Any]:
    shapes = [_manual_report_shape(item) for item in records]
    report_bytes = [item["report_bytes"] for item in shapes if item["report_bytes"] is not None]
    transcript_fields = [item["transcript_field_count"] for item in shapes]
    durations = [item["duration_minutes"] for item in shapes if item["duration_minutes"] is not None]
    return {
        "run_count": len(records),
        "median_report_bytes": round(statistics.median(report_bytes), 2) if report_bytes else None,
        "mean_transcript_fields": round(statistics.mean(transcript_fields), 2) if transcript_fields else None,
        "self_reported_lifecycle_anomaly_pct": round(
            100.0 * sum(bool(item["self_reported_lifecycle_anomaly"]) for item in shapes) / len(shapes), 2
        ) if shapes else None,
        "micro_run_lt2_pct": round(100.0 * sum(value < 2.0 for value in durations) / len(durations), 2) if durations else None,
        "short_run_lt5_pct_guardrail": round(100.0 * sum(value < 5.0 for value in durations) / len(durations), 2) if durations else None,
        "median_tool_interval_minutes_guardrail": round(statistics.median(durations), 2) if durations else None,
    }



def _manual_run_mode(item: dict[str, Any]) -> str:
    fields = item.get("reported_fields") if isinstance(item.get("reported_fields"), dict) else {}
    explicit = str(item.get("run_mode") or fields.get("run_mode") or "").strip().casefold()
    if explicit:
        return explicit
    legacy = " ".join([str(item.get("run_id") or ""), str(item.get("scope") or "")])
    if re.search(r"(?:^|[-_])go(?:\d+)?(?:$|[-_])|\bcontinue\b|\bcontinuation\b", legacy, re.IGNORECASE):
        return "continuation"
    return "task"


def _manual_continuation_observation(records: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [item for item in records if _manual_run_mode(item) == "continuation"]
    completed: list[dict[str, Any]] = []
    interrupted = 0
    for item in selected:
        stop_reason = str(item.get("stop_reason") or (item.get("reported_fields") or {}).get("stop_reason") or "").strip().casefold()
        if stop_reason in {"user_interrupted", "user_superseded"}:
            interrupted += 1
            continue
        completed.append(item)
    durations = [float(item["duration_minutes"]) for item in completed if isinstance(item.get("duration_minutes"), (int, float))]
    return {
        "identified_run_count": len(selected),
        "eligible_run_count": len(completed),
        "excluded_user_interrupted_count": interrupted,
        "median_duration_minutes": round(statistics.median(durations), 2) if durations else None,
        "short_run_lt5_pct": round(100.0 * sum(value < 5.0 for value in durations) / len(durations), 2) if durations else None,
        "micro_run_lt2_pct": round(100.0 * sum(value < 2.0 for value in durations) / len(durations), 2) if durations else None,
    }

def _manual_sanity_component(*, baseline: float, current: float, weight: float) -> float:
    if baseline <= 0:
        return 0.0
    ratio = (baseline - current) / baseline
    return round(max(-1.0, min(1.0, ratio)) * weight, 2)


def build_manual_sanity_projection(
    history_root: Path,
    *,
    baseline_path: Path = MANUAL_SANITY_BASELINE_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    baseline = _load_manual_sanity_baseline(baseline_path)
    if baseline is None:
        return {"available": False, "status": "BASELINE_MISSING", "baseline_path": str(baseline_path)}
    boundary = _parse_time(baseline.get("boundary_at"))
    if boundary is None:
        return {"available": False, "status": "BASELINE_INVALID", "baseline_path": str(baseline_path)}
    current_now = now or datetime.now().astimezone()
    if current_now.tzinfo is None:
        current_now = current_now.replace(tzinfo=timezone.utc)
    boundary = boundary.astimezone(current_now.tzinfo)
    window_hours = float(baseline.get("comparison_window_hours") or 6.0)
    window_start = max(boundary, current_now - timedelta(hours=window_hours))
    records = [
        item for item in load_history_metadata(history_root)
        if _metadata_population(item) == "manual" and _history_chronology_is_plausible(item)
    ]
    records = _dedupe_manual_run_records(records)
    post_records: list[dict[str, Any]] = []
    for item in records:
        started = _parse_time(item.get("started_at") or item.get("observed_started_at"))
        if started is None:
            continue
        started = started.astimezone(current_now.tzinfo)
        if window_start <= started <= current_now and started >= boundary:
            post_records.append(item)
    observed = _manual_sanity_observation(post_records)
    continuation_observed = _manual_continuation_observation(post_records)
    continuation_baseline = baseline.get("continuation_baseline") if isinstance(baseline.get("continuation_baseline"), dict) else {}
    continuation_gates = continuation_baseline.get("sample_gates") if isinstance(continuation_baseline.get("sample_gates"), dict) else {}
    continuation_count = int(continuation_observed.get("eligible_run_count") or 0)
    continuation_provisional_min = int(continuation_gates.get("minimum_post_runs_for_provisional") or 5)
    continuation_comparable_min = int(continuation_gates.get("minimum_post_runs_for_comparable") or 20)
    if continuation_count < continuation_provisional_min:
        continuation_status = "INSUFFICIENT_DATA"
    elif continuation_count < continuation_comparable_min:
        continuation_status = "PROVISIONAL"
    else:
        continuation_status = "COMPARABLE"
    continuation = {
        "status": continuation_status,
        "baseline_run_count": continuation_baseline.get("baseline_run_count"),
        "post_run_count": continuation_count,
        "minimum_post_runs_for_provisional": continuation_provisional_min,
        "minimum_post_runs_for_comparable": continuation_comparable_min,
        "baseline": {
            "median_duration_minutes": continuation_baseline.get("median_duration_minutes"),
            "short_run_lt5_pct": continuation_baseline.get("short_run_lt5_pct"),
            "micro_run_lt2_pct": continuation_baseline.get("micro_run_lt2_pct"),
        },
        "observation": continuation_observed,
        "semantics": "Only go/continue continuation runs. Bounded one-shot tasks and correction-only handling are not evidence that a continuation run was short.",
    }
    gates = baseline.get("sample_gates") if isinstance(baseline.get("sample_gates"), dict) else {}
    provisional_min = int(gates.get("minimum_post_runs_for_provisional") or 5)
    comparable_min = int(gates.get("minimum_post_runs_for_comparable") or 20)
    run_count = int(observed.get("run_count") or 0)
    if run_count < provisional_min:
        status = "INSUFFICIENT_DATA"
    elif run_count < comparable_min:
        status = "PROVISIONAL"
    else:
        status = "COMPARABLE"
    base_metrics = baseline.get("metrics") if isinstance(baseline.get("metrics"), dict) else {}
    axis_specs = baseline.get("axes") if isinstance(baseline.get("axes"), dict) else {}
    if not axis_specs:
        # Backward-compatible fallback for v1 baselines. Treat the former weighted sum as one axis.
        legacy_weights = baseline.get("weights") if isinstance(baseline.get("weights"), dict) else {}
        axis_specs = {"legacy": {"metrics": legacy_weights, "semantics": "legacy single-axis baseline"}}
    axes: dict[str, Any] = {}
    components: dict[str, Any] = {}
    axis_descriptive_scores: list[float] = []
    score_complete = True
    for axis_name, raw_axis in axis_specs.items():
        axis = raw_axis if isinstance(raw_axis, dict) else {}
        metric_weights = axis.get("metrics") if isinstance(axis.get("metrics"), dict) else {}
        axis_score = 0.0
        axis_complete = bool(metric_weights)
        axis_components: dict[str, Any] = {}
        for key, weight in metric_weights.items():
            b = base_metrics.get(key)
            c = observed.get(key)
            if not isinstance(b, (int, float)) or not isinstance(c, (int, float)) or not isinstance(weight, (int, float)):
                axis_complete = False
                axis_components[key] = {"baseline": b, "current": c, "weight": weight, "delta_points": None}
                components[key] = {**axis_components[key], "axis": axis_name}
                continue
            points = _manual_sanity_component(baseline=float(b), current=float(c), weight=float(weight))
            axis_score += points
            axis_components[key] = {"baseline": b, "current": c, "weight": weight, "delta_points": points}
            components[key] = {**axis_components[key], "axis": axis_name}
        descriptive = round(axis_score, 1) if axis_complete else None
        axes[axis_name] = {
            "descriptive_delta": descriptive,
            "score_delta": descriptive if status != "INSUFFICIENT_DATA" and axis_complete else None,
            "components": axis_components,
            "semantics": axis.get("semantics"),
        }
        if descriptive is not None:
            axis_descriptive_scores.append(descriptive)
        else:
            score_complete = False
    descriptive_headline = round(min(axis_descriptive_scores), 1) if axis_descriptive_scores and score_complete else None
    score_delta = descriptive_headline if status != "INSUFFICIENT_DATA" else None
    # Canonical v2+ baselines with a continuation baseline keep duration out of the mixed manual headline.
    # Retain the historical guardrail behavior only for older baselines/tests that predate run-mode separation.
    if continuation_baseline:
        guardrails: dict[str, Any] = {}
    else:
        short_base = base_metrics.get("short_run_lt5_pct_guardrail")
        short_current = observed.get("short_run_lt5_pct_guardrail")
        short_delta = (round(float(short_current) - float(short_base), 2)
                       if isinstance(short_base, (int, float)) and isinstance(short_current, (int, float)) else None)
        guardrails = {
            "short_run_lt5_pct": {
                "baseline": short_base, "current": short_current, "delta_percentage_points": short_delta,
                "status": ("REGRESSED" if short_delta is not None and short_delta > 0 else "NOT_REGRESSED") if short_delta is not None else "UNKNOWN",
                "scored": False,
            },
            "median_tool_interval_minutes": {
                "baseline": base_metrics.get("median_tool_interval_minutes_guardrail"),
                "current": observed.get("median_tool_interval_minutes_guardrail"),
                "status": "OBSERVE_ONLY", "scored": False,
            },
        }
    threshold = float((baseline.get("score_semantics") or {}).get("direction_threshold") or 10.0)
    guardrail_regressed = any(
        isinstance(item, dict) and item.get("status") == "REGRESSED" for item in guardrails.values()
    )
    if score_delta is None:
        direction = "UNKNOWN"
    elif score_delta <= -threshold:
        direction = "WORSE"
    elif guardrail_regressed:
        direction = "MIXED_GUARDRAIL_REGRESSION"
    elif score_delta >= threshold:
        direction = "IMPROVED"
    else:
        direction = "NO_CLEAR_CHANGE"
    return {
        "available": True,
        "schema": "manual-worker-sanity.v1",
        "baseline_id": baseline.get("baseline_id"),
        "baseline_label": baseline.get("label"),
        "baseline_path": str(baseline_path),
        "boundary_at": baseline.get("boundary_at"),
        "comparison_window_hours": window_hours,
        "comparison_window_start": window_start.isoformat(),
        "generated_at": current_now.isoformat(),
        "status": status,
        "score_delta": score_delta,
        "descriptive_delta": descriptive_headline,
        "direction": direction,
        "post_run_count": run_count,
        "minimum_post_runs_for_provisional": provisional_min,
        "minimum_post_runs_for_comparable": comparable_min,
        "observation": observed,
        "axes": axes,
        "guardrails": guardrails,
        "continuation": continuation,
        "components": components,
        "semantics": "0 is the fixed pre-#658 insanity baseline. General manual sanity covers reporting friction plus lifecycle mistakes. Go/continue duration and fragmentation are a separate continuation projection; bounded task/correction duration is not continuation evidence. Diagnostic only, never a worker target or gate.",
    }


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

    if population == "manual":
        records = _dedupe_manual_run_records(records)

    durations = [float(item["duration_minutes"]) for item in records if isinstance(item.get("duration_minutes"), (int, float))]
    tag_counts: Counter[str] = Counter()
    for item in records:
        for tag in item.get("finding_tags") or []:
            tag_counts[str(tag)] += 1
    records.sort(key=lambda item: _parse_time(item.get("archived_at")) or datetime.min.replace(tzinfo=timezone.utc))
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
    if population == "manual":
        metrics["sanity"] = build_manual_sanity_projection(history_root)
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


def worker_history_events(history_root: Path, *, since: datetime | None = None) -> list[dict[str, Any]]:
    population = _report_population(history_root=history_root)
    records = [
        item for item in load_history_metadata(history_root, since=since)
        if _metadata_population(item) == population and _history_chronology_is_plausible(item)
    ]
    if population == "manual":
        records = _dedupe_manual_run_records(records)
    events: list[dict[str, Any]] = []
    for item in records:
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
            "proof_artifact": item.get("proof_artifact"),
            "proof_artifact_sha256": item.get("proof_artifact_sha256"),
            "visual_proof_run": item.get("visual_proof_run"),
            "visual_proof_review": item.get("visual_proof_review"),
            "refs": [value for value in (scope, mutation, item.get("proof_artifact")) if value],
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
    if population == "manual" and report.parent.name.casefold() == "current":
        report.unlink(missing_ok=True)
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


def audit_manual_current_reports(current_root: Path, history_root: Path) -> dict[str, Any]:
    """Classify manual current reports without treating file presence as worker liveness."""
    if current_root.name.casefold() != "current" or current_root.parent.name.casefold() != "manual":
        raise ValueError("manual current audit requires worker-reports/manual/current")
    if _report_population(history_root=history_root) != "manual":
        raise ValueError("manual current audit requires worker-reports/manual/history")

    archived_run_ids = {
        str(item.get("run_id") or "").strip().casefold()
        for item in _dedupe_manual_run_records([
            item for item in load_history_metadata(history_root)
            if _metadata_population(item) == "manual" and _history_chronology_is_plausible(item)
        ])
        if str(item.get("run_id") or "").strip()
    }
    rows: list[dict[str, Any]] = []
    for report in sorted(current_root.glob("*.md")):
        raw = report.read_bytes()
        fields = _fields(raw)
        error = None
        try:
            _validate_current_report(report, fields, raw)
        except ValueError as exc:
            error = str(exc)
        run_id = str(fields.get("run_id") or report.stem).strip()
        state = str(fields.get("state") or "").strip().upper()
        archived = run_id.casefold() in archived_run_ids
        if error:
            lifecycle_status = "INVALID_CURRENT"
        elif state in {"RUNNING", "TOOL_INTERVAL_OPEN"}:
            lifecycle_status = "UNFINALIZED_OPEN"
        elif archived:
            lifecycle_status = "ARCHIVED_CURRENT_POINTER"
        else:
            lifecycle_status = "UNARCHIVED_TERMINAL"
        rows.append({
            "run_id": run_id,
            "path": str(report),
            "state": state or None,
            "last_activity_at": fields.get("last_activity_at"),
            "archived": archived,
            "lifecycle_status": lifecycle_status,
            "liveness": "NOT_ESTABLISHED_BY_REPORT",
            "error": error,
        })
    counts = Counter(row["lifecycle_status"] for row in rows)
    return {
        "ok": True,
        "population": "manual",
        "current_root": str(current_root),
        "history_root": str(history_root),
        "reports": rows,
        "counts": dict(sorted(counts.items())),
        "unfinalized_count": counts.get("UNFINALIZED_OPEN", 0),
        "unarchived_terminal_count": counts.get("UNARCHIVED_TERMINAL", 0),
        "liveness_semantics": "manual current reports are lifecycle evidence only; present worker liveness requires independent live activity evidence",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preserve finalized worker reports as immutable content-addressed history.")
    sub = parser.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("begin")
    begin.add_argument("--report", type=Path, required=True)
    archive = sub.add_parser("archive")
    archive.add_argument("--report", type=Path, required=True)
    archive.add_argument("--history-root", type=Path)
    audit = sub.add_parser("audit-manual-current")
    audit.add_argument("--current-root", type=Path, required=True)
    audit.add_argument("--history-root", type=Path, required=True)
    sanity = sub.add_parser("sanity")
    sanity.add_argument("--history-root", type=Path, required=True)
    sanity.add_argument("--baseline", type=Path, default=MANUAL_SANITY_BASELINE_PATH)
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
        elif args.command == "audit-manual-current":
            result = audit_manual_current_reports(args.current_root, args.history_root)
        elif args.command == "sanity":
            result = build_manual_sanity_projection(args.history_root, baseline_path=args.baseline)
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
