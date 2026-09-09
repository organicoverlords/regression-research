#!/usr/bin/env python3
"""Read-only transient-evidence watcher for safety-buffering investigations.

Archives three independently observable layers before local retention/pruning loses them:
  * matching MCP transport events for one caller,
  * optional Codex logs_2.sqlite rows for one known thread,
  * explicit operator/UI markers (for example banner_on/banner_off/stop/go).

It does not infer backend/model inactivity from MCP silence.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

UTC = dt.timezone.utc
TERMINAL_EVENTS = {"process_exit_observed", "process_killed"}


def now_iso() -> str:
    return dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def default_paths() -> tuple[Path, Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    user = Path(os.environ.get("USERPROFILE", str(Path.home())))
    transport = local / "ChatGPTMcpClean" / "minimal-connectors" / "clone-a" / "transport.jsonl"
    logs_db = user / ".codex" / "logs_2.sqlite"
    return transport, logs_db


def emit(fp, payload: dict[str, Any]) -> None:
    fp.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    fp.flush()


def ro_connect(db: Path) -> sqlite3.Connection | None:
    if not db.exists():
        return None
    try:
        uri = "file:" + str(db).replace("\\", "/") + "?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=2)
    except sqlite3.Error:
        return None


def belongs_to_caller(obj: dict[str, Any], caller: str) -> bool:
    return obj.get("caller_id") == caller or obj.get("owner_caller_id") == caller


class ToolPlaneState:
    def __init__(self) -> None:
        self.started: dict[str, dict[str, Any]] = {}
        self.ended: set[str] = set()
        self.last_target_event_at: str | None = None
        self.last_request_start_at: str | None = None

    def ingest(self, obj: dict[str, Any]) -> None:
        at = obj.get("at")
        if at:
            self.last_target_event_at = at
        if obj.get("event") == "request_start" and at:
            self.last_request_start_at = at
        pid = obj.get("process_id")
        if obj.get("event") == "process_started" and pid:
            self.started[pid] = obj
        if obj.get("event") in TERMINAL_EVENTS and pid:
            self.ended.add(pid)

    def live(self) -> list[dict[str, Any]]:
        return [x for pid, x in self.started.items() if pid not in self.ended]

    def snapshot(self) -> dict[str, Any]:
        now = dt.datetime.now(UTC)
        last = parse_iso(self.last_target_event_at)
        last_req = parse_iso(self.last_request_start_at)
        live = self.live()
        return {
            "live_process_count": len(live),
            "live_processes": [
                {
                    "process_id": x.get("process_id"),
                    "pid": x.get("pid"),
                    "cwd": x.get("cwd"),
                    "started_at": x.get("started_at") or x.get("at"),
                }
                for x in live
            ],
            "last_target_event_at": self.last_target_event_at,
            "last_request_start_at": self.last_request_start_at,
            "seconds_since_last_target_event": round(max(0.0, (now - last).total_seconds()), 3) if last else None,
            "seconds_since_last_request_start": round(max(0.0, (now - last_req).total_seconds()), 3) if last_req else None,
            "interpretation": (
                "local_child_active" if live else "no_observed_live_connector_child"
            ),
        }


def seed_tool_state(path: Path, caller: str) -> ToolPlaneState:
    state = ToolPlaneState()
    if not path.exists():
        return state
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if caller not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if belongs_to_caller(obj, caller):
                state.ingest(obj)
    return state


def iter_new_transport(path: Path, offset: int, caller: str) -> tuple[int, list[dict[str, Any]], bool]:
    """Return new byte offset, matching parsed events, and whether truncation was detected."""
    if not path.exists():
        return offset, [], False
    size = path.stat().st_size
    truncated = size < offset
    if truncated:
        offset = 0
    out: list[dict[str, Any]] = []
    with path.open("rb") as f:
        f.seek(offset)
        while True:
            raw = f.readline()
            if not raw:
                break
            # Avoid consuming an incomplete final JSONL record while a writer is mid-write.
            if not raw.endswith(b"\n"):
                f.seek(-len(raw), os.SEEK_CUR)
                break
            offset = f.tell()
            if caller.encode("utf-8") not in raw:
                continue
            try:
                obj = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if belongs_to_caller(obj, caller):
                out.append(obj)
    return offset, out, truncated


def max_thread_log_id(db: Path, thread_id: str) -> int:
    con = ro_connect(db)
    if con is None:
        return 0
    try:
        row = con.execute("SELECT COALESCE(MAX(id),0) FROM logs WHERE thread_id=?", (thread_id,)).fetchone()
        return int(row[0] or 0)
    finally:
        con.close()


def read_thread_rows(db: Path, thread_id: str, after_id: int, include_existing: bool = False) -> list[dict[str, Any]]:
    con = ro_connect(db)
    if con is None:
        return []
    try:
        if include_existing and after_id == 0:
            rows = con.execute(
                "SELECT id,ts,ts_nanos,level,target,file,line,process_uuid,feedback_log_body "
                "FROM logs WHERE thread_id=? ORDER BY id ASC",
                (thread_id,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id,ts,ts_nanos,level,target,file,line,process_uuid,feedback_log_body "
                "FROM logs WHERE thread_id=? AND id>? ORDER BY id ASC",
                (thread_id, after_id),
            ).fetchall()
    finally:
        con.close()
    return [
        {
            "id": rid,
            "ts": ts,
            "ts_nanos": nanos,
            "level": level,
            "target": target,
            "file": file,
            "line": line,
            "process_uuid": process_uuid,
            "feedback_log_body": body,
        }
        for rid, ts, nanos, level, target, file, line, process_uuid, body in rows
    ]


def append_marker(out: Path, label: str, note: str | None, caller: str | None, thread_id: str | None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8", newline="\n") as fp:
        emit(fp, {
            "schema": "safety-buffering-watch.v1",
            "capture_kind": "operator_marker",
            "captured_at": now_iso(),
            "label": label,
            "note": note,
            "caller_id": caller,
            "thread_id": thread_id,
        })


def main() -> int:
    transport_d, logs_d = default_paths()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--caller", help="MCP caller_id to archive")
    ap.add_argument("--thread-id", help="Known Codex app-server/thread id to archive from logs_2.sqlite")
    ap.add_argument("--transport", type=Path, default=transport_d)
    ap.add_argument("--logs-db", type=Path, default=logs_d)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--heartbeat", type=float, default=10.0)
    ap.add_argument("--include-existing", action="store_true", help="Archive existing matching transport/log rows before watching")
    ap.add_argument("--once", action="store_true", help="Take one pass and exit")
    ap.add_argument("--mark", metavar="LABEL", help="Append an operator/UI marker and exit")
    ap.add_argument("--note", help="Optional marker note")
    args = ap.parse_args()

    if args.mark:
        append_marker(args.out, args.mark, args.note, args.caller, args.thread_id)
        return 0
    if not args.caller:
        ap.error("--caller is required unless --mark is used")
    if args.interval <= 0 or args.heartbeat <= 0:
        ap.error("--interval and --heartbeat must be > 0")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    state = seed_tool_state(args.transport, args.caller)
    transport_offset = 0 if args.include_existing else (args.transport.stat().st_size if args.transport.exists() else 0)
    if args.thread_id:
        log_id = 0 if args.include_existing else max_thread_log_id(args.logs_db, args.thread_id)
    else:
        log_id = 0

    last_heartbeat = 0.0
    first_pass = True
    with args.out.open("a", encoding="utf-8", newline="\n") as fp:
        emit(fp, {
            "schema": "safety-buffering-watch.v1",
            "capture_kind": "watch_start",
            "captured_at": now_iso(),
            "caller_id": args.caller,
            "thread_id": args.thread_id,
            "transport_path": str(args.transport),
            "logs_db": str(args.logs_db),
            "transport_start_offset": transport_offset,
            "thread_log_start_id": log_id if args.thread_id else None,
            "include_existing": args.include_existing,
            "interpretation_contract": {
                "banner": "UI display state; not an execution-state signal",
                "tool_plane_silence": "no fresh MCP plus zero observed live connector child; backend/model state remains unknown",
                "model_rerouted": "separate notification; do not infer from safety-buffering banner",
            },
        })

        while True:
            transport_offset, events, truncated = iter_new_transport(args.transport, transport_offset, args.caller)
            if truncated:
                emit(fp, {
                    "schema": "safety-buffering-watch.v1",
                    "capture_kind": "warning",
                    "captured_at": now_iso(),
                    "warning": "transport_truncated_or_rotated",
                    "new_offset": transport_offset,
                })
            for obj in events:
                state.ingest(obj)
                emit(fp, {
                    "schema": "safety-buffering-watch.v1",
                    "capture_kind": "mcp_transport_event",
                    "captured_at": now_iso(),
                    "caller_id": args.caller,
                    "event": obj,
                })

            if args.thread_id:
                rows = read_thread_rows(args.logs_db, args.thread_id, log_id, include_existing=args.include_existing and first_pass)
                for row in rows:
                    log_id = max(log_id, int(row["id"]))
                    emit(fp, {
                        "schema": "safety-buffering-watch.v1",
                        "capture_kind": "codex_log_row",
                        "captured_at": now_iso(),
                        "thread_id": args.thread_id,
                        "row": row,
                    })

            mono = time.monotonic()
            if first_pass or mono - last_heartbeat >= args.heartbeat:
                snap = state.snapshot()
                # Name the observable states without upgrading them to backend claims.
                if snap["live_process_count"] > 0:
                    observable = "connector_child_active"
                elif snap["seconds_since_last_target_event"] is not None and snap["seconds_since_last_target_event"] >= args.heartbeat:
                    observable = "tool_plane_quiet_no_live_child"
                else:
                    observable = "no_live_child_recent_or_unknown_transport_state"
                emit(fp, {
                    "schema": "safety-buffering-watch.v1",
                    "capture_kind": "heartbeat",
                    "captured_at": now_iso(),
                    "caller_id": args.caller,
                    "thread_id": args.thread_id,
                    "observable_state": observable,
                    "tool_plane": snap,
                    "latest_archived_thread_log_id": log_id if args.thread_id else None,
                    "backend_model_state": "unknown",
                })
                last_heartbeat = mono

            first_pass = False
            if args.once:
                break
            time.sleep(args.interval)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
