from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def nearest_rank(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def numeric_summary(values: Iterable[float]) -> dict[str, float | int | None]:
    ordered = [float(value) for value in values]
    if not ordered:
        return {"count": 0, "median": None, "p95": None, "max": None}
    return {
        "count": len(ordered),
        "median": round(statistics.median(ordered), 3),
        "p95": round(nearest_rank(ordered, 0.95) or 0.0, 3),
        "max": round(max(ordered), 3),
    }


def load_jsonl(path: Path) -> tuple[list[dict[str, object]], int]:
    events: list[dict[str, object]] = []
    parse_errors = 0
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if not isinstance(record, dict):
                parse_errors += 1
                continue
            events.append(record)
    return events, parse_errors


def summarize_events(
    label: str,
    events: list[dict[str, object]],
    *,
    parse_errors: int = 0,
    since: datetime | None = None,
) -> dict[str, object]:
    filtered: list[tuple[datetime, dict[str, object]]] = []
    undated_events = 0
    for event in events:
        at = parse_timestamp(event.get("at"))
        if at is None:
            undated_events += 1
            continue
        if since is not None and at < since:
            continue
        filtered.append((at, event))
    filtered.sort(key=lambda item: item[0])

    tool_calls: list[tuple[datetime, dict[str, object]]] = []
    successful_tool_calls: list[tuple[datetime, dict[str, object]]] = []
    tool_durations: list[float] = []
    by_tool: dict[str, Counter[str]] = {}
    caller_ids: set[str] = set()
    status_counts: Counter[str] = Counter()

    for at, event in filtered:
        if event.get("event") != "response_finish" or event.get("mcp_method") != "tools/call":
            continue
        tool_calls.append((at, event))
        status = event.get("status")
        success = isinstance(status, int) and 200 <= status < 300
        status_counts[str(status) if status is not None else "missing"] += 1
        if success:
            successful_tool_calls.append((at, event))
        tool = str(event.get("mcp_tool") or "unknown")
        counts = by_tool.setdefault(tool, Counter())
        counts["total"] += 1
        counts["success" if success else "http_error"] += 1
        duration = event.get("duration_ms")
        if isinstance(duration, (int, float)):
            tool_durations.append(float(duration))
        caller = event.get("caller_id")
        if isinstance(caller, str) and caller:
            caller_ids.add(caller)

    event_counts = Counter(str(event.get("event") or "unknown") for _, event in filtered)
    connection_errors = [at for at, event in filtered if event.get("event") == "connection_error"]
    recovery_seconds: list[float] = []
    recovered_connection_errors = 0
    for error_at in connection_errors:
        next_success = next((success_at for success_at, _ in successful_tool_calls if success_at > error_at), None)
        if next_success is not None:
            recovered_connection_errors += 1
            recovery_seconds.append((next_success - error_at).total_seconds())

    process_events = [event for _, event in filtered]
    cross_live_reads = sum(
        1
        for event in process_events
        if event.get("event") == "process_read"
        and event.get("caller_id")
        and event.get("owner_caller_id")
        and event.get("caller_id") != event.get("owner_caller_id")
    )
    cross_receipt_reads = sum(
        1
        for event in process_events
        if event.get("event") == "process_receipt_read"
        and event.get("caller_id")
        and event.get("owner_caller_id")
        and event.get("caller_id") != event.get("owner_caller_id")
    )
    kill_requested_ids = {
        str(event.get("process_id"))
        for event in process_events
        if event.get("event") == "process_kill_requested" and event.get("process_id")
    }
    killed_ids = {
        str(event.get("process_id"))
        for event in process_events
        if event.get("event") == "process_killed" and event.get("process_id")
    }
    kill_incomplete_ids = {
        str(event.get("process_id"))
        for event in process_events
        if event.get("event") == "process_kill_incomplete" and event.get("process_id")
    }

    total = len(tool_calls)
    success = len(successful_tool_calls)
    first_at = filtered[0][0].isoformat() if filtered else None
    last_at = filtered[-1][0].isoformat() if filtered else None

    return {
        "label": label,
        "window": {"first_at": first_at, "last_at": last_at, "events": len(filtered)},
        "input_quality": {"json_parse_errors": parse_errors, "undated_events_skipped": undated_events},
        "tool_calls": {
            "total": total,
            "success": success,
            "http_errors": total - success,
            "success_rate": round(success / total, 6) if total else None,
            "caller_count": len(caller_ids),
            "by_status": dict(sorted(status_counts.items())),
            "by_tool": {name: dict(sorted(counts.items())) for name, counts in sorted(by_tool.items())},
        },
        "connections": {
            "opened": event_counts["connection_open"],
            "closed": event_counts["connection_close"],
            "ended": event_counts["connection_end"],
            "errors": event_counts["connection_error"],
            "error_per_open": round(event_counts["connection_error"] / event_counts["connection_open"], 6)
            if event_counts["connection_open"]
            else None,
        },
        "process_lifecycle": {
            "started": event_counts["process_started"],
            "exit_observed": event_counts["process_exit_observed"],
            "receipt_persisted": event_counts["process_receipt_persisted"],
            "reads": event_counts["process_read"],
            "receipt_reads": event_counts["process_receipt_read"],
            "cross_caller_live_reads": cross_live_reads,
            "cross_caller_receipt_reads": cross_receipt_reads,
            "kill_requested": len(kill_requested_ids),
            "killed": len(killed_ids),
            "kill_incomplete": len(kill_incomplete_ids),
            "outstanding_kill_requests": len(kill_requested_ids - killed_ids - kill_incomplete_ids),
            "unmatched_kills": len(killed_ids - kill_requested_ids),
        },
        "mcp_server_duration_ms": numeric_summary(tool_durations),
        "same_backend_recovery": {
            "scope": "next successful tool call on the same owned MCP backend after connection_error",
            "connection_errors": len(connection_errors),
            "recovered": recovered_connection_errors,
            "seconds": numeric_summary(recovery_seconds),
        },
        "latency_scope": "mcp_server_only",
        "end_to_end_wall_time_available": False,
    }


def default_sources() -> list[tuple[str, Path]]:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []
    root = Path(local_app_data) / "ChatGPTMcpClean"
    candidates = [
        ("root", root / ".state" / "transport.jsonl"),
        ("clone-a", root / "minimal-connectors" / "clone-a" / "transport.jsonl"),
        ("clone-b", root / "minimal-connectors" / "clone-b" / "transport.jsonl"),
    ]
    return [(label, path) for label, path in candidates if path.exists()]


def parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("source must be LABEL=PATH")
    label, raw_path = value.split("=", 1)
    label = label.strip()
    raw_path = raw_path.strip()
    if not label or not raw_path:
        raise argparse.ArgumentTypeError("source must be LABEL=PATH")
    return label, Path(raw_path)


def build_report(
    sources: list[tuple[str, Path]],
    *,
    since: datetime | None = None,
    last_hours: float | None = None,
) -> dict[str, object]:
    loaded: list[tuple[str, Path, list[dict[str, object]], int]] = []
    timestamps: list[datetime] = []
    for label, path in sources:
        events, parse_errors = load_jsonl(path)
        loaded.append((label, path, events, parse_errors))
        timestamps.extend(at for event in events if (at := parse_timestamp(event.get("at"))) is not None)

    cutoff = since
    if last_hours is not None:
        if last_hours <= 0:
            raise ValueError("last_hours must be > 0")
        latest = max(timestamps) if timestamps else None
        cutoff = latest - timedelta(hours=last_hours) if latest else None

    return {
        "schema_version": 1,
        "cutoff": cutoff.isoformat() if cutoff else None,
        "sources": [
            summarize_events(label, events, parse_errors=parse_errors, since=cutoff)
            for label, _path, events, parse_errors in loaded
        ],
        "interpretation": {
            "scope": "owned MCP server telemetry only",
            "wall_time": "not derivable from transport.jsonl; collect externally and keep separate",
            "ranking": "no connector ranking or hidden-upstream inference is produced",
        },
    }


def format_text(report: dict[str, object]) -> str:
    lines = []
    cutoff = report.get("cutoff")
    if cutoff:
        lines.append(f"cutoff={cutoff}")
    for source in report["sources"]:  # type: ignore[index]
        assert isinstance(source, dict)
        tools = source["tool_calls"]
        connections = source["connections"]
        lifecycle = source["process_lifecycle"]
        duration = source["mcp_server_duration_ms"]
        recovery = source["same_backend_recovery"]
        assert isinstance(tools, dict) and isinstance(connections, dict)
        assert isinstance(lifecycle, dict) and isinstance(duration, dict) and isinstance(recovery, dict)
        rate = tools["success_rate"]
        rate_text = "n/a" if rate is None else f"{float(rate) * 100:.2f}%"
        lines.append(
            f"{source['label']}: tools={tools['success']}/{tools['total']} ({rate_text}) "
            f"http_errors={tools['http_errors']} connection_errors={connections['errors']}/{connections['opened']}opens "
            f"cross_reads={lifecycle['cross_caller_live_reads']} cross_receipts={lifecycle['cross_caller_receipt_reads']} "
            f"kills={lifecycle['killed']}/{lifecycle['kill_requested']} incomplete={lifecycle['kill_incomplete']} "
            f"outstanding_kill_requests={lifecycle['outstanding_kill_requests']} "
            f"mcp_ms_median={duration['median']} p95={duration['p95']} max={duration['max']} "
            f"same_backend_recovery={recovery['recovered']}/{recovery['connection_errors']}"
        )
    lines.append("NOTE: mcp_ms values are MCP-server handling only; end-to-end wall time is not present in these logs.")
    lines.append("NOTE: this report does not rank connectors or infer hidden upstream behavior.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize reliability from MCP transport logs we operate without probing external infrastructure."
    )
    parser.add_argument("--source", action="append", type=parse_source, help="LABEL=PATH; repeat for multiple backends")
    window = parser.add_mutually_exclusive_group()
    window.add_argument("--since", help="ISO-8601 cutoff")
    window.add_argument("--last-hours", type=float, help="deterministic window relative to the newest event in supplied logs")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of compact text")
    args = parser.parse_args()

    sources = args.source or default_sources()
    if not sources:
        parser.error("no transport logs found; pass --source LABEL=PATH")
    missing = [str(path) for _label, path in sources if not path.exists()]
    if missing:
        parser.error("missing source(s): " + ", ".join(missing))
    since = parse_timestamp(args.since) if args.since else None
    if args.since and since is None:
        parser.error("--since must be valid ISO-8601")

    report = build_report(sources, since=since, last_hours=args.last_hours)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
