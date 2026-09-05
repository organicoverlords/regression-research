from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_ROOT = ROOT / "worker-reports"


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.astimezone()


def _parse_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lstrip("\ufeff").lower()
        if key and key.replace("_", "").isalnum():
            fields[key] = value.strip()
    return fields


def _normalize_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        text = str(value).strip()
        if not text or text.casefold() == "none":
            return []
        raw = text.split(",")
    return sorted({str(tag).strip().casefold() for tag in raw if str(tag).strip() and str(tag).strip().casefold() != "none"})


def _history_records(history_root: Path, *, population: str, cutoff: datetime) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    root = history_root / "_reports"
    if not root.exists():
        return records
    for path in root.glob("*.json"):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        recorded_population = str(item.get("population") or "timed").casefold()
        if recorded_population != population:
            continue
        archived_at = _parse_time(item.get("archived_at"))
        if archived_at is None or archived_at < cutoff:
            continue
        row = dict(item)
        row["tag_eligible"] = "finding_tags" in item
        row["finding_tags"] = _normalize_tags(item.get("finding_tags"))
        row["source"] = "history"
        row["event_at"] = item.get("finished_at") or item.get("archived_at")
        records.append(row)
    return records


def _running_records(current_root: Path, *, population: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not current_root.exists():
        return records
    for path in current_root.glob("*.md"):
        try:
            fields = _parse_fields(path)
        except OSError:
            continue
        if str(fields.get("state") or "").strip().upper() != "RUNNING":
            continue
        tags = _normalize_tags(fields.get("finding_tags"))
        records.append(
            {
                "population": population,
                "source": "current",
                "worker": fields.get("display_label") or fields.get("worker") or fields.get("run_id") or fields.get("automation_id") or path.stem,
                "automation_id": fields.get("automation_id"),
                "run_id": fields.get("run_id"),
                "state": "RUNNING",
                "scope": fields.get("scope"),
                "tag_eligible": "finding_tags" in fields,
                "finding_tags": tags,
                "findings": fields.get("findings"),
                "event_at": fields.get("last_activity_at") or fields.get("started_at"),
            }
        )
    return records


def _population_summary(history: list[dict[str, Any]], current: list[dict[str, Any]], *, population: str) -> dict[str, Any]:
    durations = [float(item["duration_minutes"]) for item in history if isinstance(item.get("duration_minutes"), (int, float))]
    eligible_history = [item for item in history if item.get("tag_eligible")]
    tagged_history = [item for item in eligible_history if item.get("finding_tags")]
    eligible_current = [item for item in current if item.get("tag_eligible")]
    tagged_current = [item for item in eligible_current if item.get("finding_tags")]
    summary: dict[str, Any] = {
        "archived_runs": len(history),
        "archived_tag_eligible_runs": len(eligible_history),
        "archived_tagged_runs": len(tagged_history),
        "archived_tagged_pct": round(len(tagged_history) / len(eligible_history) * 100, 1) if eligible_history else None,
        "average_duration_minutes": round(statistics.mean(durations), 2) if durations else None,
        "active_runs": len(current),
        "active_tag_eligible_runs": len(eligible_current),
        "active_tagged_runs": len(tagged_current),
        "active_tagged_pct": round(len(tagged_current) / len(eligible_current) * 100, 1) if eligible_current else None,
    }
    if population == "timed":
        utilizations = [float(item["target_utilization_pct"]) for item in history if isinstance(item.get("target_utilization_pct"), (int, float))]
        summary["average_target_utilization_pct"] = round(statistics.mean(utilizations), 1) if utilizations else None
    return summary


def build_summary(reports_root: Path, *, hours: float = 24.0, recent_limit: int = 20) -> dict[str, Any]:
    now = datetime.now().astimezone()
    cutoff = now - timedelta(hours=hours)
    timed_history = _history_records(reports_root / "history", population="timed", cutoff=cutoff)
    manual_history = _history_records(reports_root / "manual" / "history", population="manual", cutoff=cutoff)
    timed_current = _running_records(reports_root / "current", population="timed")
    manual_current = _running_records(reports_root / "manual" / "current", population="manual")

    finding_rows = [item for item in timed_history + manual_history + timed_current + manual_current if item.get("finding_tags")]
    counts: Counter[str] = Counter()
    for item in finding_rows:
        counts.update(item.get("finding_tags") or [])

    def sort_key(item: dict[str, Any]) -> float:
        parsed = _parse_time(item.get("event_at"))
        return parsed.timestamp() if parsed is not None else float("-inf")

    recent: list[dict[str, Any]] = []
    for item in sorted(finding_rows, key=sort_key, reverse=True)[:recent_limit]:
        recent.append(
            {
                "population": item.get("population") or "timed",
                "source": item.get("source"),
                "worker": item.get("display_label") or item.get("worker") or item.get("run_id") or item.get("automation_id"),
                "event_at": item.get("event_at"),
                "scope": item.get("scope"),
                "finding_tags": item.get("finding_tags") or [],
                "findings": item.get("findings"),
            }
        )

    return {
        "schema": "worker-findings-summary.v1",
        "generated_at": now.isoformat(),
        "window_hours": hours,
        "populations": {
            "timed": _population_summary(timed_history, timed_current, population="timed"),
            "manual": _population_summary(manual_history, manual_current, population="manual"),
        },
        "findings": {
            "tagged_records": len(finding_rows),
            "tag_counts": dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))),
            "recent": recent,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize timed and manual worker findings without mixing run statistics.")
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--recent", type=int, default=20)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.hours <= 0:
        raise SystemExit("--hours must be > 0")
    if args.recent < 0:
        raise SystemExit("--recent must be >= 0")
    print(json.dumps(build_summary(args.reports_root, hours=args.hours, recent_limit=args.recent), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
