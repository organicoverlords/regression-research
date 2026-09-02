from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TARGET_RUN_MINUTES = 24.0


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
    return {
        "schema": "worker-report-history.v2",
        "report_sha256": digest,
        "worker": fields.get("worker") or archive_path.parent.name,
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
        "visual_proof_run": fields.get("visual_proof_run"),
        "visual_proof_claim": fields.get("visual_proof_claim"),
        "visual_proof_review": fields.get("visual_proof_review"),
        "visual_proof_reviewed_json": fields.get("visual_proof_reviewed_json"),
        "archived_at": datetime.now().astimezone().isoformat(),
        "archive_path": str(archive_path),
    }


def load_history_metadata(history_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not history_root.exists():
        return records
    for path in sorted(history_root.glob("*/*.json")):
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
    records = []
    for item in load_history_metadata(history_root):
        finished = _parse_time(item.get("finished_at") or item.get("archived_at"))
        if finished is not None and finished >= cutoff:
            records.append(item)
    durations = [float(x["duration_minutes"]) for x in records if isinstance(x.get("duration_minutes"), (int, float))]
    utils = [float(x["target_utilization_pct"]) for x in records if isinstance(x.get("target_utilization_pct"), (int, float))]
    by_worker: dict[str, dict[str, Any]] = {}
    for item in sorted(records, key=lambda x: str(x.get("finished_at") or x.get("archived_at") or "")):
        worker = str(item.get("worker") or "unknown")
        by_worker[worker] = {
            "finished_at": item.get("finished_at"),
            "duration_minutes": item.get("duration_minutes"),
            "target_utilization_pct": item.get("target_utilization_pct"),
            "repo": item.get("repo"),
            "scope": item.get("scope"),
            "state": item.get("state"),
            "remaining_gate": item.get("remaining_gate"),
        }
    total_minutes = round(sum(durations), 2)
    window_minutes = hours * 60.0
    return {
        "schema": "worker-report-metrics.v1",
        "generated_at": now.isoformat(),
        "window_hours": float(hours),
        "target_run_minutes": TARGET_RUN_MINUTES,
        "captured_runs": len(records),
        "runs_with_duration": len(durations),
        "average_duration_minutes": round(statistics.mean(durations), 2) if durations else None,
        "median_duration_minutes": round(statistics.median(durations), 2) if durations else None,
        "average_target_utilization_pct": round(statistics.mean(utils), 1) if utils else None,
        "short_runs_under_75pct": sum(1 for value in utils if value < 75.0),
        "worker_minutes": total_minutes,
        "equivalent_continuous_workers": round(total_minutes / window_minutes, 3) if window_minutes else None,
        "capacity_pct_of_one_continuous_worker": round(total_minutes / window_minutes * 100.0, 1) if window_minutes else None,
        "by_worker_latest": by_worker,
    }


def write_metrics_projection(history_root: Path, output: Path | None = None, *, hours: float = 24.0) -> dict[str, Any]:
    summary = summarize_history(history_root, hours=hours)
    target = output or history_root.parent / "metrics.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def archive_finalized_report(report: Path, history_root: Path) -> dict[str, Any]:
    raw = report.read_bytes()
    fields = _fields(raw)
    state = fields.get("state", "").upper()
    if state not in {"COMPLETE", "WAITING", "BLOCKED", "DONE"}:
        raise ValueError(f"report is not finalized: state={state or 'MISSING'}")
    worker = fields.get("worker") or report.stem
    digest = hashlib.sha256(raw).hexdigest()
    target_dir = history_root / worker
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
        "fleet_metrics_path": str(history_root.parent / "metrics.json"),
        "fleet_average_utilization_pct": metrics.get("average_target_utilization_pct"),
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


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "archive":
            history_root = args.history_root or args.report.parent / "history"
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
