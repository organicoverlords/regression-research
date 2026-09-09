#!/usr/bin/env python3
"""Read-only cross-layer snapshot for safety-buffering investigations.

Correlates the MCP transport plane with optional Codex per-thread tracing.
It deliberately does NOT infer backend/model stall from MCP silence alone.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

UTC = dt.timezone.utc
TERMINAL_EVENTS = {"process_exit_observed", "process_killed"}
TRACE_MARKERS = (
    "run_sampling_request",
    "try_run_sampling_request",
    "receiving_stream",
    "handle_responses",
)


def iso_now() -> str:
    return dt.datetime.now(UTC).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def default_paths() -> tuple[Path, Path, Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    user = Path(os.environ.get("USERPROFILE", str(Path.home())))
    base = local / "ChatGPTMcpClean" / "minimal-connectors"
    return (
        base / "clone-a" / "transport.jsonl",
        base / "shared-process-receipts",
        user / ".codex" / "logs_2.sqlite",
    )


def read_transport(path: Path, caller: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if caller not in line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("caller_id") == caller or obj.get("owner_caller_id") == caller:
                out.append(obj)
    return out


def transport_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    started: dict[str, dict[str, Any]] = {}
    ended: set[str] = set()
    request_starts: list[dict[str, Any]] = []
    process_events: list[dict[str, Any]] = []
    for e in events:
        if e.get("event") == "process_started" and e.get("process_id"):
            started[e["process_id"]] = e
        if e.get("event") in TERMINAL_EVENTS and e.get("process_id"):
            ended.add(e["process_id"])
        if e.get("event") == "request_start":
            request_starts.append(e)
        if e.get("process_id"):
            process_events.append(e)
    live = [e for pid, e in started.items() if pid not in ended]
    last = events[-1] if events else None
    last_req = request_starts[-1] if request_starts else None
    last_proc = process_events[-1] if process_events else None
    now = dt.datetime.now(UTC)
    last_dt = parse_iso(last.get("at")) if last else None
    last_req_dt = parse_iso(last_req.get("at")) if last_req else None
    last_proc_dt = parse_iso(last_proc.get("at")) if last_proc else None
    silent_s = (now - last_dt).total_seconds() if last_dt else None
    req_s = (now - last_req_dt).total_seconds() if last_req_dt else None
    proc_s = (now - last_proc_dt).total_seconds() if last_proc_dt else None
    return {
        "event_count": len(events),
        "last_event": last,
        "last_request_start": last_req,
        "last_process_event": last_proc,
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
        "seconds_since_last_transport_event": round(max(0.0, silent_s), 3) if silent_s is not None else None,
        "seconds_since_last_request_start": round(max(0.0, req_s), 3) if req_s is not None else None,
        "seconds_since_last_process_event": round(max(0.0, proc_s), 3) if proc_s is not None else None,
    }


def read_receipt(receipts: Path, process_id: str | None) -> dict[str, Any] | None:
    if not process_id:
        return None
    p = receipts / f"{process_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def distinctive_terms(command: str) -> list[str]:
    # Favor worktree/file/repo-ish tokens; avoid common shell syntax.
    toks = re.findall(r"[A-Za-z0-9_.-]{12,}", command)
    bad = {"ErrorActionPreference", "SilentlyContinue", "Select-Object", "Write-Output", "Write-Host"}
    uniq: list[str] = []
    for t in sorted(set(toks), key=len, reverse=True):
        if t in bad or t.lower().startswith(("process", "powershell")):
            continue
        if t not in uniq:
            uniq.append(t)
    return uniq[:12]


def ro_connect(db: Path) -> sqlite3.Connection | None:
    if not db.exists():
        return None
    try:
        uri = "file:" + str(db).replace("\\", "/") + "?mode=ro"
        return sqlite3.connect(uri, uri=True, timeout=2)
    except sqlite3.Error:
        return None


def auto_map_thread(db: Path, receipt: dict[str, Any] | None, window_s: int = 20) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "unavailable", "candidates": []}
    if not receipt or not receipt.get("command") or not receipt.get("started_at"):
        result["reason"] = "no suitable process receipt"
        return result
    con = ro_connect(db)
    if con is None:
        result["reason"] = "logs database unavailable"
        return result
    started = parse_iso(receipt.get("started_at"))
    if started is None:
        result["reason"] = "receipt start time not parseable"
        return result
    terms = distinctive_terms(receipt["command"])
    if not terms:
        result["reason"] = "no distinctive command terms"
        return result
    lo = int(started.timestamp()) - window_s
    hi = int(started.timestamp()) + window_s
    cur = con.cursor()
    scores: dict[str, dict[str, Any]] = {}
    for term in terms:
        rows = cur.execute(
            "SELECT id, ts, target, thread_id, feedback_log_body FROM logs "
            "WHERE ts BETWEEN ? AND ? AND thread_id IS NOT NULL "
            "AND INSTR(COALESCE(feedback_log_body,''), ?) > 0 ORDER BY id DESC LIMIT 100",
            (lo, hi, term),
        ).fetchall()
        for rid, ts, target, thread_id, body in rows:
            d = scores.setdefault(thread_id, {"thread_id": thread_id, "score": 0, "matched_terms": [], "example_log_id": rid, "example_ts": ts, "target": target})
            d["score"] += 1
            if term not in d["matched_terms"]:
                d["matched_terms"].append(term)
    con.close()
    candidates = sorted(scores.values(), key=lambda x: (-x["score"], x["thread_id"]))
    result["terms_tried"] = terms
    result["window_utc"] = {
        "from": dt.datetime.fromtimestamp(lo, UTC).isoformat(),
        "to": dt.datetime.fromtimestamp(hi, UTC).isoformat(),
    }
    result["candidates"] = candidates[:10]
    if len(candidates) == 1:
        result["status"] = "unique_candidate"
        result["thread_id"] = candidates[0]["thread_id"]
    elif candidates:
        result["status"] = "ambiguous"
        result["reason"] = "multiple candidate threads matched receipt terms"
    else:
        result["status"] = "no_match"
        result["reason"] = "no retained local Codex log rows matched receipt terms in time window"
    return result


def log_window_coverage(db: Path, receipt: dict[str, Any] | None, pad_s: int = 20) -> dict[str, Any]:
    """Check whether the local Codex log DB retains *any* rows around a process receipt."""
    if not receipt or not receipt.get("started_at"):
        return {"status": "unavailable", "reason": "no process receipt start time"}
    started = parse_iso(receipt.get("started_at"))
    finished = parse_iso(receipt.get("finished_at")) or started
    if started is None or finished is None:
        return {"status": "unavailable", "reason": "receipt timestamps not parseable"}
    con = ro_connect(db)
    if con is None:
        return {"status": "unavailable", "reason": "logs database unavailable"}
    lo = int(started.timestamp()) - pad_s
    hi = int(finished.timestamp()) + pad_s
    try:
        count = int(con.execute("SELECT COUNT(*) FROM logs WHERE ts BETWEEN ? AND ?", (lo, hi)).fetchone()[0])
        before = con.execute(
            "SELECT id,ts,ts_nanos,thread_id,target FROM logs WHERE ts < ? ORDER BY ts DESC,ts_nanos DESC,id DESC LIMIT 1",
            (lo,),
        ).fetchone()
        after = con.execute(
            "SELECT id,ts,ts_nanos,thread_id,target FROM logs WHERE ts > ? ORDER BY ts ASC,ts_nanos ASC,id ASC LIMIT 1",
            (hi,),
        ).fetchone()
    finally:
        con.close()

    def row_obj(row):
        if row is None:
            return None
        rid, ts, nanos, thread_id, target = row
        stamp = dt.datetime.fromtimestamp(ts, UTC).replace(microsecond=int(nanos // 1000)).isoformat()
        return {"id": rid, "ts": ts, "ts_nanos": nanos, "at_utc": stamp, "thread_id": thread_id, "target": target}

    status = "covered" if count else "retention_gap_or_logging_gap"
    return {
        "status": status,
        "window_utc": {
            "from": dt.datetime.fromtimestamp(lo, UTC).isoformat(),
            "to": dt.datetime.fromtimestamp(hi, UTC).isoformat(),
        },
        "row_count_any_thread": count,
        "nearest_row_before": row_obj(before),
        "nearest_row_after": row_obj(after),
        "interpretation": (
            "local Codex log rows exist in receipt window"
            if count
            else "current logs_2.sqlite has no rows in this receipt window; Responses state cannot be reconstructed from this DB window"
        ),
    }


def thread_trace(db: Path, thread_id: str, minutes: int) -> dict[str, Any]:
    con = ro_connect(db)
    if con is None:
        return {"status": "unavailable", "reason": "logs database unavailable"}
    cutoff = int((dt.datetime.now(UTC) - dt.timedelta(minutes=minutes)).timestamp())
    rows = con.execute(
        "SELECT id, ts, ts_nanos, level, target, file, line, feedback_log_body "
        "FROM logs WHERE thread_id=? AND ts>=? ORDER BY id DESC LIMIT 1000",
        (thread_id, cutoff),
    ).fetchall()
    con.close()
    flags = {m: False for m in TRACE_MARKERS}
    idle_timeout_rows: list[dict[str, Any]] = []
    safety_rows: list[dict[str, Any]] = []
    response_event_names: list[str] = []
    newest = None
    for rid, ts, nanos, level, target, file, line, body in rows:
        body = body or ""
        if newest is None:
            newest = {"id": rid, "ts": ts, "ts_nanos": nanos, "level": level, "target": target, "body": body[:1200]}
        for m in TRACE_MARKERS:
            flags[m] = flags[m] or (m in body)
        low = body.lower()
        if "idle timeout waiting for" in low:
            idle_timeout_rows.append({"id": rid, "ts": ts, "target": target, "body": body[:1200]})
        if "safety_buffering" in low or "safetybuffering" in low:
            safety_rows.append({"id": rid, "ts": ts, "target": target, "body": body[:1200]})
        for name in re.findall(r'otel\.name="([^"]+)"', body):
            if name not in response_event_names:
                response_event_names.append(name)
    return {
        "status": "ok",
        "thread_id": thread_id,
        "rows_considered": len(rows),
        "lookback_minutes": minutes,
        "newest_row": newest,
        "trace_markers_seen": flags,
        "response_event_names_seen": response_event_names[:80],
        "safety_buffering_log_rows": safety_rows[:20],
        "idle_timeout_log_rows": idle_timeout_rows[:20],
    }


def classify(ts: dict[str, Any], trace: dict[str, Any] | None) -> dict[str, Any]:
    live = int(ts.get("live_process_count", 0) or 0)
    since = ts.get("seconds_since_last_transport_event")
    req_since = ts.get("seconds_since_last_request_start")
    recent_event = since is not None and since < 10
    recent_request = req_since is not None and req_since < 10
    if live > 0 and recent_request:
        observable = "fresh_mcp_with_live_connector_child"
    elif live > 0:
        observable = "live_connector_child_without_fresh_mcp"
    elif recent_event:
        observable = "recent_mcp_event_no_live_connector_child"
    else:
        observable = "tool_plane_quiet_no_live_connector_child"
    result = {
        "tool_plane_observable": observable,
        "live_connector_child": live > 0,
        "fresh_mcp_request_within_10s": recent_request,
        "backend_model_state": "unknown",
        "warning": "Never infer backend/model stall from zero MCP calls and zero connector children alone.",
    }
    if trace and trace.get("status") == "ok":
        markers = trace.get("trace_markers_seen", {})
        if markers.get("receiving_stream") or markers.get("handle_responses") or markers.get("try_run_sampling_request"):
            result["responses_trace_evidence"] = "recent local Codex logs contain remote Responses sampling/receiving-stream span context"
        if trace.get("idle_timeout_log_rows"):
            result["responses_transport_error_evidence"] = "idle-timeout log row observed; inspect exact timestamp/turn before asserting backend/transport stall"
    return result


def main() -> int:
    transport_d, receipts_d, logs_d = default_paths()
    ap = argparse.ArgumentParser()
    ap.add_argument("--caller", required=True)
    ap.add_argument("--thread-id")
    ap.add_argument("--transport", type=Path, default=transport_d)
    ap.add_argument("--receipts", type=Path, default=receipts_d)
    ap.add_argument("--logs-db", type=Path, default=logs_d)
    ap.add_argument("--trace-minutes", type=int, default=30)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    events = read_transport(args.transport, args.caller)
    ts = transport_summary(events)
    latest_pid = None
    for e in reversed(events):
        if e.get("process_id"):
            latest_pid = e.get("process_id")
            break
    receipt = read_receipt(args.receipts, latest_pid)
    mapping = None
    thread_id = args.thread_id
    if thread_id is None:
        mapping = auto_map_thread(args.logs_db, receipt)
        if mapping.get("status") == "unique_candidate":
            thread_id = mapping.get("thread_id")
    trace = thread_trace(args.logs_db, thread_id, args.trace_minutes) if thread_id else None
    out = {
        "schema": "safety-buffering-probe.v2",
        "generated_at": iso_now(),
        "caller_id": args.caller,
        "transport_path": str(args.transport),
        "logs_db": str(args.logs_db),
        "transport": ts,
        "latest_process_receipt": {
            "process_id": receipt.get("process_id"),
            "started_at": receipt.get("started_at"),
            "finished_at": receipt.get("finished_at"),
            "cwd": receipt.get("cwd"),
            "command_preview": receipt.get("command", "")[:1200],
        } if receipt else None,
        "thread_mapping": mapping,
        "codex_log_window_coverage": log_window_coverage(args.logs_db, receipt),
        "codex_thread_trace": trace,
        "classification": classify(ts, trace),
        "interpretation_contract": {
            "tool_plane_silence": "zero/freshly absent MCP activity plus zero live connector child is a local execution-plane observation only",
            "backend_stall": "requires additional Responses/inference-channel evidence; not inferable from MCP silence alone",
            "safety_buffering": "requires UI/app-server evidence; not synonymous with model/rerouted",
        },
    }
    payload = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
