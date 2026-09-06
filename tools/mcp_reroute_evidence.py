#!/usr/bin/env python3
"""Verify that reroute incident memories claiming routing-log evidence are actually linked."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MEMORY = ROOT / "memory" / "memory-bank.jsonl"
DEFAULT_ROUTING = ROOT / "02 Evidence" / "mcp-security-routing-events.jsonl"
DEFAULT_MAX_BYTES = 8 * 1024 * 1024


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def load_jsonl(path: Path, max_bytes: int = DEFAULT_MAX_BYTES) -> list[dict[str, Any]]:
    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"{path} exceeds bounded verifier limit: {size} > {max_bytes} bytes")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSONL at {path}:{line_number}: {exc.msg}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"non-object JSONL row at {path}:{line_number}")
            rows.append(row)
    return rows


def _cites_routing_log(memory: dict[str, Any], routing_path: Path) -> bool:
    target = routing_path.name.casefold()
    evidence = memory.get("evidence")
    if not isinstance(evidence, list):
        return False
    return any(isinstance(item, str) and target in item.replace("\\", "/").casefold() for item in evidence)


def requires_routing_link(memory: dict[str, Any], routing_path: Path = DEFAULT_ROUTING) -> bool:
    tags = {str(tag).casefold() for tag in (memory.get("tags") or [])}
    sources = memory.get("source_messages")
    return (
        "security_incident" in tags
        and "reroute" in tags
        and isinstance(sources, list)
        and any(isinstance(item, str) and item.strip() for item in sources)
        and _cites_routing_log(memory, routing_path)
    )


def _routing_memory_ids(row: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    direct = row.get("source_memory_id")
    if isinstance(direct, str) and direct.strip():
        result.add(direct.strip())
    many = row.get("source_memory_ids")
    if isinstance(many, list):
        result.update(str(item).strip() for item in many if isinstance(item, str) and item.strip())
    return result


def _routing_source_messages(row: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    direct = row.get("source_message")
    if isinstance(direct, str) and direct.strip():
        result.add(direct.strip())
    many = row.get("source_messages")
    if isinstance(many, list):
        result.update(str(item).strip() for item in many if isinstance(item, str) and item.strip())
    context = row.get("conversation_context")
    if isinstance(context, dict):
        for key, value in context.items():
            if str(key).startswith("source_message") and isinstance(value, str) and value.strip():
                result.add(value.strip())
    return result


def routing_link_for_memory(
    memory: dict[str, Any],
    routes: list[dict[str, Any]],
    routing_path: Path = DEFAULT_ROUTING,
    *,
    report_time_tolerance_seconds: int = 600,
) -> bool:
    if not requires_routing_link(memory, routing_path):
        return True
    memory_id = memory.get("id")
    if isinstance(memory_id, str) and memory_id.strip():
        if any(memory_id in _routing_memory_ids(row) for row in routes):
            return True
    memory_time = _timestamp(memory.get("timestamp"))
    source_messages = {str(item).strip() for item in (memory.get("source_messages") or []) if isinstance(item, str) and item.strip()}
    if memory_time is None or not source_messages:
        return False
    for row in routes:
        if not source_messages.intersection(_routing_source_messages(row)):
            continue
        reported = _timestamp(row.get("reported_at"))
        if reported is None:
            continue
        if abs((reported - memory_time).total_seconds()) <= report_time_tolerance_seconds:
            return True
    return False


def verify(
    memory_path: Path = DEFAULT_MEMORY,
    routing_path: Path = DEFAULT_ROUTING,
    *,
    since: datetime | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    memories = load_jsonl(memory_path, max_bytes=max_bytes)
    routes = load_jsonl(routing_path, max_bytes=max_bytes)
    required: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    linked_count = 0
    for memory in memories:
        if not requires_routing_link(memory, routing_path):
            continue
        observed = _timestamp(memory.get("timestamp"))
        item = {"id": memory.get("id"), "timestamp": memory.get("timestamp")}
        if since is not None:
            if observed is None:
                required.append(item)
                missing.append({**item, "reason": "invalid_or_timezone_missing_timestamp"})
                continue
            if observed < since:
                continue
        required.append(item)
        memory_id = memory.get("id")
        if not isinstance(memory_id, str) or not memory_id.strip():
            missing.append({**item, "reason": "missing_memory_id"})
        elif not routing_link_for_memory(memory, routes, routing_path):
            missing.append({**item, "reason": "routing_log_missing_matching_event"})
        else:
            linked_count += 1

    return {
        "schema": "mcp-reroute-evidence-integrity.v1",
        "status": "PASS" if not missing else "FAIL",
        "memory_path": str(memory_path),
        "routing_path": str(routing_path),
        "required_incident_count": len(required),
        "linked_incident_count": linked_count,
        "missing": missing,
        "bounded_max_bytes": max_bytes,
        "since": since.isoformat() if since is not None else None,
        "rule": "security_incident+reroute memories with source_messages that cite the canonical routing JSONL must match a routing row by source_memory_id, or exact source message within 10 minutes of report time",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("verify", help="verify bounded memory-to-routing-log incident links")
    check.add_argument("--memory-path", type=Path, default=DEFAULT_MEMORY)
    check.add_argument("--routing-path", type=Path, default=DEFAULT_ROUTING)
    check.add_argument("--since", help="optional ISO-8601 lower bound on memory timestamp")
    check.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    if args.command != "verify":
        raise AssertionError(args.command)
    since = _timestamp(args.since) if args.since else None
    if args.since and since is None:
        parser.error("--since must be a valid ISO-8601 timestamp")
    if args.max_bytes < 1:
        parser.error("--max-bytes must be >= 1")
    try:
        report = verify(args.memory_path, args.routing_path, since=since, max_bytes=args.max_bytes)
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema": "mcp-reroute-evidence-integrity.v1", "status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
