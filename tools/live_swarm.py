from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ACTIVITY_WINDOW_SECONDS = 300
OBSERVATION_WINDOW_MINUTES = 30.0
EXECUTION_REFERENCE_MINUTES = 27.0
MAX_TRANSPORT_BYTES = 8 * 1024 * 1024


def _dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _read_window(path: Path, cutoff: datetime) -> tuple[list[dict[str, Any]], bool, int]:
    parts: list[bytes] = []
    size = path.stat().st_size
    pos = size
    read = 0
    complete = size == 0
    with path.open("rb") as handle:
        while pos > 0 and read < MAX_TRANSPORT_BYTES:
            take = min(256 * 1024, pos, MAX_TRANSPORT_BYTES - read)
            pos -= take
            handle.seek(pos)
            chunk = handle.read(take)
            parts.append(chunk)
            read += len(chunk)
            lines = chunk.splitlines()[1:] if pos > 0 else chunk.splitlines()
            for raw in lines:
                try:
                    row = json.loads(raw.decode("utf-8-sig"))
                except Exception:
                    continue
                at = _dt(row.get("at")) if isinstance(row, dict) else None
                if at is not None:
                    if at <= cutoff:
                        complete = True
                    break
            if complete:
                break
    if pos == 0:
        complete = True
    rows: list[dict[str, Any]] = []
    for raw in b"".join(reversed(parts)).splitlines():
        try:
            row = json.loads(raw.decode("utf-8-sig"))
        except Exception:
            continue
        at = _dt(row.get("at")) if isinstance(row, dict) else None
        if isinstance(row, dict) and (at is None or at >= cutoff):
            rows.append(row)
    return rows, complete, read


def _workspace(path: str | None) -> str | None:
    if not path:
        return None
    low = path.replace("/", "\\").casefold()
    if "tiny3d" in low:
        return "Tiny3D"
    if "lowvram" in low:
        return "LowVRAM"
    if "\\.agents" in low:
        return "Agents"
    if "unreal projects\\p3" in low or "p3-" in low or "-p3-" in low:
        return "P3"
    if "chatgptmcpclean" in low:
        return "MCP"
    if "chatgptmcpminimal" in low:
        return "MCP-runtime"
    if "\\vault" in low:
        return "Vault"
    return Path(path).name or path


def _command_target(command: str) -> tuple[str | None, str | None]:
    variables = {
        m.group(1).casefold(): m.group(2)
        for m in re.finditer(r"\$([A-Za-z_]\w*)\s*=\s*['\"]([A-Za-z]:\\[^'\"]+)['\"]", command)
    }
    for name, path in variables.items():
        if re.search(rf"(?i)\b(?:Set-Location|cd)\s+\${re.escape(name)}\b", command):
            return path, "command_cwd"
    for pattern, basis in (
        (r"(?i)\b(?:Set-Location|cd)(?:\s+-LiteralPath)?\s+['\"]([A-Za-z]:\\[^'\"]+)['\"]", "command_cwd"),
        (r"(?i)\bgit\s+-C\s+['\"]([A-Za-z]:\\[^'\"]+)['\"]", "command_git_c"),
    ):
        match = re.search(pattern, command)
        if match:
            return match.group(1), basis
    return None, None


def _git_identity(candidate: str | None, cache: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve worktree/branch/HEAD from bounded local Git metadata; no Git process."""
    if not candidate:
        return None
    probe = Path(os.path.expandvars(candidate))
    try:
        if probe.is_file() or (not probe.exists() and probe.suffix):
            probe = probe.parent
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        if not probe.exists():
            return None
        root = probe
        while root.parent != root and not (root / ".git").exists():
            root = root.parent
        dotgit = root / ".git"
        if not dotgit.exists():
            return None
        key = os.path.normcase(os.path.normpath(str(root)))
        if key in cache:
            return cache[key]

        if dotgit.is_dir():
            gitdir = dotgit
        else:
            marker = dotgit.read_text(encoding="utf-8", errors="replace").strip()
            if not marker.casefold().startswith("gitdir:"):
                cache[key] = None
                return None
            target = marker.split(":", 1)[1].strip()
            gitdir = Path(target)
            if not gitdir.is_absolute():
                gitdir = (root / gitdir).resolve()

        common = gitdir
        commondir = gitdir / "commondir"
        if commondir.is_file():
            common_target = commondir.read_text(encoding="utf-8", errors="replace").strip()
            common = Path(common_target)
            if not common.is_absolute():
                common = (gitdir / common).resolve()

        head_text = (gitdir / "HEAD").read_text(encoding="ascii", errors="replace").strip()
        branch = None
        head = None
        if head_text.startswith("ref: "):
            ref = head_text[5:].strip()
            branch = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
            for base in (gitdir, common):
                ref_path = base / Path(*ref.split("/"))
                if ref_path.is_file():
                    value = ref_path.read_text(encoding="ascii", errors="replace").strip()
                    if re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
                        head = value[:8].lower()
                        break
            if head is None:
                for packed in (gitdir / "packed-refs", common / "packed-refs"):
                    if not packed.is_file():
                        continue
                    for line in packed.read_text(encoding="ascii", errors="replace").splitlines():
                        if not line or line.startswith(("#", "^")):
                            continue
                        parts = line.split(" ", 1)
                        if len(parts) == 2 and parts[1] == ref and re.fullmatch(r"[0-9a-fA-F]{40,64}", parts[0]):
                            head = parts[0][:8].lower()
                            break
                    if head is not None:
                        break
        elif re.fullmatch(r"[0-9a-fA-F]{40,64}", head_text):
            branch = "(detached)"
            head = head_text[:8].lower()

        result = {"path": str(root), "branch": branch, "head": head}
        cache[key] = result
        return result
    except OSError:
        return None


def build_live_swarm_snapshot(now: datetime | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    now = now or datetime.now(timezone.utc)
    root = Path(os.path.expandvars(r"%LOCALAPPDATA%\ChatGPTMcpClean\minimal-connectors"))
    logs = sorted(root.glob("clone-*/transport.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return {"schema":"live-swarm.v1","available":False,"lanes":[],"summary":{"recent_callers":0,"lanes":0}}
    source = logs[0]
    cutoff = now - timedelta(minutes=OBSERVATION_WINDOW_MINUTES)
    rows, complete, sample_bytes = _read_window(source, cutoff)
    active_cutoff = now - timedelta(seconds=ACTIVITY_WINDOW_SECONDS)
    callers: dict[str, dict[str, Any]] = {}
    processes: dict[str, dict[str, Any]] = {}
    activity_counts = {"starts":0,"reads":0,"exits":0,"kills":0,"nonzero_exits":0}
    last_event_at = None
    observer_pids = {os.getpid(), os.getppid()}
    observer_callers: set[str] = set()
    for row in rows:
        if row.get("event") == "process_started":
            try:
                event_at = _dt(row.get("at"))
                if int(row.get("pid")) in observer_pids and event_at and event_at >= now - timedelta(seconds=8):
                    c = row.get("caller_id") or row.get("owner_caller_id")
                    if c:
                        observer_callers.add(str(c))
            except Exception:
                pass
    for row in rows:
        row_at = _dt(row.get("at"))
        row_event = row.get("event")
        if row_at and row_at >= active_cutoff:
            last_event_at = max(last_event_at, row_at) if last_event_at else row_at
            if row_event == "process_started": activity_counts["starts"] += 1
            elif row_event == "process_read": activity_counts["reads"] += 1
            elif row_event == "process_exit_observed":
                activity_counts["exits"] += 1
                if row.get("exit_code") not in (None,0): activity_counts["nonzero_exits"] += 1
            elif row_event == "process_killed": activity_counts["kills"] += 1
        c = row.get("caller_id") or row.get("owner_caller_id")
        if not c or str(c) in observer_callers:
            continue
        at = _dt(row.get("at")); ev = row.get("event"); pid = row.get("process_id")
        if at:
            item = callers.setdefault(str(c), {"first":at,"last":at,"starts":0,"reads":0,"pids":[],"cwd":None})
            item["first"] = min(item["first"], at); item["last"] = max(item["last"], at)
            if ev == "process_started":
                item["starts"] += 1; item["cwd"] = row.get("cwd") or item["cwd"]
                if pid and pid not in item["pids"]: item["pids"].append(pid)
            elif ev == "process_read": item["reads"] += 1
        if pid:
            proc = processes.setdefault(pid, {})
            if ev == "process_started": proc.update(start=at, cwd=row.get("cwd"))
            elif ev in ("process_exit_observed","process_killed"): proc.update(end=at, exit_code=row.get("exit_code"))
    callers = {c:i for c,i in callers.items() if (i["starts"] or i["reads"]) and i["last"] >= active_cutoff}

    receipts = root / "shared-process-receipts"
    git_cache: dict[str, Any] = {}
    details: dict[str, dict[str, Any]] = {}
    for c,item in callers.items():
        pid = item["pids"][-1] if item["pids"] else None
        receipt = {}; command = ""
        if pid:
            try: receipt = json.loads((receipts / f"{pid}.json").read_text(encoding="utf-8-sig"))
            except Exception: receipt = {}
            command = str(receipt.get("command") or "")
        target,basis = _command_target(command)
        worktree = _git_identity(target, git_cache) if target else None
        if not worktree:
            worktree = _git_identity(item["cwd"], git_cache); basis = "launch_cwd" if worktree else None
        proc = processes.get(pid,{}) if pid else {}
        st = proc.get("start") or _dt(receipt.get("started_at")); en = proc.get("end") or _dt(receipt.get("finished_at"))
        latest = None
        if st:
            latest = {"end_observed":bool(en),"elapsed_seconds":round(((en or now)-st).total_seconds(),1),"semantics":"duration" if en else "since_start_no_end_observed"}
        details[c] = {
            "caller_id":c,
            "last_activity_age_seconds":round((now-item["last"]).total_seconds(),1),
            "observed_span_minutes":round((now-item["first"]).total_seconds()/60,1),
            "observed_span_lower_bound":bool(not complete or item["first"] <= cutoff + timedelta(seconds=2)),
            "workspace":_workspace(worktree["path"] if worktree else item["cwd"]),
            "worktree":worktree,
            "worktree_evidence":basis,
            "latest_process":latest,
            "command":" ".join(command.split())[:120],
        }

    busy_path = Path(os.path.expandvars(r"%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json"))
    try:
        busy = json.loads(busy_path.read_text(encoding="utf-8-sig")); jobs_raw = ((busy.get("coordinator") or {}).get("jobs") or {})
        busy_age = max(0.0,(now-datetime.fromtimestamp(busy_path.stat().st_mtime,timezone.utc)).total_seconds())
    except Exception:
        jobs_raw = {}; busy_age = None
    jobs=[]
    for j in jobs_raw.values() if isinstance(jobs_raw,dict) else []:
        ex=_dt(j.get("lease_expires_at"))
        if isinstance(j,dict) and j.get("state")=="active" and (not ex or ex>now): jobs.append(j)
    owners: dict[str,list[dict[str,Any]]] = {}
    for j in jobs:
        o=str(j.get("owner") or "")
        if o: owners.setdefault(o,[]).append(j)

    lanes: dict[str,dict[str,Any]] = {}
    branch_lane: dict[str,str] = {}
    def wt_key(g: dict[str,Any]) -> str:
        return "wt:" + os.path.normcase(os.path.normpath(g["path"]))
    for d in details.values():
        g=d.get("worktree")
        key=wt_key(g) if g else "caller:"+d["caller_id"]
        lane=lanes.setdefault(key,{"lane_id":key,"basis":"worktree" if g else "caller_activity","workspace":d.get("workspace"),"worktree":g,"callers":[],"busy":[]})
        lane["callers"].append(d)
        if g and g.get("branch") and g.get("branch") not in ("HEAD","(detached)"):
            branch_lane[str(g["branch"]).casefold()]=key
    for owner,owner_jobs in owners.items():
        candidate_keys=set()
        for j in owner_jobs:
            scope=str(j.get("scope") or "")
            m=re.search(r"refs/heads/(.+)$",scope,re.I)
            if m and m.group(1).casefold() in branch_lane:
                candidate_keys.add(branch_lane[m.group(1).casefold()])
            elif re.match(r"^[A-Za-z]:[\\/]",scope):
                normalized=os.path.normcase(os.path.normpath(scope))
                for lane_key,lane_value in lanes.items():
                    g=lane_value.get("worktree")
                    if not g: continue
                    root_norm=os.path.normcase(os.path.normpath(g["path"]))
                    if normalized==root_norm or normalized.startswith(root_norm+os.sep):
                        candidate_keys.add(lane_key)
        key=next(iter(candidate_keys)) if len(candidate_keys)==1 else "busy:"+owner.casefold()
        if key not in lanes:
            lanes[key]={"lane_id":key,"basis":"busy_owner","workspace":None,"worktree":None,"callers":[],"busy":[]}
        claim_times=[x for x in (_dt(j.get("claim_timestamp")) for j in owner_jobs) if x]
        update_times=[x for x in (_dt(j.get("updated_at")) for j in owner_jobs) if x]
        lanes[key]["busy"].append({
            "owner":owner,
            "scope_count":len(owner_jobs),
            "scopes":[str(j.get("scope")) for j in owner_jobs if j.get("scope")],
            "claim_age_minutes":round((now-min(claim_times)).total_seconds()/60,1) if claim_times else None,
            "last_update_age_seconds":round((now-max(update_times)).total_seconds(),1) if update_times else None,
            "checkpoint":next((str(j.get("checkpoint")) for j in owner_jobs if j.get("checkpoint")),None),
        })
    lane_list=list(lanes.values())
    lane_list.sort(key=lambda lane:min(
        [float(c["last_activity_age_seconds"]) for c in lane["callers"] if c.get("last_activity_age_seconds") is not None]
        +[float(b["last_update_age_seconds"]) for b in lane["busy"] if b.get("last_update_age_seconds") is not None]+[1e9]
    ))
    workspace_counts: dict[str,int]={}
    for d in details.values():
        w=d.get("workspace") or "Unknown"; workspace_counts[w]=workspace_counts.get(w,0)+1
    result={
        "schema":"live-swarm.v1","available":True,"generated_at":now.isoformat(),
        "summary":{
            "recent_callers":len(details),"lanes":len(lane_list),
            "worktree_lanes":sum(1 for l in lane_list if l["basis"]=="worktree"),
            "busy_only_lanes":sum(1 for l in lane_list if l["basis"]=="busy_owner"),
            "activity_only_lanes":sum(1 for l in lane_list if l["basis"]=="caller_activity"),
            "busy_owners":len(owners),"busy_scopes":len(jobs),"workspace_counts":workspace_counts,
        },
        "evidence":{
            "source_age_seconds":round(max(0.0,(now-datetime.fromtimestamp(source.stat().st_mtime,timezone.utc)).total_seconds()),1),
            "activity_window_seconds":ACTIVITY_WINDOW_SECONDS,"observation_window_minutes":OBSERVATION_WINDOW_MINUTES,
            "observation_window_complete":complete,"sample_bytes":sample_bytes,
            "busy_source_age_seconds":round(busy_age,1) if busy_age is not None else None,
            "execution_reference_minutes":EXECUTION_REFERENCE_MINUTES,
            "execution_reference_semantics":"orientation_only_not_remaining_time",
            "observer_callers_excluded":sorted(observer_callers),
            "activity_summary":{**activity_counts,"last_event_at":last_event_at.isoformat() if last_event_at else None},
        },
        "lanes":lane_list,
    }
    result["elapsed_ms"]=round((time.perf_counter()-started)*1000,1)
    return result


def compact_for_bootstrap(snapshot: dict[str,Any], lane_limit: int=8) -> dict[str,Any]:
    lanes=[]
    for lane in list(snapshot.get("lanes") or [])[:lane_limit]:
        lanes.append({
            "basis":lane.get("basis"),"workspace":lane.get("workspace"),"worktree":lane.get("worktree"),
            "callers":[{k:c.get(k) for k in ("caller_id","last_activity_age_seconds","observed_span_minutes","observed_span_lower_bound","latest_process") if c.get(k) is not None} for c in lane.get("callers",[])],
            "busy":[{k:b.get(k) for k in ("owner","scope_count","claim_age_minutes","last_update_age_seconds","checkpoint") if b.get(k) is not None} for b in lane.get("busy",[])],
        })
    return {"summary":snapshot.get("summary",{}),"evidence":snapshot.get("evidence",{}),"lanes":lanes,"lanes_truncated":len(snapshot.get("lanes") or [])>len(lanes),"elapsed_ms":snapshot.get("elapsed_ms")}
