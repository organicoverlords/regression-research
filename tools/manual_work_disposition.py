from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

BINDING_SCHEMA = "manual-run-binding.v1"
BINDING_DIRNAME = "bindings"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
TRACE_MAX_SPAN_HOURS = 2.0


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _stdout_run_id(stdout: Any) -> str | None:
    text = str(stdout or "")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("run_id"):
            return str(value["run_id"])
    return None

def _stdout_legacy_report_run_id(stdout: Any) -> str | None:
    for line in str(stdout or "").splitlines():
        line = line.strip()
        if not line.upper().startswith("REPORT="):
            continue
        value = line.split("=", 1)[1].strip().strip('\"')
        stem = Path(value).stem
        if RUN_ID_RE.fullmatch(stem):
            return stem
    return None


def binding_path(manual_root: Path, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(str(run_id)):
        raise ValueError("manual binding run_id must be filesystem-safe")
    return Path(manual_root) / BINDING_DIRNAME / f"{run_id}.json"


def load_binding(manual_root: Path, run_id: str) -> dict[str, Any] | None:
    path = binding_path(manual_root, run_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema") != BINDING_SCHEMA or value.get("run_id") != run_id:
        return None
    return value


def _receipt_candidates(
    receipt_dir: Path,
    *,
    archive_days: set[str] | None = None,
    mtime_floor: float | None = None,
    mtime_ceiling: float | None = None,
) -> list[Path]:
    """Return bounded flat + selected day-sharded durable archive receipts."""

    def collect(directory: Path) -> list[Path]:
        found: list[Path] = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not entry.is_file() or not entry.name.lower().endswith(".json"):
                        continue
                    if mtime_floor is not None or mtime_ceiling is not None:
                        try:
                            observed = entry.stat().st_mtime
                        except OSError:
                            continue
                        if mtime_floor is not None and observed < mtime_floor:
                            continue
                        if mtime_ceiling is not None and observed > mtime_ceiling:
                            continue
                    found.append(Path(entry.path))
        except OSError:
            pass
        return found

    root = Path(receipt_dir)
    candidates = collect(root)
    archive = root / "archive"
    try:
        day_dirs = [
            path for path in archive.iterdir()
            if path.is_dir()
            and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.name)
            and (archive_days is None or path.name in archive_days)
        ]
        day_dirs = sorted(day_dirs, key=lambda path: path.name, reverse=True)[:8]
    except OSError:
        day_dirs = []
    for day in day_dirs:
        candidates.extend(collect(day))
    return candidates


def _receipt_caller_matches(path: Path, caller_id: str) -> bool:
    """Cheaply reject foreign receipts before decoding retained command/output payloads."""
    token = re.escape(json.dumps(str(caller_id), ensure_ascii=False))
    pattern = re.compile(r'"caller_id"\s*:\s*' + token)
    try:
        with path.open("rb") as handle:
            prefix = handle.read(2048).decode("utf-8", errors="ignore")
    except OSError:
        return False
    return pattern.search(prefix) is not None


def _caller_receipt_candidates(
    receipt_dir: Path,
    caller_id: str,
    *,
    archive_days: set[str],
    mtime_floor: float,
    mtime_ceiling: float,
) -> list[Path]:
    """Find one caller's receipts from a bounded mtime window without full payload scans."""
    candidates = _receipt_candidates(
        Path(receipt_dir),
        archive_days=archive_days,
        mtime_floor=mtime_floor,
        mtime_ceiling=mtime_ceiling,
    )
    return [path for path in candidates if _receipt_caller_matches(path, caller_id)]


def _archive_days_for_run_id(run_id: str) -> set[str] | None:
    match = re.match(r"^manual-(\d{4})(\d{2})(\d{2})(?:-|T)", run_id)
    if not match:
        return None
    try:
        local_day = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc).date()
    except ValueError:
        return None
    # Manual IDs use local wall date while MCP archive shards use receipt time. A one-day
    # pad in either direction covers timezone/date-boundary differences without a full scan.
    return {(local_day + timedelta(days=offset)).isoformat() for offset in (-1, 0, 1)}


def _archive_days_since(start_at: datetime) -> set[str]:
    start_day = start_at.astimezone(timezone.utc).date()
    today = datetime.now(timezone.utc).date()
    end_day = min(today, start_day + timedelta(days=7))
    if end_day < start_day:
        end_day = start_day
    return {(start_day + timedelta(days=offset)).isoformat() for offset in range((end_day - start_day).days + 1)}


def _matching_receipt(
    receipt_dir: Path, run_id: str, *, started_at: datetime | None = None
) -> tuple[Path, dict[str, Any], bytes, str] | None:
    if started_at is not None:
        start_day = started_at.astimezone(timezone.utc).date()
        archive_days = {start_day.isoformat(), (start_day + timedelta(days=1)).isoformat()}
    else:
        archive_days = _archive_days_for_run_id(run_id)
    lower = started_at.timestamp() - 60.0 if started_at is not None else None
    upper = started_at.timestamp() + 30.0 * 60.0 if started_at is not None else None
    candidates = _receipt_candidates(
        Path(receipt_dir), archive_days=archive_days, mtime_floor=lower, mtime_ceiling=upper
    )
    if not candidates:
        return None
    # Exact structured stdout run_id remains the identity proof. The timestamp window is
    # only a bounded lookup key supplied from the report created by the same command.
    for path in candidates:
        try:
            raw = path.read_bytes()
            receipt = json.loads(raw.decode("utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(receipt, dict):
            continue
        command = str(receipt.get("command") or "")
        low = command.casefold()
        canonical = (
            "worker_report_history.py" in low
            and "create-manual" in low
            and _stdout_run_id(receipt.get("stdout")) == run_id
        )
        legacy = (
            "worker-reports" in low
            and "manual" in low
            and "current" in low
            and "set-content" in low
            and _stdout_legacy_report_run_id(receipt.get("stdout")) == run_id
        )
        if not canonical and not legacy:
            continue
        if not all(str(receipt.get(key) or "").strip() for key in ("process_id", "caller_id", "request_id")):
            continue
        basis = (
            "mcp_process_receipt_create_manual_stdout_run_id"
            if canonical
            else "mcp_process_receipt_legacy_manual_report_stdout_path"
        )
        return path, receipt, raw, basis
    return None


def capture_binding(
    *,
    run_id: str,
    creator_child_pid: int,
    receipt_dir: Path,
    manual_root: Path,
    started_at: str | None = None,
    timeout_seconds: float = 15.0,
    poll_seconds: float = 0.10,
) -> dict[str, Any]:
    """Persist the exact MCP caller/process identity for a newly created manual run.

    The create-manual process cannot see caller_id directly. MCP writes that identity into
    its immutable process receipt only after the tool call exits, so this bounded helper waits
    for the canonical create-manual receipt whose structured stdout contains this collision-
    resistant run_id. No caller/timestamp inference is involved.
    """
    destination = binding_path(manual_root, run_id)
    existing = load_binding(manual_root, run_id)
    if existing is not None:
        return {"ok": True, "captured": False, "deduplicated": True, "path": str(destination), "binding": existing}

    observed_start = _parse_time(started_at) if started_at else None
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while True:
        matched = _matching_receipt(Path(receipt_dir), run_id, started_at=observed_start)
        if matched is not None:
            source, receipt, raw, basis = matched
            payload = {
                "schema": BINDING_SCHEMA,
                "run_id": run_id,
                "binding_basis": basis,
                "caller_id": str(receipt["caller_id"]),
                "create_process_id": str(receipt["process_id"]),
                "create_request_id": str(receipt["request_id"]),
                "mcp_process_pid": int(receipt["pid"]) if receipt.get("pid") is not None else None,
                "creator_child_pid": int(creator_child_pid),
                "create_started_at": receipt.get("started_at"),
                "create_finished_at": receipt.get("finished_at"),
                "receipt_file": source.name,
                "receipt_source": "archive" if source.parent.parent.name == "archive" else "flat",
                "receipt_sha256": hashlib.sha256(raw).hexdigest(),
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "authority": "EXACT_MCP_IDENTITY_EVIDENCE_NOT_WORK_LIVENESS",
            }
            _atomic_json(destination, payload)
            return {"ok": True, "captured": True, "deduplicated": False, "path": str(destination), "binding": payload}
        if time.monotonic() >= deadline:
            return {
                "ok": False,
                "captured": False,
                "run_id": run_id,
                "error": "matching MCP create-manual receipt not observed before timeout",
            }
        time.sleep(max(0.01, float(poll_seconds)))


def binding_summary(binding: dict[str, Any] | None) -> dict[str, Any]:
    if not binding:
        return {"status": "UNBOUND", "authority": "NO_EXACT_MCP_IDENTITY_EVIDENCE"}
    return {
        "status": "BOUND",
        "authority": binding.get("authority"),
        "binding_basis": binding.get("binding_basis"),
        "caller_id": binding.get("caller_id"),
        "create_process_id": binding.get("create_process_id"),
        "create_request_id": binding.get("create_request_id"),
        "receipt_source": binding.get("receipt_source"),
        "receipt_sha256": binding.get("receipt_sha256"),
    }



def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _json_objects(text: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            result.append(value)
    return result


def _command_kind(command: str) -> str:
    low = command.casefold()
    if "worker_report_history.py" in low and "create-manual" in low:
        return "manual_create"
    if "worker_report_history.py" in low and " archive " in f" {low} ":
        return "manual_archive"
    if "swarm_exec.py" in low:
        return "swarm_exec"
    if "swarm_route.py" in low:
        return "swarm_route"
    if re.search(r"(?:^|[;&|]\s*)gh\s+", command, re.IGNORECASE):
        return "github_cli"
    if re.search(r"(?:^|[;&|]\s*)git\s+", command, re.IGNORECASE):
        return "git_cli"
    return "other"


def _work_ids(command: str, stdout: Any, stderr: Any) -> set[str]:
    values = set(re.findall(r"--work-id(?:=|\s+)[\"']?([A-Za-z0-9._:-]+)", command))
    for item in _json_objects(stdout) + _json_objects(stderr):
        value = item.get("work_id")
        if value:
            values.add(str(value))
    return values


def _route_decisions(stdout: Any, stderr: Any) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for item in _json_objects(stdout) + _json_objects(stderr):
        if not item.get("work_id"):
            continue
        if not any(key in item for key in ("decision_id", "route", "event")):
            continue
        decisions.append({
            key: item.get(key)
            for key in ("event", "work_id", "decision_id", "route", "kind", "reason", "execution_node_id")
            if item.get(key) is not None
        })
    return decisions


def _github_refs(command: str, stdout: Any, stderr: Any) -> set[str]:
    text = "\n".join((command, str(stdout or ""), str(stderr or "")))
    refs = {
        match.group(0).rstrip(".,);]")
        for match in re.finditer(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(?:pull|issues)/\d+", text)
    }
    repo_match = re.search(r"--repo(?:=|\s+)[\"']?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", command)
    if repo_match:
        repo = repo_match.group(1)
        for kind in ("pr", "issue"):
            match = re.search(rf"\bgh\s+{kind}\s+(?:view|merge|close|edit|checks|reopen)\s+(\d+)\b", command, re.IGNORECASE)
            if match:
                suffix = "pull" if kind == "pr" else "issues"
                refs.add(f"https://github.com/{repo}/{suffix}/{match.group(1)}")
    return refs


def _commit_shas(command: str, stdout: Any) -> set[str]:
    if not re.search(r"\bgit\b.*\bcommit\b", command, re.IGNORECASE):
        return set()
    values: set[str] = set()
    for line in str(stdout or "").splitlines():
        match = re.search(r"\[[^\]]+\s+([0-9a-fA-F]{7,40})\]", line)
        if match:
            values.add(match.group(1).lower())
    return values


def trace_path(manual_root: Path, run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(str(run_id)):
        raise ValueError("manual trace run_id must be filesystem-safe")
    return Path(manual_root) / "traces" / f"{run_id}.json"


def capture_trace(*, run_id: str, receipt_dir: Path, manual_root: Path) -> dict[str, Any]:
    """Persist a bounded exact-process trace for one bound manual run.

    Membership is segmented by exact MCP caller plus explicit manual lifecycle control
    receipts (this run's create receipt, archive receipt, or the next create-manual receipt
    for the same caller). Timestamps only order receipts; they are never used to guess a
    caller or run identity.
    """
    binding = load_binding(manual_root, run_id)
    if binding is None:
        return {"ok": False, "run_id": run_id, "error": "exact manual run binding is unavailable"}
    caller_id = str(binding.get("caller_id") or "")
    create_process_id = str(binding.get("create_process_id") or "")
    start_at = _parse_time(binding.get("create_started_at"))
    if not caller_id or not create_process_id or start_at is None:
        return {"ok": False, "run_id": run_id, "error": "manual run binding is incomplete"}

    receipts: list[tuple[datetime, Path, dict[str, Any], bytes]] = []
    trace_ceiling = start_at.timestamp() + TRACE_MAX_SPAN_HOURS * 3600.0
    candidates = _caller_receipt_candidates(
        Path(receipt_dir),
        caller_id,
        archive_days=_archive_days_since(start_at),
        mtime_floor=start_at.timestamp() - 5.0,
        mtime_ceiling=trace_ceiling,
    )
    if not candidates:
        return {"ok": False, "run_id": run_id, "error": "no MCP process receipts available"}
    seen_process_ids: set[str] = set()
    for path in candidates:
        try:
            raw = path.read_bytes()
            item = json.loads(raw.decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict) or str(item.get("caller_id") or "") != caller_id:
            continue
        process_id = str(item.get("process_id") or "")
        if not process_id or process_id in seen_process_ids:
            continue
        seen_process_ids.add(process_id)
        observed = _parse_time(item.get("started_at"))
        if observed is None or observed < start_at:
            continue
        receipts.append((observed, path, item, raw))
    receipts.sort(key=lambda row: (row[0], str(row[2].get("process_id") or "")))

    processes: list[dict[str, Any]] = []
    work_ids: set[str] = set()
    github_refs: set[str] = set()
    commit_shas: set[str] = set()
    route_decisions: list[dict[str, Any]] = []
    boundary = "OPEN_NO_TERMINAL_CONTROL_RECEIPT"
    complete_through_boundary = False
    for _, path, item, raw in receipts:
        process_id = str(item.get("process_id") or "")
        command = str(item.get("command") or "")
        command_kind = _command_kind(command)
        stdout = item.get("stdout")
        stderr = item.get("stderr")
        created_run = _stdout_run_id(stdout) if command_kind == "manual_create" else None
        if process_id != create_process_id and command_kind == "manual_create" and created_run and created_run != run_id:
            boundary = f"NEXT_MANUAL_CREATE:{created_run}"
            complete_through_boundary = True
            break

        item_work_ids = _work_ids(command, stdout, stderr)
        item_refs = _github_refs(command, stdout, stderr)
        item_commits = _commit_shas(command, stdout)
        item_routes = _route_decisions(stdout, stderr)
        work_ids.update(item_work_ids)
        github_refs.update(item_refs)
        commit_shas.update(item_commits)
        route_decisions.extend(item_routes)
        processes.append({
            "process_id": process_id or None,
            "request_id": item.get("request_id"),
            "started_at": item.get("started_at"),
            "finished_at": item.get("finished_at"),
            "exit_code": item.get("exit_code"),
            "cwd": item.get("cwd"),
            "command_kind": command_kind,
            "command_sha256": hashlib.sha256(command.encode("utf-8", errors="replace")).hexdigest(),
            "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "work_ids": sorted(item_work_ids),
            "github_refs": sorted(item_refs),
            "commit_shas": sorted(item_commits),
        })
        if command_kind == "manual_archive" and run_id in command:
            boundary = "MANUAL_ARCHIVE_RECEIPT"
            complete_through_boundary = True
            break

    payload = {
        "schema": "manual-run-process-trace.v1",
        "run_id": run_id,
        "authority": "EXACT_MCP_PROCESS_EVIDENCE_NOT_WORK_LIVENESS",
        "caller_id": caller_id,
        "create_process_id": create_process_id,
        "boundary": boundary,
        "complete_through_boundary": complete_through_boundary,
        "trace_horizon_hours": TRACE_MAX_SPAN_HOURS,
        "horizon_exhausted": (
            not complete_through_boundary and datetime.now(timezone.utc).timestamp() >= trace_ceiling
        ),
        "process_count": len(processes),
        "work_ids": sorted(work_ids),
        "github_refs": sorted(github_refs),
        "commit_shas": sorted(commit_shas),
        "route_decisions": route_decisions,
        "processes": processes,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    destination = trace_path(manual_root, run_id)
    _atomic_json(destination, payload)
    return {"ok": True, "path": str(destination), "trace": payload}


def trace_summary(trace: dict[str, Any] | None) -> dict[str, Any]:
    if not trace:
        return {"status": "UNAVAILABLE"}
    return {
        "status": "CAPTURED",
        "authority": trace.get("authority"),
        "boundary": trace.get("boundary"),
        "complete_through_boundary": bool(trace.get("complete_through_boundary")),
        "trace_horizon_hours": trace.get("trace_horizon_hours"),
        "horizon_exhausted": bool(trace.get("horizon_exhausted")),
        "process_count": trace.get("process_count", 0),
        "work_ids": trace.get("work_ids") or [],
        "github_refs": trace.get("github_refs") or [],
        "commit_shas": trace.get("commit_shas") or [],
        "route_decisions": trace.get("route_decisions") or [],
    }


def load_trace(manual_root: Path, run_id: str) -> dict[str, Any] | None:
    path = trace_path(manual_root, run_id)
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("schema") != "manual-run-process-trace.v1" or value.get("run_id") != run_id:
        return None
    return value

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture exact MCP identity for manual worker runs.")
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture-binding")
    capture.add_argument("--run-id", required=True)
    capture.add_argument("--creator-child-pid", type=int, required=True)
    capture.add_argument("--receipt-dir", type=Path, required=True)
    capture.add_argument("--manual-root", type=Path, required=True)
    capture.add_argument("--started-at")
    capture.add_argument("--timeout-seconds", type=float, default=15.0)
    trace = sub.add_parser("capture-trace")
    trace.add_argument("--run-id", required=True)
    trace.add_argument("--receipt-dir", type=Path, required=True)
    trace.add_argument("--manual-root", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "capture-binding":
        result = capture_binding(
            run_id=args.run_id,
            creator_child_pid=args.creator_child_pid,
            receipt_dir=args.receipt_dir,
            manual_root=args.manual_root,
            started_at=args.started_at,
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(result))
        return 0 if result.get("ok") else 1
    if args.command == "capture-trace":
        result = capture_trace(run_id=args.run_id, receipt_dir=args.receipt_dir, manual_root=args.manual_root)
        print(json.dumps(result))
        return 0 if result.get("ok") else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
