from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from recurring_slot_registry import load_slot_snapshot
except ModuleNotFoundError:  # imported as ``tools.live_swarm`` from the repository package
    from tools.recurring_slot_registry import load_slot_snapshot

ACTIVITY_WINDOW_SECONDS = 300
ACTIVITY_COUNT_WINDOWS = (("15s", 15), ("60s", 60), ("2m", 120), ("5m", 300), ("15m", 900), ("30m", 1800))
ACTIVITY_BUCKET_WINDOWS = (("0_15s", 0, 15), ("15_60s", 15, 60), ("1_2m", 60, 120), ("2_5m", 120, 300), ("5_15m", 300, 900), ("15_30m", 900, 1800))
OBSERVATION_WINDOW_MINUTES = 30.0
EXECUTION_REFERENCE_MINUTES = 27.0
MAX_TRANSPORT_BYTES = 8 * 1024 * 1024
MAX_TRANSPORT_SOURCE_CANDIDATES = 64
MAX_TRANSPORT_SOURCES = 16
TRANSPORT_DISCOVERY_TAIL_BYTES = 64 * 1024
TRANSPORT_KIND = "MCPv4"
ACTOR_BINDING_TTL_HOURS = 8.0
ACTOR_IDENTIFY_LOOKBACK_SECONDS = 120


def _repo_root() -> Path:
    return Path(os.environ.get("STACK_ATLAS_ROOT_OVERRIDE") or Path(__file__).resolve().parent.parent).resolve()


def _dt(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _action_mode(action_class: Any) -> str:
    """Return PLAN_ONLY only for explicitly plan-labelled action classes; never infer execution."""
    normalized = re.sub(r"[^a-z0-9]+", "_", str(action_class or "").casefold()).strip("_")
    if normalized in {"plan", "planning", "plan_only", "planonly"} or normalized.endswith("_plan"):
        return "PLAN_ONLY"
    return "UNKNOWN"


def _read_window(path: Path, cutoff: datetime, max_bytes: int = MAX_TRANSPORT_BYTES) -> tuple[list[dict[str, Any]], bool, int]:
    parts: list[bytes] = []
    size = path.stat().st_size
    pos = size
    read = 0
    complete = size == 0
    with path.open("rb") as handle:
        while pos > 0 and read < max_bytes:
            take = min(256 * 1024, pos, max_bytes - read)
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


def _latest_event_timestamp(path: Path, max_bytes: int = TRANSPORT_DISCOVERY_TAIL_BYTES) -> tuple[datetime | None, int]:
    """Read only a small tail to identify whether a transport source is current."""
    try:
        size = path.stat().st_size
        take = min(size, max_bytes)
        with path.open("rb") as handle:
            if take:
                handle.seek(size - take)
            data = handle.read(take)
    except OSError:
        return None, 0
    for raw in reversed(data.splitlines()):
        try:
            row = json.loads(raw.decode("utf-8-sig"))
        except Exception:
            continue
        if not isinstance(row, dict):
            continue
        at = _dt(row.get("at"))
        if at is not None:
            return at, take
    return None, take


def _transport_instance(path: Path) -> str:
    if path.parent.name == "transport.jsonl.archive":
        return path.parent.parent.name
    return path.parent.name


def _discover_transport_sources(root: Path, cutoff: datetime, now: datetime) -> tuple[list[tuple[Path, datetime]], dict[str, Any]]:
    """Discover one bounded current MCPv4 transport source per connector instance."""
    try:
        active = list(root.glob("*/transport.jsonl"))
        archive_dirs = list(root.glob("*/transport.jsonl.archive"))
    except OSError:
        active, archive_dirs = [], []

    candidates = list(active)
    for archive_dir in archive_dirs:
        try:
            newest = max(
                (path for path in archive_dir.iterdir() if path.is_file() and path.suffix.lower() == ".jsonl"),
                key=lambda path: path.stat().st_mtime,
                default=None,
            )
        except OSError:
            newest = None
        if newest is not None:
            candidates.append(newest)

    candidate_count = len(candidates)
    candidate_truncated = candidate_count > MAX_TRANSPORT_SOURCE_CANDIDATES
    candidate_truncation_affects_window = False
    candidate_truncation_affects_activity_window = False
    if candidate_truncated:
        def candidate_mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                # Unknown freshness must stay conservative: retain it ahead of
                # known-old candidates and treat an omitted unknown as relevant.
                return float("inf")

        ordered = sorted(candidates, key=candidate_mtime, reverse=True)
        omitted = ordered[MAX_TRANSPORT_SOURCE_CANDIDATES:]
        candidates = ordered[:MAX_TRANSPORT_SOURCE_CANDIDATES]
        cutoff_timestamp = cutoff.timestamp()
        activity_cutoff_timestamp = (now - timedelta(seconds=ACTIVITY_WINDOW_SECONDS)).timestamp()
        candidate_truncation_affects_window = any(
            candidate_mtime(path) >= cutoff_timestamp for path in omitted
        )
        candidate_truncation_affects_activity_window = any(
            candidate_mtime(path) >= activity_cutoff_timestamp for path in omitted
        )

    by_instance: dict[str, tuple[Path, datetime]] = {}
    discovery_bytes = 0
    future_limit = now + timedelta(minutes=2)
    for path in candidates:
        latest, read_bytes = _latest_event_timestamp(path)
        discovery_bytes += read_bytes
        if latest is None or not (cutoff <= latest <= future_limit):
            continue
        instance = _transport_instance(path)
        current = by_instance.get(instance)
        if current is None or latest > current[1]:
            by_instance[instance] = (path, latest)

    discovered = sorted(by_instance.values(), key=lambda item: item[1], reverse=True)
    source_truncated = len(discovered) > MAX_TRANSPORT_SOURCES
    omitted_sources = discovered[MAX_TRANSPORT_SOURCES:]
    activity_cutoff = now - timedelta(seconds=ACTIVITY_WINDOW_SECONDS)
    source_truncation_affects_activity_window = any(latest >= activity_cutoff for _, latest in omitted_sources)
    selected = discovered[:MAX_TRANSPORT_SOURCES]
    return selected, {
        "candidate_count": candidate_count,
        "candidate_truncated": candidate_truncated,
        "candidate_truncation_affects_window": candidate_truncation_affects_window,
        "candidate_truncation_affects_activity_window": candidate_truncation_affects_activity_window,
        "source_truncated": source_truncated,
        "source_truncation_affects_activity_window": source_truncation_affects_activity_window,
        "discovery_bytes": discovery_bytes,
    }


def _transport_runtime_identity(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Latest backend PID/listener port observed in one transport source."""
    latest_server: tuple[datetime, int] | None = None
    latest_port: tuple[datetime, int] | None = None
    for row in rows:
        at = _dt(row.get("at"))
        if at is None:
            continue
        try:
            server_pid = int(row.get("server_pid"))
            if server_pid > 0 and (latest_server is None or at >= latest_server[0]):
                latest_server = (at, server_pid)
        except (TypeError, ValueError):
            pass
        try:
            local_port = int(row.get("local_port"))
            if 0 < local_port <= 65535 and (latest_port is None or at >= latest_port[0]):
                latest_port = (at, local_port)
        except (TypeError, ValueError):
            pass
    result: dict[str, int] = {}
    if latest_server is not None:
        result["server_pid"] = latest_server[1]
    if latest_port is not None:
        result["local_port"] = latest_port[1]
    return result


def _local_appdata_root() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if value:
        return Path(value)
    return Path(os.path.expandvars(r"%LOCALAPPDATA%"))



def _actor_binding_dir() -> Path:
    return _local_appdata_root() / "ChatGPTMcpClean" / ".state" / "swarm-actor-bindings"


def _normalize_actor(value: Any) -> str | None:
    actor = " ".join(str(value or "").strip().split())
    if not actor or len(actor) > 96 or any(ord(ch) < 32 for ch in actor):
        return None
    return actor


def _actor_binding_path(caller_id: str) -> Path | None:
    caller = str(caller_id or "")
    if not re.fullmatch(r"caller_[A-Za-z0-9_-]{4,80}", caller):
        return None
    return _actor_binding_dir() / f"{caller}.json"


def _load_explicit_actor_binding(caller_id: str, now: datetime) -> dict[str, Any] | None:
    path = _actor_binding_path(caller_id)
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("caller_id") != caller_id:
        return None
    actor = _normalize_actor(payload.get("actor"))
    bound_at = _dt(payload.get("bound_at"))
    if actor is None or bound_at is None:
        return None
    age = max(0.0, (now - bound_at).total_seconds())
    if age > ACTOR_BINDING_TTL_HOURS * 3600:
        return None
    return {"actor": actor, "bound_at": bound_at.isoformat(), "age_seconds": round(age, 1)}


def _find_current_caller_id(*, now: datetime | None = None, parent_pid: int | None = None) -> str | None:
    now = now or datetime.now(timezone.utc)
    parent_pid = int(parent_pid if parent_pid is not None else os.getppid())
    root = _local_appdata_root() / "ChatGPTMcpClean" / "minimal-connectors"
    cutoff = now - timedelta(seconds=ACTOR_IDENTIFY_LOOKBACK_SECONDS)
    sources, _ = _discover_transport_sources(root, cutoff, now)
    matches: list[tuple[datetime, str]] = []
    for source, _latest in sources:
        try:
            rows, _, _ = _read_window(source, cutoff, max_bytes=512 * 1024)
        except Exception:
            continue
        for row in rows:
            if row.get("event") != "process_started":
                continue
            try:
                row_pid = int(row.get("pid"))
            except Exception:
                continue
            if row_pid != parent_pid:
                continue
            caller = row.get("caller_id") or row.get("owner_caller_id")
            at = _dt(row.get("at"))
            if caller and at:
                matches.append((at, str(caller)))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    newest_at = matches[0][0]
    newest = {caller for at, caller in matches if abs((newest_at - at).total_seconds()) <= 2}
    return next(iter(newest)) if len(newest) == 1 else None


def identify_current_actor(actor: str, *, now: datetime | None = None, parent_pid: int | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    normalized = _normalize_actor(actor)
    if normalized is None:
        return {"status": "INVALID_ACTOR", "bound": False}
    caller_id = _find_current_caller_id(now=now, parent_pid=parent_pid)
    if caller_id is None:
        return {"status": "CALLER_NOT_RESOLVED", "bound": False, "actor": normalized}
    path = _actor_binding_path(caller_id)
    if path is None:
        return {"status": "CALLER_NOT_RESOLVED", "bound": False, "actor": normalized}
    payload = {
        "schema": "swarm-actor-binding.v1",
        "caller_id": caller_id,
        "actor": normalized,
        "source": "self_declared",
        "bound_at": now.isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return {"status": "BOUND", "bound": True, **payload}


def _actor_name_from_binding_label(label: str, partition: str) -> str:
    name = re.sub(r"^Repo\s+Worker\s+", "", str(label or "").strip(), flags=re.I)
    part = re.escape(str(partition or "").strip())
    if part:
        name = re.sub(rf"\s+#?{part}(?:\s+New)?\s*$", "", name, flags=re.I)
    return name.strip()


def _actor_specs_from_slot_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    if snapshot.get("status") != "OK":
        return []

    raw: list[tuple[str, str, str]] = []
    for binding in snapshot.get("bound_workers", []):
        if not isinstance(binding, dict):
            continue
        partition = str(binding.get("partition") or "").strip().upper()
        slot_id = str(binding.get("slot_id") or "").strip().upper()
        name = _actor_name_from_binding_label(str(binding.get("label") or ""), partition)
        if partition and slot_id and name:
            raw.append((partition, slot_id, name))

    counts: dict[str, int] = {}
    for _, _, name in raw:
        key = name.casefold()
        counts[key] = counts.get(key, 0) + 1
    return [
        {
            "actor": f"{partition}/{name}",
            "partition": partition.casefold(),
            "slot_id": slot_id,
            "name": name.casefold(),
            "name_unique": counts.get(name.casefold(), 0) == 1,
        }
        for partition, slot_id, name in raw
    ]


def _canonical_actor_specs(root: Path | None = None) -> list[dict[str, Any]]:
    actor_root = root or _repo_root()
    return _actor_specs_from_slot_snapshot(load_slot_snapshot(actor_root))


def _actor_candidate_map(detail: dict[str, Any], busy_entries: list[dict[str, Any]], specs: list[dict[str, Any]]) -> dict[str, set[str]]:
    evidence_texts: list[tuple[str, str]] = []
    worktree = detail.get("worktree") if isinstance(detail.get("worktree"), dict) else {}
    if worktree.get("branch"):
        evidence_texts.append(("worktree_branch", str(worktree["branch"])))
    if worktree.get("path"):
        evidence_texts.append(("worktree_path", str(worktree["path"])))
    for busy in busy_entries:
        if busy.get("owner"):
            evidence_texts.append(("busy_owner", str(busy["owner"])))
        scopes = busy.get("scopes") if isinstance(busy.get("scopes"), list) else []
        for scope in scopes:
            if scope:
                evidence_texts.append(("busy_scope", str(scope)))
    candidates: dict[str, set[str]] = {}
    for source, text in evidence_texts:
        tokens = set(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())
        for spec in specs:
            name_tokens = set(re.sub(r"[^a-z0-9]+", " ", spec["name"]).split())
            if not name_tokens or not name_tokens.issubset(tokens):
                continue
            partition_present = spec["partition"] in tokens
            if not partition_present and not spec["name_unique"]:
                continue
            candidates.setdefault(str(spec["actor"]), set()).add(source)
    return candidates


def _resolve_caller_identity(
    detail: dict[str, Any],
    busy_entries: list[dict[str, Any]],
    *,
    now: datetime,
    specs: list[dict[str, Any]],
) -> dict[str, Any]:
    caller_id = str(detail.get("caller_id") or "")
    explicit = _load_explicit_actor_binding(caller_id, now)
    candidates = _actor_candidate_map(detail, busy_entries, specs)
    candidate_rows = [
        {"actor": actor, "sources": sorted(sources)}
        for actor, sources in sorted(candidates.items())
    ]
    if explicit:
        actor = explicit["actor"]
        result: dict[str, Any] = {
            "status": "ATTRIBUTED",
            "actor": actor,
            "source": "self_declared",
            "bound_at": explicit["bound_at"],
        }
        if actor in candidates:
            result["corroborated_by"] = sorted(candidates[actor])
        other = [row for row in candidate_rows if row["actor"] != actor]
        if other:
            result["diagnostic"] = "RESOLVER_MISMATCH"
            result["resolver_candidates"] = candidate_rows
        return result
    if len(candidates) == 1:
        actor, sources = next(iter(candidates.items()))
        return {
            "status": "ATTRIBUTED",
            "actor": actor,
            "source": "resolved",
            "resolved_by": sorted(sources),
        }
    result = {"status": "UNATTRIBUTED", "actor": None, "source": None}
    if candidate_rows:
        result["diagnostic"] = "AMBIGUOUS_RESOLVER_CANDIDATES"
        result["resolver_candidates"] = candidate_rows
    return result


def _resolve_busy_identity(busy: dict[str, Any], specs: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = _actor_candidate_map({"worktree": None}, [busy], specs)
    candidate_rows = [
        {"actor": actor, "sources": sorted(sources)}
        for actor, sources in sorted(candidates.items())
    ]
    if len(candidates) == 1:
        actor, sources = next(iter(candidates.items()))
        return {
            "status": "ATTRIBUTED",
            "actor": actor,
            "source": "resolved_coordination",
            "resolved_by": sorted(sources),
        }
    result: dict[str, Any] = {"status": "UNATTRIBUTED", "actor": None, "source": None}
    if candidate_rows:
        result["diagnostic"] = "AMBIGUOUS_COORDINATION_ACTOR"
        result["resolver_candidates"] = candidate_rows
    return result


def _recurring_actor_evidence(
    specs: list[dict[str, Any]],
    callers: list[dict[str, Any]],
    lanes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    busy_entries = [
        busy
        for lane in lanes
        for busy in lane.get("busy", [])
        if isinstance(busy, dict)
    ]
    for spec in sorted(specs, key=lambda item: str(item.get("slot_id") or item.get("actor") or "")):
        actor = str(spec.get("actor") or "")
        actor_callers = [
            caller for caller in callers
            if (caller.get("identity") or {}).get("status") == "ATTRIBUTED"
            and (caller.get("identity") or {}).get("actor") == actor
        ]
        actor_busy = [
            busy for busy in busy_entries
            if (busy.get("identity") or {}).get("status") == "ATTRIBUTED"
            and (busy.get("identity") or {}).get("actor") == actor
        ]
        actor_callers.sort(key=lambda item: float(item["last_activity_age_seconds"]) if item.get("last_activity_age_seconds") is not None else 1e9)
        actor_busy.sort(key=lambda item: float(item["last_update_age_seconds"]) if item.get("last_update_age_seconds") is not None else 1e9)
        if actor_callers:
            evidence_state = "RECENT_ATTRIBUTED_MCP_ACTIVITY"
        elif actor_busy:
            evidence_state = "RECENT_COORDINATION_ONLY"
        else:
            evidence_state = "NO_RECENT_EVIDENCE"
        row: dict[str, Any] = {
            "slot_id": spec.get("slot_id"),
            "actor": actor,
            "evidence_state": evidence_state,
        }
        if actor_callers:
            latest = actor_callers[0]
            worktree = latest.get("worktree") if isinstance(latest.get("worktree"), dict) else {}
            row["mcp"] = {
                "caller_count": len(actor_callers),
                "most_recent_activity_age_seconds": latest.get("last_activity_age_seconds"),
                "identity_source": (latest.get("identity") or {}).get("source"),
                "workspace": latest.get("workspace"),
                "branch": worktree.get("branch"),
                "activity_target": latest.get("activity_target"),
            }
            row["mcp"] = {k: v for k, v in row["mcp"].items() if v is not None}
        if actor_busy:
            latest_busy = actor_busy[0]
            scopes = latest_busy.get("scopes") if isinstance(latest_busy.get("scopes"), list) else []
            row["coordination"] = {
                "owner_count": len({str(item.get("owner")) for item in actor_busy if item.get("owner")}),
                "most_recent_update_age_seconds": latest_busy.get("last_update_age_seconds"),
                "latest_owner": latest_busy.get("owner"),
                "latest_scope": next((str(scope) for scope in scopes if scope), None),
                "checkpoint": latest_busy.get("checkpoint"),
            }
            row["coordination"] = {k: v for k, v in row["coordination"].items() if v is not None}
        rows.append(row)
    return rows


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
    root = _local_appdata_root() / "ChatGPTMcpClean" / "minimal-connectors"
    cutoff = now - timedelta(minutes=OBSERVATION_WINDOW_MINUTES)
    active_cutoff = now - timedelta(seconds=ACTIVITY_WINDOW_SECONDS)
    sources, discovery = _discover_transport_sources(root, cutoff, now)
    if not sources and not discovery.get("candidate_count"):
        return {
            "schema":"live-swarm.v1", "available":False, "lanes":[],
            "summary":{
                "recent_callers":0,
                "active_callers":{label:0 for label,_ in ACTIVITY_COUNT_WINDOWS},
                "lanes":0,
            },
            "evidence":{
                "transport":TRANSPORT_KIND,
                "transport_source_count":0,
                "active_callers_complete_through_seconds":0,
                "active_callers_semantics":"unique_non_observer_callers_with_process_started_or_process_read_in_window",
            },
        }

    rows: list[dict[str, Any]] = []
    complete = not bool(discovery.get("candidate_truncation_affects_window") or discovery.get("source_truncated"))
    activity_complete = not bool(
        discovery.get("candidate_truncation_affects_activity_window")
        or discovery.get("source_truncation_affects_activity_window")
    )
    sample_bytes = 0
    per_source_budget = max(1, MAX_TRANSPORT_BYTES // max(1, len(sources)))
    source_details: list[dict[str, Any]] = []
    for source, latest in sources:
        source_rows, source_complete, read_bytes = _read_window(source, cutoff, max_bytes=per_source_budget)
        rows.extend(source_rows)
        complete = complete and source_complete
        source_activity_complete = source_complete or any(
            (at := _dt(row.get("at"))) is not None and at <= active_cutoff
            for row in source_rows
        )
        activity_complete = activity_complete and source_activity_complete
        sample_bytes += read_bytes
        source_details.append({
            "instance": _transport_instance(source),
            "latest_event_at": latest.isoformat(),
            "observation_window_complete": source_complete,
            "activity_window_complete": source_activity_complete,
            "sample_bytes": read_bytes,
            **_transport_runtime_identity(source_rows),
        })
    rows.sort(key=lambda row: _dt(row.get("at")) or datetime.min.replace(tzinfo=timezone.utc))
    latest_transport_at = max((latest for _, latest in sources), default=None)
    callers: dict[str, dict[str, Any]] = {}
    caller_activity_at: dict[str, datetime] = {}
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
            item = callers.setdefault(str(c), {"first":at,"last":at,"starts":0,"reads":0,"pids":[],"cwd":None,"activity_pid":None})
            item["first"] = min(item["first"], at); item["last"] = max(item["last"], at)
            previous_activity = caller_activity_at.get(str(c))
            if ev == "process_started":
                item["starts"] += 1; item["cwd"] = row.get("cwd") or item["cwd"]
                if previous_activity is None or at >= previous_activity: item["activity_pid"] = pid
                caller_activity_at[str(c)] = max(previous_activity or at, at)
                if pid and pid not in item["pids"]: item["pids"].append(pid)
            elif ev == "process_read":
                item["reads"] += 1
                if previous_activity is None or at >= previous_activity: item["activity_pid"] = pid
                caller_activity_at[str(c)] = max(previous_activity or at, at)
        if pid:
            proc = processes.setdefault(pid, {})
            if ev == "process_started": proc.update(start=at, cwd=row.get("cwd"), action_class=row.get("action_class"), activity_target=row.get("activity_target"))
            elif ev in ("process_exit_observed","process_killed"): proc.update(end=at, exit_code=row.get("exit_code"))
    active_callers = {
        label: sum(1 for at in caller_activity_at.values() if at >= now - timedelta(seconds=seconds))
        for label, seconds in ACTIVITY_COUNT_WINDOWS
    }
    activity_buckets = {}
    for label, lower, upper in ACTIVITY_BUCKET_WINDOWS:
        activity_buckets[label] = sum(
            1
            for at in caller_activity_at.values()
            if (age := max(0.0, (now - at).total_seconds())) <= upper and (lower == 0 or age > lower)
        )
    active_callers_complete_through_seconds = (
        int(OBSERVATION_WINDOW_MINUTES * 60) if complete else ACTIVITY_WINDOW_SECONDS if activity_complete else 0
    )
    callers = {
        c:i for c,i in callers.items()
        if (activity_at := caller_activity_at.get(c)) is not None and activity_at >= active_cutoff
    }

    receipts = root / "shared-process-receipts"
    git_cache: dict[str, Any] = {}
    details: dict[str, dict[str, Any]] = {}
    for c,item in callers.items():
        pid = item.get("activity_pid") or (item["pids"][-1] if item["pids"] else None)
        receipt = {}; command = ""
        if pid:
            try: receipt = json.loads((receipts / f"{pid}.json").read_text(encoding="utf-8-sig"))
            except Exception: receipt = {}
            command = str(receipt.get("command") or "")
        proc = processes.get(pid,{}) if pid else {}
        action_class = proc.get("action_class") or receipt.get("action_class")
        activity_target = proc.get("activity_target") or receipt.get("activity_target")
        target,basis = _command_target(command)
        worktree = _git_identity(target, git_cache) if target else None
        if not worktree:
            worktree = _git_identity(item["cwd"], git_cache); basis = "launch_cwd" if worktree else None
        st = proc.get("start") or _dt(receipt.get("started_at")); en = proc.get("end") or _dt(receipt.get("finished_at"))
        latest = None
        if st:
            latest = {"end_observed":bool(en),"elapsed_seconds":round(((en or now)-st).total_seconds(),1),"semantics":"duration" if en else "since_start_no_end_observed"}
        details[c] = {
            "caller_id":c,
            "last_activity_age_seconds":round((now-caller_activity_at[c]).total_seconds(),1),
            "observed_span_minutes":round((now-item["first"]).total_seconds()/60,1),
            "observed_span_lower_bound":bool(not complete or item["first"] <= cutoff + timedelta(seconds=2)),
            "workspace":_workspace(worktree["path"] if worktree else item["cwd"]),
            "worktree":worktree,
            "worktree_evidence":basis,
            "latest_process":latest,
            "mode":_action_mode(action_class),
            "action_class":str(action_class) if action_class else None,
            "activity_target":activity_target if isinstance(activity_target, dict) else None,
            "command":" ".join(command.split())[:120],
        }

    busy_path = _local_appdata_root() / "ChatGPTMcpClean" / ".state" / "busy-claims.json"
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
    slot_snapshot = load_slot_snapshot(_repo_root())
    actor_specs = _actor_specs_from_slot_snapshot(slot_snapshot)
    for lane in lane_list:
        for busy_entry in lane["busy"]:
            busy_entry["identity"] = _resolve_busy_identity(busy_entry, actor_specs)
        for caller in lane["callers"]:
            caller["identity"] = _resolve_caller_identity(caller, lane["busy"], now=now, specs=actor_specs)
        caller_ages = [float(c["last_activity_age_seconds"]) for c in lane["callers"] if c.get("last_activity_age_seconds") is not None]
        if any(age <= 60 for age in caller_ages): lane["state"] = "ACTIVE"
        elif caller_ages: lane["state"] = "RECENT"
        elif lane["busy"]: lane["state"] = "BUSY_NO_RECENT_MCP_ACTIVITY"
        else: lane["state"] = "UNKNOWN"
    lane_list.sort(key=lambda lane:min(
        [float(c["last_activity_age_seconds"]) for c in lane["callers"] if c.get("last_activity_age_seconds") is not None]
        +[float(b["last_update_age_seconds"]) for b in lane["busy"] if b.get("last_update_age_seconds") is not None]+[1e9]
    ))
    caller_list=sorted(details.values(), key=lambda item: float(item.get("last_activity_age_seconds") or 1e9))
    caller_modes={"PLAN_ONLY":sum(1 for d in caller_list if d.get("mode")=="PLAN_ONLY"),"UNKNOWN":sum(1 for d in caller_list if d.get("mode")!="PLAN_ONLY")}
    attributed = [d for d in caller_list if (d.get("identity") or {}).get("status") == "ATTRIBUTED"]
    identity_summary = {
        "attributed": len(attributed),
        "unattributed": len(caller_list) - len(attributed),
        "self_declared": sum(1 for d in attributed if (d.get("identity") or {}).get("source") == "self_declared"),
        "resolved": sum(1 for d in attributed if (d.get("identity") or {}).get("source") == "resolved"),
        "resolver_mismatches": sum(1 for d in attributed if (d.get("identity") or {}).get("diagnostic") == "RESOLVER_MISMATCH"),
        "semantics": "missing_or_ambiguous_actor_attribution_is_normal_and_does_not_degrade_swarm_health",
    }
    lane_states: dict[str,int]={}
    for lane in lane_list:
        state=str(lane.get("state") or "UNKNOWN"); lane_states[state]=lane_states.get(state,0)+1
    workspace_counts: dict[str,int]={}
    for d in details.values():
        w=d.get("workspace") or "Unknown"; workspace_counts[w]=workspace_counts.get(w,0)+1
    recurring_actors = _recurring_actor_evidence(actor_specs, caller_list, lane_list)
    recurring_states: dict[str, int] = {}
    for row in recurring_actors:
        state = str(row.get("evidence_state") or "NO_RECENT_EVIDENCE")
        recurring_states[state] = recurring_states.get(state, 0) + 1
    unbound_slots = [
        str(slot.get("slot_id"))
        for partition in (slot_snapshot.get("partitions") or {}).values()
        for slot in (partition.get("slots") or [])
        if isinstance(slot, dict) and not slot.get("bound") and slot.get("slot_id")
    ] if slot_snapshot.get("status") == "OK" else []
    recurring_actor_summary = {
        "slot_registry_status": slot_snapshot.get("status"),
        "available": slot_snapshot.get("status") == "OK",
        "bound_actors": len(recurring_actors),
        "unbound_slots": sorted(unbound_slots),
        "evidence_states": recurring_states,
        "semantics": "evidence_fusion_only_not_worker_health; coordination_only_is_not_liveness; no_recent_evidence_is_not_dead_or_scheduler_failure",
    }
    result={
        "schema":"live-swarm.v1","available":True,"generated_at":now.isoformat(),
        "summary":{
            "recent_callers":len(details),"active_callers":active_callers,"activity_buckets":activity_buckets,"caller_modes":caller_modes,"lanes":len(lane_list),
            "worktree_lanes":sum(1 for l in lane_list if l["basis"]=="worktree"),
            "busy_only_lanes":sum(1 for l in lane_list if l["basis"]=="busy_owner"),
            "activity_only_lanes":sum(1 for l in lane_list if l["basis"]=="caller_activity"),
            "busy_owners":len(owners),"busy_scopes":len(jobs),"lane_states":lane_states,"workspace_counts":workspace_counts,"identity":identity_summary,
            "recurring_actor_evidence":recurring_actor_summary,
        },
        "evidence":{
            "transport":TRANSPORT_KIND,
            "transport_source_count":len(sources),
            "source_age_seconds":round(max(0.0,(now-latest_transport_at).total_seconds()),1) if latest_transport_at else None,
            "activity_window_seconds":ACTIVITY_WINDOW_SECONDS,"observation_window_minutes":OBSERVATION_WINDOW_MINUTES,
            "activity_window_complete":activity_complete,"observation_window_complete":complete,"sample_bytes":sample_bytes,
            "active_callers_complete_through_seconds":active_callers_complete_through_seconds,
            "active_callers_semantics":"unique_non_observer_callers_with_process_started_or_process_read_in_window",
            "activity_buckets_semantics":"non_overlapping_unique_callers_by_latest_process_started_or_process_read_age",
            "caller_mode_semantics":"PLAN_ONLY_only_when_latest_activity_process_action_class_is_explicitly_plan_labelled; otherwise_UNKNOWN",
            "actor_attribution_semantics":"self_declared_current_caller_binding_wins; passive_resolver_is_corroborating_or_fallback_only; missing_identity_is_not_health_failure",
            "recurring_actor_evidence_semantics":"bound-slot projection joins attributed MCP activity and deterministic Busy coordination; coordination_only and no_recent_evidence are not liveness or health verdicts",
            "actor_self_identify_command":"python tools/live_swarm.py identify-actor <semantic-actor>",
            "busy_source_age_seconds":round(busy_age,1) if busy_age is not None else None,
            "execution_reference_minutes":EXECUTION_REFERENCE_MINUTES,
            "execution_reference_semantics":"orientation_only_not_remaining_time",
            "observer_callers_excluded":sorted(observer_callers),
            "activity_summary":{**activity_counts,"last_event_at":last_event_at.isoformat() if last_event_at else None},
        },
        "callers":caller_list,
        "recurring_actors":recurring_actors,
        "transport_sources":source_details,
        "transport_source_discovery":{
            "bytes":discovery.get("discovery_bytes"),
            "truncated":bool(discovery.get("candidate_truncated") or discovery.get("source_truncated")),
            "truncation_affects_window":bool(discovery.get("candidate_truncation_affects_window") or discovery.get("source_truncated")),
            "truncation_affects_activity_window":bool(
                discovery.get("candidate_truncation_affects_activity_window")
                or discovery.get("source_truncation_affects_activity_window")
            ),
        },
        "lanes":lane_list,
    }
    result["elapsed_ms"]=round((time.perf_counter()-started)*1000,1)
    return result


def compact_for_bootstrap(snapshot: dict[str,Any], lane_limit: int=8) -> dict[str,Any]:
    lane_limit=max(0,int(lane_limit))
    summary=dict(snapshot.get("summary") or {})
    recurring_summary=summary.get("recurring_actor_evidence")
    if isinstance(recurring_summary,dict):
        summary["recurring_actor_evidence"]={
            k:recurring_summary.get(k)
            for k in ("available","bound_actors","unbound_slots","evidence_states")
            if recurring_summary.get(k) is not None
        }
    evidence=dict(snapshot.get("evidence") or {})
    evidence.pop("recurring_actor_evidence_semantics",None)
    source_lanes=list(snapshot.get("lanes") or [])
    lanes=[]
    for lane in source_lanes[:lane_limit]:
        lanes.append({
            "basis":lane.get("basis"),"state":lane.get("state"),"workspace":lane.get("workspace"),"worktree":lane.get("worktree"),
            "callers":[{k:c.get(k) for k in ("caller_id","last_activity_age_seconds","observed_span_minutes","observed_span_lower_bound","latest_process","mode","identity") if c.get(k) is not None} for c in lane.get("callers",[])],
            "busy":[{k:b.get(k) for k in ("owner","scope_count","claim_age_minutes","last_update_age_seconds","checkpoint") if b.get(k) is not None} for b in lane.get("busy",[])],
        })
    source_actors=[
        row for row in list(snapshot.get("recurring_actors") or [])
        if str(row.get("evidence_state") or "") != "NO_RECENT_EVIDENCE"
    ]
    state_priority={"RECENT_ATTRIBUTED_MCP_ACTIVITY":0,"RECENT_COORDINATION_ONLY":1}
    source_actors.sort(key=lambda row:(state_priority.get(str(row.get("evidence_state")),9),str(row.get("slot_id") or row.get("actor") or "")))
    actor_limit=2
    recurring_actors=[]
    for row in source_actors[:actor_limit]:
        compact_row={k:row.get(k) for k in ("slot_id","actor","evidence_state") if row.get(k) is not None}
        if isinstance(row.get("mcp"),dict):
            compact_row["mcp"]={
                k:row["mcp"].get(k)
                for k in ("most_recent_activity_age_seconds","workspace","branch","activity_target")
                if row["mcp"].get(k) is not None
            }
        if isinstance(row.get("coordination"),dict):
            compact_row["coordination"]={
                k:row["coordination"].get(k)
                for k in ("most_recent_update_age_seconds","latest_owner")
                if row["coordination"].get(k) is not None
            }
        recurring_actors.append(compact_row)
    return {
        "summary":summary,
        "evidence":evidence,
        "recurring_actors":recurring_actors,
        "lanes":lanes,
        "lane_details":{
            "policy":"most_recent",
            "limit":lane_limit,
            "returned":len(lanes),
            "total":len(source_lanes),
            "bounded":len(source_lanes)>len(lanes),
            "semantics":"bootstrap_detail_bound_not_evidence_truncation",
        },
        "elapsed_ms":snapshot.get("elapsed_ms"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Live MCP swarm activity and fail-soft actor attribution.")
    sub = parser.add_subparsers(dest="command")
    identify = sub.add_parser("identify-actor")
    identify.add_argument("actor")
    args = parser.parse_args(argv)
    if args.command == "identify-actor":
        value = identify_current_actor(args.actor)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value.get("bound") else 2
    print(json.dumps(build_live_swarm_snapshot(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
