from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from .memory_bank import (
        DEFAULT_MANUAL_WORKER_HISTORY,
        DEFAULT_WORKER_HISTORY,
        build_overview,
        load_bank,
    )
    from .memory_timeline import build_timeline, build_timeline_snapshots
    from .repo_timeline import RepoSpec, collect_repo_history, discover_repo_specs, tracked_artifact_events
    from .worker_report_history import worker_history_events
except ImportError:
    from memory_bank import DEFAULT_MANUAL_WORKER_HISTORY, DEFAULT_WORKER_HISTORY, build_overview, load_bank
    from memory_timeline import build_timeline, build_timeline_snapshots
    from repo_timeline import RepoSpec, collect_repo_history, discover_repo_specs, tracked_artifact_events
    from worker_report_history import worker_history_events

ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = ROOT / ".state" / "timeline"
STORE_PATH = STATE_ROOT / "timeline-store.json"
BOOTSTRAP_PATH = STATE_ROOT / "bootstrap-memory-overview.json"
STATUS_PATH = STATE_ROOT / "status.json"
LOCK_PATH = STATE_ROOT / "refresh.lock"

SCHEMA = "vault.timeline.materialized.v1"
BOOTSTRAP_SCHEMA = "vault.timeline.bootstrap.v1"
TASK_NAME = "Vault Timeline Materializer"
DEFAULT_DAYS = 30
DEFAULT_REPO_EVENTS = 1000
DEFAULT_ARTIFACT_EVENTS = 2000
DEFAULT_REFRESH_MINUTES = 5
DEFAULT_MAX_EVENTS = 20000
DEFAULT_GITHUB_EVENTS_PER_KIND = 1000
DEFAULT_DELTA_GITHUB_EVENTS_PER_KIND = 200
DEFAULT_DELTA_REPO_EVENTS_PER_REPO = 200
DEFAULT_DELTA_ARTIFACT_EVENTS = 500
DEFAULT_OVERLAP_MINUTES = 10
LOCK_STALE_MINUTES = 30

_GITHUB_REMOTE_RE = re.compile(r"github\.com[:/](?P<repo>[^/\s]+/[^/\s]+?)(?:\.git)?$", re.I)
_ISSUE_REF_RE = re.compile(r"#(?P<number>\d+)\b")
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b", re.I)
_INCIDENT_RE = re.compile(r"\b(?:INC|RR)-[A-Za-z0-9][A-Za-z0-9._-]*\b", re.I)
_SECRET_LINE_RE = re.compile(r"(?i)\b(?:authorization|bearer|token|secret|password|cookie|credential)\b")
_SAFE_RUNNER_MARKER_RE = re.compile(
    r"(?i)\b(?:running job|job completed|job result|completed with result|finish job request|runner connect|job request)\b"
)
_SUBJECT_PR_SUFFIX_RE = re.compile(r"\s*\(#\d+\)\s*$")
_SUBJECT_ISSUE_PREFIX_RE = re.compile(r"^\s*\[#\d+\]\s*")
_SUBJECT_KIND_PREFIX_RE = re.compile(r"^\s*(?:fix|feat|test|build|docs|chore|refactor|ci)(?:\([^)]*\))?\s*:\s*", re.I)

ARTIFACT_ROOTS = (
    "01 Reports",
    "02 Evidence",
    "03 Fixtures and Experiments",
    "04 Operating Contracts",
    "90 Raw Transcripts",
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _dt(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _run_json(command: list[str], *, timeout: int = 30) -> tuple[Any, str | None]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[:240]
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid json: {exc}"


def _git_value(path: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = proc.stdout.strip() if proc.returncode == 0 else ""
    return value or None


def _github_slug(spec: RepoSpec) -> str | None:
    origin = _git_value(spec.path, "remote", "get-url", "origin")
    if not origin:
        return None
    match = _GITHUB_REMOTE_RE.search(origin.strip())
    return match.group("repo").removesuffix(".git").casefold() if match else None


def _repo_maps(specs: Iterable[RepoSpec]) -> tuple[dict[str, str], dict[str, str]]:
    project_to_slug: dict[str, str] = {}
    slug_to_project: dict[str, str] = {}
    for spec in specs:
        slug = _github_slug(spec)
        if not slug:
            continue
        project_to_slug[spec.project] = slug
        slug_to_project[slug] = spec.project
    return project_to_slug, slug_to_project


def _branch_refs(decorations: Any) -> list[str]:
    return sorted(
        {
            ref.strip().replace("HEAD -> ", "", 1)
            for ref in str(decorations or "").split(",")
            if ref.strip()
        }
    )


def _batch_patch_ids(spec: RepoSpec, *, since: datetime) -> dict[str, str]:
    """Compute stable patch ids for all non-merge commits in one Git pipeline."""
    try:
        log = subprocess.run(
            [
                "git", "-C", str(spec.path), "log", "--all", "--no-merges",
                f"--since={since.isoformat()}", "--max-count=2000",
                "--pretty=format:commit %H", "-p", "--no-ext-diff",
            ],
            capture_output=True,
            timeout=90,
            check=False,
        )
        if log.returncode != 0:
            return {}
        patch = subprocess.run(
            ["git", "patch-id", "--stable"],
            input=log.stdout,
            capture_output=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if patch.returncode != 0:
        return {}
    out: dict[str, str] = {}
    for line in patch.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 2 and len(parts[0]) == 40 and len(parts[1]) == 40:
            out[parts[1].casefold()] = parts[0].casefold()
    return out


def enrich_repo_events(repo_events: list[dict[str, Any]], specs: Iterable[RepoSpec], *, since: datetime) -> None:
    by_project = {spec.project: spec for spec in specs}
    patch_maps = {project: _batch_patch_ids(spec, since=since) for project, spec in by_project.items()}
    for event in repo_events:
        project = str(event.get("project") or "")
        sha = str(event.get("sha") or "").casefold()
        event["branch_refs"] = _branch_refs(event.get("decorations"))
        patch_id = patch_maps.get(project, {}).get(sha)
        if patch_id:
            event["patch_id"] = patch_id


def _event_time_ok(value: Any, since: datetime) -> bool:
    stamp = _dt(value)
    return bool(stamp and stamp >= since.astimezone(stamp.tzinfo))


def github_events(
    specs: Iterable[RepoSpec],
    *,
    since: datetime,
    limit_per_kind: int = DEFAULT_GITHUB_EVENTS_PER_KIND,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {"available": True, "repos": {}, "errors": []}
    for spec in specs:
        slug = _github_slug(spec)
        if not slug:
            continue
        repo_cov = {
            "project": spec.project,
            "issues": {"events": 0, "limit": limit_per_kind, "saturated": False},
            "prs": {"events": 0, "limit": limit_per_kind, "saturated": False},
            "actions": {"events": 0, "limit": limit_per_kind, "saturated": False},
        }
        updated_filter = "updated:>=" + since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        issue_rows, err = _run_json([
            "gh", "issue", "list", "--repo", slug, "--state", "all",
            "--search", updated_filter,
            "--limit", str(limit_per_kind),
            "--json", "number,title,state,createdAt,updatedAt,closedAt,url",
        ])
        if err:
            coverage["errors"].append({"repo": slug, "source": "issues", "error": err})
        for row in issue_rows if isinstance(issue_rows, list) else []:
            event_at = row.get("updatedAt") or row.get("createdAt")
            if not _event_time_ok(event_at, since):
                continue
            number = int(row.get("number") or 0)
            anchor = f"github:{slug}#{number}"
            events.append({
                "id": f"github-issue:{slug}#{number}:{event_at}",
                "source_type": "GITHUB_ISSUE",
                "authority": "GITHUB_HISTORY_SNAPSHOT",
                "event_at": event_at,
                "recorded_at": event_at,
                "project": spec.project,
                "projects": [spec.project],
                "title": f"Issue #{number}: {row.get('title') or ''}".strip(),
                "summary": f"state={row.get('state')}",
                "github_repo": slug,
                "github_number": number,
                "github_kind": "issue",
                "state": row.get("state"),
                "url": row.get("url"),
                "refs": [f"#{number}"],
                "anchors": [anchor, f"issue:{anchor}"],
                "thread_id": f"issue:{anchor}",
                "thread_source": "GITHUB_OBJECT",
            })
            repo_cov["issues"]["events"] += 1

        pr_rows, err = _run_json([
            "gh", "pr", "list", "--repo", slug, "--state", "all",
            "--search", updated_filter,
            "--limit", str(limit_per_kind),
            "--json", "number,title,state,createdAt,updatedAt,closedAt,mergedAt,url,headRefName,baseRefName,headRefOid",
        ])
        if err:
            coverage["errors"].append({"repo": slug, "source": "prs", "error": err})
        for row in pr_rows if isinstance(pr_rows, list) else []:
            event_at = row.get("updatedAt") or row.get("mergedAt") or row.get("createdAt")
            if not _event_time_ok(event_at, since):
                continue
            number = int(row.get("number") or 0)
            anchor = f"github:{slug}#{number}"
            head_sha = str(row.get("headRefOid") or "").casefold()
            anchors = [anchor, f"pr:{anchor}"]
            if head_sha:
                anchors.append(f"gitsha:{head_sha}")
            events.append({
                "id": f"github-pr:{slug}#{number}:{event_at}",
                "source_type": "GITHUB_PR",
                "authority": "GITHUB_HISTORY_SNAPSHOT",
                "event_at": event_at,
                "recorded_at": event_at,
                "project": spec.project,
                "projects": [spec.project],
                "title": f"PR #{number}: {row.get('title') or ''}".strip(),
                "summary": f"state={row.get('state')}",
                "github_repo": slug,
                "github_number": number,
                "github_kind": "pr",
                "state": row.get("state"),
                "url": row.get("url"),
                "head_ref": row.get("headRefName"),
                "base_ref": row.get("baseRefName"),
                "head_sha": head_sha or None,
                "refs": [f"#{number}", head_sha] if head_sha else [f"#{number}"],
                "anchors": anchors,
                "thread_id": f"pr:{anchor}",
                "thread_source": "GITHUB_OBJECT",
            })
            repo_cov["prs"]["events"] += 1

        action_rows, err = _run_json([
            "gh", "run", "list", "--repo", slug, "--created", ">=" + since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "--limit", str(limit_per_kind),
            "--json", "databaseId,workflowName,status,conclusion,createdAt,updatedAt,headSha,headBranch,event,displayTitle,url",
        ])
        if err:
            coverage["errors"].append({"repo": slug, "source": "actions", "error": err})
        for row in action_rows if isinstance(action_rows, list) else []:
            event_at = row.get("updatedAt") or row.get("createdAt")
            if not _event_time_ok(event_at, since):
                continue
            run_id = str(row.get("databaseId") or "")
            head_sha = str(row.get("headSha") or "").casefold()
            anchors = [f"action:{slug}#{run_id}"]
            if head_sha:
                anchors.append(f"gitsha:{head_sha}")
            events.append({
                "id": f"github-action:{slug}#{run_id}",
                "source_type": "GITHUB_ACTION",
                "authority": "GITHUB_ACTIONS_HISTORY",
                "event_at": event_at,
                "recorded_at": event_at,
                "project": spec.project,
                "projects": [spec.project],
                "title": f"Action {row.get('workflowName') or 'workflow'}: {row.get('displayTitle') or ''}".strip(),
                "summary": f"status={row.get('status')} conclusion={row.get('conclusion')}",
                "github_repo": slug,
                "run_id": run_id,
                "workflow": row.get("workflowName"),
                "status": row.get("status"),
                "conclusion": row.get("conclusion"),
                "head_sha": head_sha or None,
                "head_ref": row.get("headBranch"),
                "event": row.get("event"),
                "url": row.get("url"),
                "refs": [head_sha] if head_sha else [],
                "anchors": anchors,
                "thread_id": f"action:{slug}:{row.get('workflowName') or 'workflow'}",
                "thread_source": "GITHUB_ACTIONS",
            })
            repo_cov["actions"]["events"] += 1
        repo_cov["issues"]["saturated"] = isinstance(issue_rows, list) and len(issue_rows) >= limit_per_kind
        repo_cov["prs"]["saturated"] = isinstance(pr_rows, list) and len(pr_rows) >= limit_per_kind
        repo_cov["actions"]["saturated"] = isinstance(action_rows, list) and len(action_rows) >= limit_per_kind
        repo_cov["limit_per_kind"] = limit_per_kind
        repo_cov["saturated_kinds"] = [
            kind for kind in ("issues", "prs", "actions")
            if bool(repo_cov[kind].get("saturated"))
        ]
        coverage["repos"][slug] = repo_cov
    coverage["events"] = len(events)
    coverage["limit_per_kind"] = limit_per_kind
    coverage["saturated"] = any(bool(row.get("saturated_kinds")) for row in coverage["repos"].values())
    if coverage["errors"] and not events:
        coverage["available"] = False
    return events, coverage


def _read_tail(path: Path, max_bytes: int) -> bytes:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > max_bytes:
                handle.seek(size - max_bytes)
                handle.readline()
            return handle.read()
    except OSError:
        return b""


def _project_from_path(value: Any, root: Path) -> str | None:
    text = str(value or "").replace("\\", "/").casefold()
    if not text:
        return None
    if "/unreal projects/p3" in text or text.endswith("/p3"):
        return "p3"
    if "/tiny3d" in text:
        return "tiny3d"
    if "/lowvram3d" in text:
        return "lowvram"
    if str(root).replace("\\", "/").casefold() in text:
        return "vault"
    return None


def _safe_refs_from_text(text: Any) -> tuple[list[str], list[str]]:
    value = str(text or "")
    refs = sorted(set(match.group(0).casefold() for match in _SHA_RE.finditer(value)))
    numbers = sorted(set(match.group("number") for match in _ISSUE_REF_RE.finditer(value)))
    return refs, numbers


def mcp_events(
    *,
    since: datetime,
    root: Path,
    project_to_slug: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    local = Path(os.path.expandvars(r"%LOCALAPPDATA%"))
    mcp_roots = [local / "ChatGPTMcpClean", local / "ChatGPTMcpMinimal"]
    events: list[dict[str, Any]] = []
    coverage = {
        "roots": [], "request_logs": 0, "receipts": 0, "errors": [],
        "request_tail_bytes": 8 * 1024 * 1024,
        "request_tail_truncated": False,
        "receipt_limit_per_root": 2000,
        "receipt_candidates": 0,
        "receipts_saturated": False,
    }

    for mcp_root in mcp_roots:
        if not mcp_root.exists():
            continue
        coverage["roots"].append(str(mcp_root))
        request_path = mcp_root / ".state" / "front-door" / "request.jsonl"
        try:
            coverage["request_tail_truncated"] = bool(
                coverage["request_tail_truncated"] or request_path.stat().st_size > coverage["request_tail_bytes"]
            )
        except OSError:
            pass
        grouped: dict[str, dict[str, Any]] = {}
        for raw in _read_tail(request_path, coverage["request_tail_bytes"]).decode("utf-8", "replace").splitlines():
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            at = row.get("at")
            if not _event_time_ok(at, since):
                continue
            request_id = str(row.get("request_id") or "")
            if not request_id:
                continue
            item = grouped.setdefault(request_id, {"first": at, "last": at, "events": []})
            item["last"] = at
            item["events"].append(row)
        for request_id, item in grouped.items():
            rows = item["events"]
            parsed = next((row for row in rows if row.get("event") == "front_request_parsed"), {})
            finish = next((row for row in reversed(rows) if row.get("event") == "front_request_finish"), {})
            select = next((row for row in rows if row.get("event") == "front_backend_select"), {})
            tool = str(parsed.get("tool") or select.get("tool") or "request")
            process_id = parsed.get("process_id") or select.get("process_id")
            status = finish.get("status")
            anchors = [f"mcp-request:{request_id}"]
            if process_id:
                anchors.append(f"process:{process_id}")
            events.append({
                "id": f"mcp-request:{mcp_root.name}:{request_id}",
                "source_type": "MCP_EVENT",
                "authority": "LOCAL_MCP_REQUEST_LOG",
                "event_at": item["last"],
                "recorded_at": item["last"],
                "title": f"MCP {tool}: status {status if status is not None else 'unknown'}",
                "summary": "front-door request lifecycle",
                "mcp_root": str(mcp_root),
                "mcp_event": "request",
                "tool": tool,
                "process_id": process_id,
                "status": status,
                "backend_generation": select.get("backend_generation"),
                "anchors": anchors,
                "refs": [str(process_id)] if process_id else [],
                "thread_id": f"mcp-tool:{tool}",
                "thread_source": "MCP_REQUEST_LOG",
            })
            coverage["request_logs"] += 1

        receipts_root = mcp_root / ".state" / "process-receipts"
        try:
            all_receipts = sorted(receipts_root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            coverage["receipt_candidates"] += len(all_receipts)
            if len(all_receipts) > coverage["receipt_limit_per_root"]:
                coverage["receipts_saturated"] = True
            receipt_paths = all_receipts[: coverage["receipt_limit_per_root"]]
        except OSError:
            receipt_paths = []
        for path in receipt_paths:
            row = _read_json(path)
            if not row:
                continue
            event_at = row.get("finished_at") or row.get("started_at")
            if not _event_time_ok(event_at, since):
                continue
            command = str(row.get("command") or "")
            cwd = row.get("cwd")
            project = _project_from_path(cwd, root)
            sha_refs, numbers = _safe_refs_from_text(command)
            anchors = [f"process:{row.get('process_id') or path.stem}"]
            anchors.extend(f"gitsha:{sha}" for sha in sha_refs)
            slug = project_to_slug.get(project or "")
            if slug:
                anchors.extend(f"github:{slug}#{number}" for number in numbers)
            command_kind = "other"
            low = command.casefold()
            for name, marker in (
                ("git", "git "), ("github", "gh "), ("test", "pytest"), ("test", "unittest"),
                ("build", "build"), ("python", "python"), ("powershell", "powershell"),
            ):
                if marker in low:
                    command_kind = name
                    break
            events.append({
                "id": f"mcp-process:{mcp_root.name}:{row.get('process_id') or path.stem}",
                "source_type": "MCP_EVENT",
                "authority": "LOCAL_MCP_PROCESS_RECEIPT",
                "event_at": event_at,
                "recorded_at": event_at,
                "project": project,
                "projects": [project] if project else [],
                "title": f"MCP process {command_kind}: exit {row.get('exit_code')}",
                "summary": "bounded process receipt metadata; raw command intentionally not copied",
                "mcp_root": str(mcp_root),
                "mcp_event": "process_receipt",
                "process_id": row.get("process_id"),
                "caller_id": row.get("caller_id"),
                "exit_code": row.get("exit_code"),
                "signal": row.get("signal"),
                "cwd": cwd,
                "command_kind": command_kind,
                "command_fingerprint": hashlib.sha256(command.encode("utf-8", "replace")).hexdigest()[:16] if command else None,
                "refs": [*sha_refs, *[f"#{number}" for number in numbers]],
                "anchors": sorted(set(anchors)),
                "thread_id": f"mcp-process:{project or 'unknown'}",
                "thread_source": "MCP_PROCESS_RECEIPT",
            })
            coverage["receipts"] += 1
    coverage["events"] = len(events)
    return events, coverage


def _runner_diag_roots() -> list[Path]:
    roots: set[Path] = set()
    try:
        roots.update(path / "_diag" for path in Path("C:/").glob("actions-runner-*") if path.is_dir())
    except OSError:
        pass
    local = Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "GitHubActions"
    try:
        roots.update(path / "_diag" for path in local.iterdir() if path.is_dir())
    except OSError:
        pass
    return sorted(path for path in roots if path.is_dir())


def runner_log_events(*, since: datetime, limit: int = 300) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    coverage = {"roots": [], "files": 0, "events": 0, "errors": [], "limit": limit, "candidates": 0, "saturated": False}
    candidates: list[tuple[float, Path, Path]] = []
    for diag in _runner_diag_roots():
        coverage["roots"].append(str(diag))
        try:
            for path in diag.glob("*.log"):
                stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if stamp >= since.astimezone(timezone.utc):
                    candidates.append((path.stat().st_mtime, diag, path))
        except OSError as exc:
            coverage["errors"].append({"root": str(diag), "error": str(exc)[:160]})
    coverage["candidates"] = len(candidates)
    coverage["saturated"] = len(candidates) > limit
    for _, diag, path in sorted(candidates, reverse=True)[:limit]:
        text = _read_tail(path, 256 * 1024).decode("utf-8", "replace")
        errors = 0
        warnings = 0
        markers = 0
        sha_refs: set[str] = set()
        for line in text.splitlines():
            if _SECRET_LINE_RE.search(line):
                continue
            low = line.casefold()
            if " err]" in low or "[err" in low:
                errors += 1
            if " wrn]" in low or "[wrn" in low:
                warnings += 1
            if _SAFE_RUNNER_MARKER_RE.search(line):
                markers += 1
                sha_refs.update(match.group(0).casefold() for match in _SHA_RE.finditer(line))
        event_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
        runner_name = diag.parent.name
        anchors = [f"runner-log:{runner_name}:{path.name.casefold()}"]
        anchors.extend(f"gitsha:{sha}" for sha in sorted(sha_refs))
        events.append({
            "id": f"runner-log:{runner_name}:{path.name}:{int(path.stat().st_mtime)}",
            "source_type": "RUNNER_LOG",
            "authority": "LOCAL_RUNNER_DIAGNOSTIC_SUMMARY",
            "event_at": event_at,
            "recorded_at": event_at,
            "title": f"Runner diag {runner_name}: {path.name}",
            "summary": f"errors={errors} warnings={warnings} job_markers={markers}; raw log body not materialized",
            "runner": runner_name,
            "diag_path": str(path),
            "error_count": errors,
            "warning_count": warnings,
            "job_marker_count": markers,
            "refs": sorted(sha_refs),
            "anchors": anchors,
            "thread_id": f"runner:{runner_name}",
            "thread_source": "RUNNER_DIAGNOSTIC",
        })
        coverage["files"] += 1
    coverage["events"] = len(events)
    return events, coverage


def _artifact_type(rel: str) -> str:
    lower = rel.replace("\\", "/").casefold()
    suffix = Path(rel).suffix.casefold()
    if "proof" in lower:
        return "proof"
    if suffix in IMAGE_SUFFIXES or "screenshot" in lower:
        return "screenshot"
    if lower.startswith("01 reports/"):
        return "report"
    if lower.startswith("02 evidence/"):
        return "evidence_log" if suffix in {".jsonl", ".log"} or "log" in lower or "telemetry" in lower else "evidence"
    if lower.startswith("03 fixtures and experiments/"):
        return "fixture"
    if lower.startswith("04 operating contracts/"):
        return "contract"
    if lower.startswith("90 raw transcripts/"):
        return "transcript"
    return "artifact"


def local_artifact_events(root: Path, *, since: datetime, limit: int = 1000) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Observe local-only artifact files without promoting them to durable Git history."""
    tracked_raw = _git_value(root, "ls-files", "-z") or ""
    tracked = {value.replace("\\", "/").casefold() for value in tracked_raw.split("\0") if value}
    rows: list[tuple[float, Path, str]] = []
    for base_name in ARTIFACT_ROOTS:
        base = root / base_name
        if not base.is_dir():
            continue
        try:
            iterator = base.rglob("*")
            for path in iterator:
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if rel.casefold() in tracked:
                    continue
                stamp = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
                if stamp < since.astimezone(stamp.tzinfo):
                    continue
                rows.append((path.stat().st_mtime, path, rel))
        except OSError:
            continue
    events: list[dict[str, Any]] = []
    for mtime, path, rel in sorted(rows, reverse=True)[:limit]:
        event_at = datetime.fromtimestamp(mtime).astimezone().isoformat()
        incident_ids = sorted({match.group(0).casefold() for match in _INCIDENT_RE.finditer(rel)})
        anchors = [f"local-artifact:{rel.casefold()}"]
        anchors.extend(f"incident:{incident}" for incident in incident_ids)
        events.append({
            "id": f"local-artifact:{rel.casefold()}:{int(mtime)}",
            "source_type": "LOCAL_ARTIFACT",
            "authority": "LOCAL_WIP_ARTIFACT_OBSERVATION",
            "event_at": event_at,
            "recorded_at": event_at,
            "project": "regression-research",
            "projects": ["regression-research"],
            "title": f"{_artifact_type(rel)}: {path.name}",
            "summary": "local-only artifact observed; not Git-tracked durable history",
            "artifact_type": _artifact_type(rel),
            "path": rel,
            "refs": [rel],
            "anchors": anchors,
            "thread_id": f"local-artifact:{rel.casefold()}",
            "thread_source": "LOCAL_ARTIFACT_PATH",
        })
    return events, {"events": len(events), "candidates": len(rows), "limit": limit, "saturated": len(rows) > limit}


def _subject_key(title: Any) -> str | None:
    text = str(title or "").strip()
    if not text or text.casefold().startswith("merge pull request"):
        return None
    text = _SUBJECT_PR_SUFFIX_RE.sub("", text)
    text = _SUBJECT_ISSUE_PREFIX_RE.sub("", text)
    text = _SUBJECT_KIND_PREFIX_RE.sub("", text)
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    if len(tokens) < 3:
        return None
    return " ".join(tokens)


def _event_sha_refs(event: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for key in ("sha", "head_sha", "short_sha"):
        value = str(event.get(key) or "").strip().casefold()
        if 7 <= len(value) <= 40 and re.fullmatch(r"[0-9a-f]+", value):
            refs.add(value)
    for anchor in event.get("anchors", []) or []:
        low = str(anchor).casefold()
        if low.startswith("gitsha:"):
            refs.add(low.split(":", 1)[1])
    for raw in event.get("refs", []) or []:
        refs.update(match.group(0).casefold() for match in _SHA_RE.finditer(str(raw)))
    for key in ("scope", "mutation", "validation", "findings", "summary"):
        refs.update(match.group(0).casefold() for match in _SHA_RE.finditer(str(event.get(key) or "")))
    return refs


def _event_github_anchors(event: dict[str, Any]) -> set[str]:
    anchors: set[str] = set()
    for anchor in event.get("anchors", []) or []:
        low = str(anchor).casefold()
        if low.startswith("github:"):
            anchors.add(low)
        elif low.startswith(("pr:github:", "issue:github:")):
            anchors.add(low.split(":", 1)[1])
    return anchors


def _event_branch_refs(event: dict[str, Any]) -> list[str]:
    values = event.get("branch_refs")
    if isinstance(values, list):
        return sorted({str(value) for value in values if str(value).strip()})
    return _branch_refs(event.get("decorations"))


def build_work_graph(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Build a work-equivalence graph without conflating it with incident identity."""
    all_events = [dict(event) for event in events]
    commits = [event for event in all_events if event.get("source_type") == "GIT_COMMIT" and event.get("sha")]
    parent = list(range(len(commits)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    patch_owner: dict[tuple[str, str], int] = {}
    subject_owner: dict[tuple[str, str], int] = {}
    for index, event in enumerate(commits):
        project = str(event.get("project") or "")
        patch_id = str(event.get("patch_id") or "")
        if patch_id:
            key = (project, patch_id)
            if key in patch_owner:
                union(index, patch_owner[key])
            else:
                patch_owner[key] = index
        subject = _subject_key(event.get("title"))
        if subject:
            key = (project, subject)
            prior = subject_owner.get(key)
            if prior is not None:
                # Exact normalized titles are fallback evidence, not identity by themselves.
                # Join only when a GitHub work anchor is shared, or when the same descriptive
                # title appears in nearby branch/main activity. Stable patch-id remains primary.
                prior_event = commits[prior]
                shared = _event_github_anchors(event) & _event_github_anchors(prior_event)
                current_at = _dt(event.get("event_at"))
                prior_at = _dt(prior_event.get("event_at"))
                nearby = bool(
                    current_at and prior_at
                    and abs((current_at - prior_at).total_seconds()) <= 48 * 3600
                    and (_event_branch_refs(event) or _event_branch_refs(prior_event))
                )
                if shared or (len(subject.split()) >= 4 and nearby):
                    union(index, prior)
            else:
                subject_owner[key] = index

    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, event in enumerate(commits):
        groups[find(index)].append(event)

    commit_to_group: dict[str, str] = {}
    pr_to_groups: dict[str, set[str]] = defaultdict(set)
    group_rows: dict[str, dict[str, Any]] = {}
    for members in groups.values():
        members.sort(key=lambda event: (_dt(event.get("event_at")) or datetime.min.replace(tzinfo=timezone.utc), str(event.get("sha"))))
        patch_ids = sorted({str(event.get("patch_id")) for event in members if event.get("patch_id")})
        title = str(members[-1].get("title") or "")
        subject = _subject_key(title) or title.casefold()
        project = str(members[-1].get("project") or "")
        if patch_ids:
            group_id = f"patch:{project}:{patch_ids[0]}"
        elif len(members) > 1:
            digest = hashlib.sha1(f"{project}\0{subject}".encode("utf-8", "replace")).hexdigest()[:16]
            group_id = f"subject:{project}:{digest}"
        else:
            group_id = f"commit:{project}:{str(members[0].get('sha') or '').casefold()}"
        github_anchors = sorted({anchor for event in members for anchor in _event_github_anchors(event)})
        branch_sets = [_event_branch_refs(event) for event in members]
        branches = sorted({ref for refs in branch_sets for ref in refs})
        cross_branch = bool(
            len(members) > 1
            and (len(branches) > 1 or (any(branch_sets) and any(not refs for refs in branch_sets)))
        )
        commit_rows = []
        for event in members:
            sha = str(event.get("sha") or "").casefold()
            commit_to_group[sha] = group_id
            for anchor in _event_github_anchors(event):
                pr_to_groups[anchor].add(group_id)
            commit_rows.append({
                "sha": sha,
                "short_sha": sha[:10],
                "at": event.get("event_at"),
                "title": event.get("title"),
                "branch_refs": _event_branch_refs(event),
                "patch_id": event.get("patch_id"),
            })
        group_rows[group_id] = {
            "work_id": group_id,
            "project": project,
            "title": title,
            "subject_key": subject,
            "commit_count": len(members),
            "equivalent_commit_count": len(members),
            "branch_refs": branches,
            "cross_branch": cross_branch,
            "github_anchors": github_anchors,
            "commits": commit_rows,
            "attached_event_ids": [],
            "source_counts": {},
            "evidence_forms": [],
            "workers": [],
            "efficiency": {},
        }

    def groups_for_sha(ref: str) -> set[str]:
        low = ref.casefold()
        out: set[str] = set()
        for sha, group_id in commit_to_group.items():
            if sha.startswith(low) or low.startswith(sha):
                out.add(group_id)
        return out

    # GitHub object type map prevents umbrella issues from acting like PR identity.
    github_kind: dict[str, str] = {}
    for event in all_events:
        kind = str(event.get("github_kind") or "")
        raw_anchors = [str(anchor).casefold() for anchor in event.get("anchors", []) or []]
        for anchor in _event_github_anchors(event):
            inferred = kind
            if not inferred and f"pr:{anchor}" in raw_anchors:
                inferred = "pr"
            elif not inferred and f"issue:{anchor}" in raw_anchors:
                inferred = "issue"
            if inferred:
                github_kind[anchor] = inferred

    attachments_by_event: dict[str, set[str]] = defaultdict(set)
    for event in all_events:
        if event.get("source_type") == "GIT_COMMIT":
            continue
        matched: set[str] = set()
        for sha_ref in _event_sha_refs(event):
            matched.update(groups_for_sha(sha_ref))
        for anchor in _event_github_anchors(event):
            if github_kind.get(anchor) == "pr":
                matched.update(pr_to_groups.get(anchor, set()))
        event_id = str(event.get("id") or "")
        if event_id and matched:
            attachments_by_event[event_id].update(matched)

    events_by_id = {str(event.get("id") or ""): event for event in all_events}
    for event_id, matched in attachments_by_event.items():
        event = events_by_id[event_id]
        share = max(1, len(matched))
        for group_id in matched:
            row = group_rows[group_id]
            row["attached_event_ids"].append(event_id)
            source = str(event.get("source_type") or "UNKNOWN")
            counts = Counter(row["source_counts"])
            counts[source] += 1
            row["source_counts"] = dict(sorted(counts.items()))
            forms = set(row["evidence_forms"])
            form = {
                "VAULT_MEMORY": "memory",
                "WORKER_REPORT": "worker_report",
                "GITHUB_PR": "pull_request",
                "GITHUB_ISSUE": "issue",
                "GITHUB_ACTION": "action_run",
                "MCP_EVENT": "mcp_event",
                "RUNNER_LOG": "runner_log",
                "TRACKED_ARTIFACT": str(event.get("artifact_type") or "artifact"),
                "LOCAL_ARTIFACT": str(event.get("artifact_type") or "artifact"),
            }.get(source, "observation")
            forms.add(form)
            row["evidence_forms"] = sorted(forms)
            if source == "WORKER_REPORT":
                duration = event.get("duration_minutes")
                utilization = event.get("target_utilization_pct")
                row["workers"].append({
                    "event_id": event_id,
                    "worker": event.get("worker") or event.get("display_label"),
                    "duration_minutes": duration,
                    "allocated_duration_minutes": round(float(duration) / share, 3) if isinstance(duration, (int, float)) else None,
                    "target_utilization_pct": utilization,
                    "outcome": event.get("outcome"),
                })

    # Derive efficiency and CI summaries after attachments are complete.
    for row in group_rows.values():
        workers = row["workers"]
        durations = [float(item["duration_minutes"]) for item in workers if isinstance(item.get("duration_minutes"), (int, float))]
        allocated = [float(item["allocated_duration_minutes"]) for item in workers if isinstance(item.get("allocated_duration_minutes"), (int, float))]
        utilization = [float(item["target_utilization_pct"]) for item in workers if isinstance(item.get("target_utilization_pct"), (int, float))]
        action_events = [
            events_by_id[event_id] for event_id in row["attached_event_ids"]
            if events_by_id.get(event_id, {}).get("source_type") == "GITHUB_ACTION"
        ]
        conclusions = Counter(str(event.get("conclusion") or event.get("status") or "unknown").casefold() for event in action_events)
        row["efficiency"] = {
            "worker_runs": len(workers),
            "worker_duration_minutes": round(sum(durations), 2) if durations else 0.0,
            "allocated_worker_minutes": round(sum(allocated), 2) if allocated else 0.0,
            "average_worker_utilization_pct": round(sum(utilization) / len(utilization), 1) if utilization else None,
            "action_runs": len(action_events),
            "action_conclusions": dict(sorted(conclusions.items())),
        }
        row["attached_event_ids"] = sorted(set(row["attached_event_ids"]))
        row["latest_at"] = max(
            [str(commit.get("at") or "") for commit in row["commits"]]
            + [str(events_by_id[event_id].get("event_at") or "") for event_id in row["attached_event_ids"] if event_id in events_by_id]
        )

    workstreams: dict[str, dict[str, Any]] = {}
    for event in all_events:
        for anchor in _event_github_anchors(event):
            item = workstreams.setdefault(anchor, {
                "anchor": anchor,
                "kind": github_kind.get(anchor, "unknown"),
                "projects": set(),
                "event_ids": set(),
                "work_ids": set(),
                "latest_at": None,
            })
            project = str(event.get("project") or "")
            if project:
                item["projects"].add(project)
            event_id = str(event.get("id") or "")
            if event_id:
                item["event_ids"].add(event_id)
                item["work_ids"].update(attachments_by_event.get(event_id, set()))
            stamp = str(event.get("event_at") or "")
            if not item["latest_at"] or stamp > item["latest_at"]:
                item["latest_at"] = stamp

    workstream_rows = [
        {
            "anchor": anchor,
            "kind": item["kind"],
            "projects": sorted(item["projects"]),
            "event_count": len(item["event_ids"]),
            "work_ids": sorted(item["work_ids"]),
            "latest_at": item["latest_at"],
        }
        for anchor, item in workstreams.items()
    ]
    workstream_rows.sort(key=lambda item: (item.get("latest_at") or "", item["anchor"]), reverse=True)

    group_list = list(group_rows.values())
    group_list.sort(key=lambda item: (item.get("latest_at") or "", item["work_id"]), reverse=True)
    similar = [
        {
            "work_id": row["work_id"],
            "project": row["project"],
            "title": row["title"],
            "commit_count": row["commit_count"],
            "branch_refs": row["branch_refs"],
            "cross_branch": row.get("cross_branch", False),
            "workers": len(row["workers"]),
            "efficiency": row["efficiency"],
        }
        for row in group_list
        if row["commit_count"] > 1
    ]
    return {
        "schema": "vault.timeline.work-graph.v1",
        "contract": "work equivalence is separate from incident identity; exact patch ids and conservative normalized commit subjects group commits, while worker/memory/proof/CI/MCP observations attach by explicit SHA or PR evidence without merging umbrella issues",
        "commit_groups": group_list,
        "similar_commit_groups": similar,
        "workstreams": workstream_rows,
        "summary": {
            "commit_groups": len(group_list),
            "equivalent_commit_groups": len(similar),
            "cross_branch_groups": sum(1 for row in similar if row.get("cross_branch")),
            "attached_observations": len(attachments_by_event),
            "workstreams": len(workstream_rows),
        },
    }


def _coverage_counts(events: Iterable[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(event.get("source_type") or "UNKNOWN") for event in events).items()))


def _acquire_lock(path: Path) -> int | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - path.stat().st_mtime
            if age > LOCK_STALE_MINUTES * 60:
                path.unlink(missing_ok=True)
                return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            pass
        return None


def _materialized_source_since(
    previous: dict[str, Any] | None,
    source: str,
    *,
    horizon_since: datetime,
    overlap_minutes: int = DEFAULT_OVERLAP_MINUTES,
) -> datetime:
    if not previous:
        return horizon_since
    watermarks = previous.get("source_watermarks") if isinstance(previous.get("source_watermarks"), dict) else {}
    raw = watermarks.get(source) or previous.get("generated_at")
    stamp = _dt(raw)
    if stamp is None:
        return horizon_since
    candidate = stamp - timedelta(minutes=max(0, int(overlap_minutes)))
    return max(horizon_since.astimezone(candidate.tzinfo), candidate)


def _event_within_horizon(event: dict[str, Any], since: datetime) -> bool:
    stamp = _dt(event.get("event_at"))
    return bool(stamp and stamp >= since.astimezone(stamp.tzinfo))


def _merge_materialized_events(
    previous_events: Iterable[dict[str, Any]],
    delta_events: Iterable[dict[str, Any]],
    *,
    since: datetime,
) -> list[dict[str, Any]]:
    """Merge immutable/revisable source observations by stable event id and prune the horizon."""
    by_id: dict[str, dict[str, Any]] = {}
    for raw in [*previous_events, *delta_events]:
        if not isinstance(raw, dict) or not _event_within_horizon(raw, since):
            continue
        event_id = str(raw.get("id") or "").strip()
        if not event_id:
            continue
        by_id[event_id] = dict(raw)
    events = list(by_id.values())
    events.sort(
        key=lambda event: (
            _dt(event.get("event_at")) or datetime.min.replace(tzinfo=timezone.utc),
            str(event.get("id") or ""),
        ),
        reverse=True,
    )
    return events


def _coverage_saturated(source: str, coverage: dict[str, Any]) -> bool:
    if source == "repos":
        return any(bool(row.get("saturated")) for row in coverage.values() if isinstance(row, dict))
    if source == "artifacts":
        return bool(coverage.get("saturated"))
    if source == "local_artifacts":
        return bool(coverage.get("saturated"))
    if source == "github":
        return bool(coverage.get("saturated")) or bool(coverage.get("errors"))
    if source == "mcp":
        return bool(coverage.get("receipts_saturated")) or bool(coverage.get("errors"))
    if source == "runner_logs":
        return bool(coverage.get("saturated")) or bool(coverage.get("errors"))
    return False


def materialize(
    *,
    root: Path = ROOT,
    state_root: Path | None = None,
    now: datetime | None = None,
    days: int = DEFAULT_DAYS,
    repo_events_per_repo: int = DEFAULT_REPO_EVENTS,
    artifact_events_limit: int = DEFAULT_ARTIFACT_EVENTS,
    max_events: int = DEFAULT_MAX_EVENTS,
    include_github: bool = True,
    rebuild: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    now = now or datetime.now().astimezone()
    horizon_since = now - timedelta(days=max(1, int(days)))
    state_root = state_root or (root / ".state" / "timeline")
    store_path = state_root / STORE_PATH.name
    bootstrap_path = state_root / BOOTSTRAP_PATH.name
    status_path = state_root / STATUS_PATH.name
    lock_path = state_root / LOCK_PATH.name

    lock_fd = _acquire_lock(lock_path)
    if lock_fd is None:
        return {"ok": False, "status": "ALREADY_RUNNING", "path": str(lock_path)}
    try:
        os.write(lock_fd, f"{os.getpid()}\n".encode("ascii"))
        previous = None if rebuild else _read_json(store_path)
        previous_timeline = previous.get("timeline") if isinstance(previous, dict) and isinstance(previous.get("timeline"), dict) else None
        incremental = bool(previous_timeline and isinstance(previous_timeline.get("events"), list))
        refresh_mode = "INCREMENTAL" if incremental else "BACKFILL"
        previous_events = [
            dict(event) for event in (previous_timeline.get("events", []) if previous_timeline else [])
            if isinstance(event, dict) and event.get("source_type") != "VAULT_MEMORY"
        ]

        source_names = ("repos", "workers", "artifacts", "local_artifacts", "github", "mcp", "runner_logs")
        source_since = {
            name: _materialized_source_since(previous, name, horizon_since=horizon_since)
            if incremental else horizon_since
            for name in source_names
        }

        specs = discover_repo_specs(vault_root=root)
        project_to_slug, _ = _repo_maps(specs)
        entries = load_bank(root / "memory" / "memory-bank.jsonl")

        repo_limit = min(repo_events_per_repo, DEFAULT_DELTA_REPO_EVENTS_PER_REPO) if incremental else repo_events_per_repo
        repo_report = collect_repo_history(specs, limit_per_repo=repo_limit, since=source_since["repos"])
        repo_delta = list(repo_report.get("events") or [])
        enrich_repo_events(repo_delta, specs, since=source_since["repos"])

        worker_delta: list[dict[str, Any]] = []
        worker_roots = [root / "worker-reports" / "history", root / "worker-reports" / "manual" / "history"]
        for history_root in worker_roots:
            worker_delta.extend(worker_history_events(history_root, since=source_since["workers"]))

        artifact_limit = min(artifact_events_limit, DEFAULT_DELTA_ARTIFACT_EVENTS) if incremental else artifact_events_limit
        artifact_delta = tracked_artifact_events(root, limit=artifact_limit, since=source_since["artifacts"])
        local_delta, local_coverage = local_artifact_events(root, since=source_since["local_artifacts"])

        github_delta: list[dict[str, Any]] = []
        github_coverage: dict[str, Any] = {"available": False, "skipped": True}
        if include_github:
            github_limit = DEFAULT_DELTA_GITHUB_EVENTS_PER_KIND if incremental else DEFAULT_GITHUB_EVENTS_PER_KIND
            github_delta, github_coverage = github_events(
                specs, since=source_since["github"], limit_per_kind=github_limit
            )

        mcp_delta, mcp_coverage = mcp_events(
            since=source_since["mcp"], root=root, project_to_slug=project_to_slug
        )
        runner_delta, runner_coverage = runner_log_events(since=source_since["runner_logs"])
        supplemental_delta = [*github_delta, *mcp_delta, *runner_delta, *local_delta]
        all_delta = [*repo_delta, *worker_delta, *artifact_delta, *supplemental_delta]

        merged_external = _merge_materialized_events(
            previous_events, all_delta, since=horizon_since
        )
        repo_events = [event for event in merged_external if event.get("source_type") == "GIT_COMMIT"]
        worker_events = [event for event in merged_external if event.get("source_type") == "WORKER_REPORT"]
        artifact_events = [event for event in merged_external if event.get("source_type") == "TRACKED_ARTIFACT"]
        supplemental = [
            event for event in merged_external
            if event.get("source_type") not in {"GIT_COMMIT", "WORKER_REPORT", "TRACKED_ARTIFACT"}
        ]

        delta_coverage = {
            "repos": repo_report.get("coverage", {}),
            "workers": {"bounded": False, "included": True, "events": len(worker_delta)},
            "artifacts": {
                "events": len(artifact_delta),
                "limit": artifact_limit,
                "saturated": len(artifact_delta) >= artifact_limit,
            },
            "local_artifacts": local_coverage,
            "github": github_coverage,
            "mcp": mcp_coverage,
            "runner_logs": runner_coverage,
        }
        saturated_sources = [
            name for name in source_names
            if _coverage_saturated(name, delta_coverage.get(name, {}))
        ]

        previous_watermarks = previous.get("source_watermarks") if isinstance(previous, dict) and isinstance(previous.get("source_watermarks"), dict) else {}
        source_watermarks: dict[str, str] = {}
        for name in source_names:
            if refresh_mode == "INCREMENTAL" and name in saturated_sources:
                source_watermarks[name] = str(previous_watermarks.get(name) or previous.get("generated_at") or source_since[name].isoformat())
            else:
                source_watermarks[name] = now.isoformat()

        previous_ingestion = previous.get("ingestion") if isinstance(previous, dict) and isinstance(previous.get("ingestion"), dict) else {}
        previous_backfill_incomplete = set(str(value) for value in previous_ingestion.get("backfill_incomplete_sources", []) if str(value).strip())
        backfill_incomplete_sources = (
            sorted(set(saturated_sources))
            if refresh_mode == "BACKFILL"
            else sorted(previous_backfill_incomplete)
        )
        retry_sources = sorted(set(saturated_sources)) if refresh_mode == "INCREMENTAL" else []
        source_coverage = {
            **delta_coverage,
            "materializer": {
                "mode": refresh_mode,
                "horizon_days": days,
                "overlap_minutes": DEFAULT_OVERLAP_MINUTES,
                "source_since": {name: value.isoformat() for name, value in source_since.items()},
                "delta_events": len(all_delta),
                "retained_previous_external_events": len(previous_events),
                "merged_external_events": len(merged_external),
                "saturated_sources": saturated_sources,
                "backfill_incomplete_sources": backfill_incomplete_sources,
                "retry_sources": retry_sources,
            },
        }
        timeline = build_timeline(
            entries,
            limit=max_events,
            max_limit=max_events,
            since=horizon_since,
            repo_events=repo_events,
            worker_events=worker_events,
            artifact_events=artifact_events,
            supplemental_events=supplemental,
            snapshot_now=now,
            source_coverage=source_coverage,
        )
        graph = build_work_graph(timeline["events"])
        timeline["work_graph"] = graph
        timeline["materialized"] = {
            "schema": SCHEMA,
            "generated_at": now.isoformat(),
            "horizon_days": days,
            "refresh_minutes": DEFAULT_REFRESH_MINUTES,
            "refresh_mode": refresh_mode,
            "overlap_minutes": DEFAULT_OVERLAP_MINUTES,
            "delta_events": len(all_delta),
            "source_counts": _coverage_counts(timeline["events"]),
            "source_watermarks": source_watermarks,
            "saturated_sources": saturated_sources,
            "backfill_incomplete_sources": backfill_incomplete_sources,
            "retry_sources": retry_sources,
        }

        store_payload = {
            "schema": SCHEMA,
            "generated_at": now.isoformat(),
            "horizon_days": days,
            "source_watermarks": source_watermarks,
            "ingestion": {
                "mode": refresh_mode,
                "overlap_minutes": DEFAULT_OVERLAP_MINUTES,
                "delta_events": len(all_delta),
                "source_since": {name: value.isoformat() for name, value in source_since.items()},
                "saturated_sources": saturated_sources,
                "backfill_incomplete_sources": backfill_incomplete_sources,
                "retry_sources": retry_sources,
            },
            "timeline": timeline,
        }
        _atomic_json(store_path, store_payload)

        overview = build_overview(entries, limit=20, include_timeline_snapshots=False, now=now)
        overview["timeline_snapshots"] = timeline["snapshots"]
        overview["timeline_source_health"] = {
            key: timeline.get(key)
            for key in (
                "matching_events", "memory_events", "repo_events", "worker_events",
                "artifact_events", "supplemental_events", "invalid_source_events",
            )
        }
        try:
            from tools.stack_atlas import _compact_memory_overview, _fit_memory_overview_budget
        except ImportError:
            from stack_atlas import _compact_memory_overview, _fit_memory_overview_budget
        compact = _compact_memory_overview(overview, 3)
        compact["timeline_materialized"] = {
            "status": "FRESH",
            "as_of": now.isoformat(),
            "horizon_days": days,
            "refresh_minutes": DEFAULT_REFRESH_MINUTES,
            "refresh_mode": refresh_mode,
            "delta_events": len(all_delta),
            "saturated_sources": saturated_sources,
            "backfill_incomplete_sources": backfill_incomplete_sources,
            "retry_sources": retry_sources,
            "coverage_status": "HISTORICAL_INCOMPLETE" if backfill_incomplete_sources else "COMPLETE_WITHIN_MATERIALIZED_HORIZON",
            "absence_semantics": "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE" if backfill_incomplete_sources else "NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HORIZON_AND_ENABLED_SOURCES_ONLY",
            "live_truth_required": True,
            "work_graph": graph["summary"],
        }
        compact = _fit_memory_overview_budget(compact)
        _atomic_json(bootstrap_path, {
            "schema": BOOTSTRAP_SCHEMA,
            "generated_at": now.isoformat(),
            "overview": compact,
        })

        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        status = {
            "ok": True,
            "status": "REFRESHED",
            "refresh_mode": refresh_mode,
            "generated_at": now.isoformat(),
            "elapsed_ms": elapsed_ms,
            "delta_events": len(all_delta),
            "events": timeline["matching_events"],
            "stored_events": len(timeline["events"]),
            "truncated": bool(timeline.get("truncated")),
            "saturated_sources": saturated_sources,
            "backfill_incomplete_sources": backfill_incomplete_sources,
            "retry_sources": retry_sources,
            "source_counts": _coverage_counts(timeline["events"]),
            "work_graph": graph["summary"],
            "store_path": str(store_path),
            "bootstrap_path": str(bootstrap_path),
            "store_bytes": store_path.stat().st_size,
            "bootstrap_bytes": bootstrap_path.stat().st_size,
        }
        _atomic_json(status_path, status)
        return status
    finally:
        try:
            os.close(lock_fd)
        except OSError:
            pass
        lock_path.unlink(missing_ok=True)


def load_materialized(*, root: Path = ROOT) -> dict[str, Any] | None:
    return _read_json(root / ".state" / "timeline" / STORE_PATH.name)


def load_bootstrap_projection(*, root: Path = ROOT) -> dict[str, Any] | None:
    return _read_json(root / ".state" / "timeline" / BOOTSTRAP_PATH.name)


def materialized_health(payload: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Describe freshness and evidence-completeness semantics for a materialized payload."""
    now = now or datetime.now().astimezone()
    timeline = payload.get("timeline") if isinstance(payload.get("timeline"), dict) else {}
    overview = payload.get("overview") if isinstance(payload.get("overview"), dict) else {}
    timeline_meta = timeline.get("materialized") if isinstance(timeline.get("materialized"), dict) else {}
    overview_meta = overview.get("timeline_materialized") if isinstance(overview.get("timeline_materialized"), dict) else {}
    meta = dict(timeline_meta or overview_meta)
    ingestion = payload.get("ingestion") if isinstance(payload.get("ingestion"), dict) else {}

    generated_at = str(payload.get("generated_at") or meta.get("as_of") or meta.get("generated_at") or "").strip()
    generated = _dt(generated_at)
    age_seconds = max(0.0, (now - generated.astimezone(now.tzinfo)).total_seconds()) if generated else None
    try:
        refresh_minutes = max(1.0, float(meta.get("refresh_minutes") or DEFAULT_REFRESH_MINUTES))
    except (TypeError, ValueError):
        refresh_minutes = float(DEFAULT_REFRESH_MINUTES)
    stale_after_seconds = max(15.0 * 60.0, refresh_minutes * 60.0 * 3.0)
    status = "FRESH" if age_seconds is not None and age_seconds <= stale_after_seconds else "STALE"

    incomplete = sorted(set(str(value) for value in (
        ingestion.get("backfill_incomplete_sources")
        or meta.get("backfill_incomplete_sources")
        or []
    ) if str(value).strip()))
    saturated = sorted(set(str(value) for value in (
        ingestion.get("saturated_sources")
        or meta.get("saturated_sources")
        or []
    ) if str(value).strip()))
    retry = sorted(set(str(value) for value in (
        ingestion.get("retry_sources")
        or meta.get("retry_sources")
        or []
    ) if str(value).strip()))
    coverage_status = "HISTORICAL_INCOMPLETE" if incomplete else "COMPLETE_WITHIN_MATERIALIZED_HORIZON"
    absence_unsafe_reasons: list[str] = []
    if status != "FRESH":
        absence_unsafe_reasons.append("MATERIALIZATION_STALE")
    if incomplete:
        absence_unsafe_reasons.append("HISTORICAL_BACKFILL_INCOMPLETE")
    if retry:
        absence_unsafe_reasons.append("DELTA_RETRY_PENDING")
    absence_semantics = (
        "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE"
        if absence_unsafe_reasons
        else "NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HORIZON_AND_ENABLED_SOURCES_ONLY"
    )
    return {
        "status": status,
        "as_of": generated_at or None,
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "stale_after_seconds": round(stale_after_seconds, 1),
        "refresh_minutes": refresh_minutes,
        "refresh_mode": meta.get("refresh_mode") or ingestion.get("mode"),
        "horizon_days": payload.get("horizon_days") or meta.get("horizon_days"),
        "read_mode": "MATERIALIZED_ONLY",
        "coverage_status": coverage_status,
        "backfill_incomplete_sources": incomplete,
        "saturated_sources": saturated,
        "retry_sources": retry,
        "absence_semantics": absence_semantics,
        "absence_unsafe_reasons": absence_unsafe_reasons,
        "live_truth_required": True,
    }


def _event_matches_query(event: dict[str, Any], query: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", query.casefold()))
    if not tokens:
        return True
    hay = " ".join([
        str(event.get("title") or ""),
        str(event.get("summary") or ""),
        str(event.get("project") or ""),
        str(event.get("worker") or ""),
        " ".join(str(value) for value in event.get("refs", []) or []),
        " ".join(str(value) for value in event.get("anchors", []) or []),
    ]).casefold()
    return tokens <= set(re.findall(r"[a-z0-9]+", hay))


def _clip_query_value(value: Any, limit: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: max(0, limit - 3)].rstrip() + "..."


def _compact_query_event(event: dict[str, Any]) -> dict[str, Any]:
    """Bound query output while preserving navigation, semantics, and source-specific proof fields."""
    result: dict[str, Any] = {}
    passthrough = (
        "id", "source_type", "authority", "event_at", "recorded_at", "project", "projects",
        "state", "kind", "scope", "worker", "display_label", "population", "automation_id", "run_id",
        "duration_minutes", "target_run_minutes", "target_utilization_pct", "finding_tags",
        "sha", "short_sha", "patch_id", "branch_refs", "decorations", "repo_path", "repo_state",
        "artifact_type", "path", "report_path", "evidence_type", "incident_id", "change",
        "github_kind", "github_number", "github_repo", "url", "head_ref", "base_ref", "head_sha",
        "workflow", "status", "conclusion", "event", "tool", "process_id", "backend_generation",
        "mcp_event", "mcp_root", "runner", "diag_path", "error_count", "warning_count", "job_marker_count",
        "thread_id", "thread_source", "continuity", "case_anchors", "evidence_form",
        "disposition", "durability", "semantic_category", "primary_domain", "tags", "superseded_by", "supersedes",
        "proof_artifact", "proof_artifact_sha256", "visual_proof_run", "visual_proof_review",
    )
    for key in passthrough:
        value = event.get(key)
        if value not in (None, "", [], {}):
            result[key] = value
    for key, limit in (("title", 260), ("summary", 480), ("outcome", 240), ("remaining_gate", 240), ("findings", 300), ("stop_reason", 200)):
        clipped = _clip_query_value(event.get(key), limit)
        if clipped:
            result[key] = clipped
    for key in ("refs", "anchors", "evidence"):
        values = event.get(key)
        if not isinstance(values, list):
            continue
        clipped_values = []
        for value in values[:4]:
            clipped = _clip_query_value(value, 240)
            if clipped:
                clipped_values.append(clipped)
        if clipped_values:
            result[key] = clipped_values
    return result


def query_materialized(
    *,
    root: Path = ROOT,
    query: str = "",
    view: str = "general",
    project: str | None = None,
    thread: str | None = None,
    days: int | None = None,
    limit: int = 20,
    include_workers: bool = True,
) -> dict[str, Any] | None:
    payload = load_materialized(root=root)
    if not payload:
        return None
    timeline = payload.get("timeline")
    if not isinstance(timeline, dict):
        return None
    events = [dict(event) for event in timeline.get("events", []) if isinstance(event, dict)]
    now = datetime.now().astimezone()
    since = now - timedelta(days=days) if days is not None else None
    selected: list[dict[str, Any]] = []
    for event in events:
        if not include_workers and event.get("source_type") == "WORKER_REPORT":
            continue
        if project and str(event.get("project") or "").casefold() != project.casefold():
            continue
        if thread and str(event.get("thread_id") or "") != thread:
            continue
        stamp = _dt(event.get("event_at"))
        if since is not None and (stamp is None or stamp < since.astimezone(stamp.tzinfo)):
            continue
        if view == "errors":
            semantics = event.get("continuity") if isinstance(event.get("continuity"), dict) else {}
            if semantics.get("severity") != "RED" and not set(semantics.get("traits") or []) & {"incident", "regression", "slopwall", "security_incident"}:
                continue
        if not _event_matches_query(event, query):
            continue
        selected.append(event)
    selected.sort(key=lambda event: (str(event.get("event_at") or ""), str(event.get("id") or "")), reverse=True)
    effective_limit = min(500, max(1, int(limit)))
    graph_limit = min(6, effective_limit)
    selected_ids = {str(event.get("id") or "") for event in selected}
    graph = timeline.get("work_graph") if isinstance(timeline.get("work_graph"), dict) else {}
    all_graph_groups = graph.get("commit_groups", []) if isinstance(graph.get("commit_groups"), list) else []
    attachment_counts: Counter[str] = Counter()
    for row in all_graph_groups:
        for event_id in row.get("attached_event_ids", []) or []:
            attachment_counts[str(event_id)] += 1

    selected_attachment_ids: set[str] = set()
    for event in selected:
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        if attachment_counts.get(event_id, 0) <= 1:
            selected_attachment_ids.add(event_id)
            continue
        # Shared worker reports can legitimately span many work nodes. Expand through
        # them only when the query targets the worker/run identity itself, not merely
        # because a broad report summary happened to mention the topical query.
        if event.get("source_type") == "WORKER_REPORT" and query:
            identity_probe = {
                "title": event.get("display_label") or event.get("worker") or "",
                "worker": event.get("worker") or "",
                "refs": [event.get("automation_id") or "", event.get("run_id") or ""],
                "anchors": [],
            }
            if _event_matches_query(identity_probe, query):
                selected_attachment_ids.add(event_id)

    def compact_group(row: dict[str, Any]) -> dict[str, Any]:
        workers = []
        for worker in row.get("workers", []) or []:
            if not isinstance(worker, dict):
                continue
            item = {key: worker.get(key) for key in (
                "worker", "duration_minutes", "allocated_duration_minutes",
                "target_utilization_pct", "outcome",
            ) if worker.get(key) is not None}
            outcome = str(item.get("outcome") or "")
            if len(outcome) > 240:
                item["outcome"] = outcome[:237].rstrip() + "..."
            workers.append(item)
        return {
            key: row.get(key) for key in (
                "work_id", "project", "title", "subject_key", "commit_count",
                "equivalent_commit_count", "branch_refs", "cross_branch",
                "github_anchors", "commits", "source_counts", "evidence_forms",
                "efficiency", "latest_at",
            ) if row.get(key) not in (None, [], {})
        } | ({"workers": workers} if workers else {})

    matched_groups: list[dict[str, Any]] = []
    for row in all_graph_groups:
        if project and str(row.get("project") or "").casefold() != project.casefold():
            continue
        attached = set(str(value) for value in row.get("attached_event_ids", []) or [])
        if query and not _event_matches_query({"title": row.get("title"), "refs": row.get("github_anchors", [])}, query) and not (attached & selected_attachment_ids):
            continue
        matched_groups.append(row)

    matched_similar: list[dict[str, Any]] = []
    for row in graph.get("similar_commit_groups", []) if isinstance(graph.get("similar_commit_groups"), list) else []:
        if project and str(row.get("project") or "").casefold() != project.casefold():
            continue
        if query and not _event_matches_query({"title": row.get("title"), "refs": row.get("branch_refs", [])}, query):
            continue
        matched_similar.append(row)

    materialized = materialized_health(payload, now=now)
    materialized["schema"] = payload.get("schema")
    result = {
        "schema_version": timeline.get("schema_version"),
        "authority": timeline.get("authority"),
        "contract": timeline.get("contract"),
        "debugging_boundary": {
            "timeline_role": "HISTORICAL_ORIENTATION_AND_LINEAGE",
            "current_diagnosis": "VERIFY_THE_OWNING_LIVE_REPO_RUNTIME_SCHEDULER_OR_COORDINATOR",
            "absence_semantics": materialized["absence_semantics"],
        },
        "materialized": materialized,
        "view": view,
        "project": project.casefold() if project else None,
        "query": " ".join(query.split()),
        "thread": thread,
        "matching_events": len(selected),
        "events": [_compact_query_event(event) for event in selected[:effective_limit]],
        "snapshots": build_timeline_snapshots(selected, now=now) if selected else {"authority": "DERIVED_HISTORY_ONLY", "windows": []},
        "work_graph": {
            "scope": "QUERY_MATCHED" if query or project or thread else "BOUNDED_OVERVIEW",
            "summary": {
                "matched_commit_groups": len(matched_groups),
                "returned_commit_groups": min(len(matched_groups), graph_limit),
                "matched_similar_commit_groups": len(matched_similar),
                "returned_similar_commit_groups": min(len(matched_similar), graph_limit),
            },
            "store_summary": graph.get("summary", {}),
            "commit_groups": [compact_group(row) for row in matched_groups[:graph_limit]],
            "similar_commit_groups": matched_similar[:graph_limit],
        },
        "truncated": len(selected) > effective_limit,
    }
    return result


def install_task(*, minutes: int = DEFAULT_REFRESH_MINUTES) -> dict[str, Any]:
    minutes = max(1, int(minutes))
    action = f'"{sys.executable}" "{Path(__file__).resolve()}" refresh --quiet'
    command = [
        "schtasks.exe", "/Create", "/F", "/TN", TASK_NAME,
        "/SC", "MINUTE", "/MO", str(minutes), "/TR", action,
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "status": "TASK_INSTALL_ERROR", "error": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "status": "TASK_INSTALLED" if proc.returncode == 0 else "TASK_INSTALL_ERROR",
        "task": TASK_NAME,
        "minutes": minutes,
        "stdout": proc.stdout.strip()[:500],
        "stderr": proc.stderr.strip()[:500],
    }


def task_status() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["schtasks.exe", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "status": "UNKNOWN", "error": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "status": "INSTALLED" if proc.returncode == 0 else "MISSING",
        "task": TASK_NAME,
        "detail": proc.stdout.strip()[:1200] if proc.returncode == 0 else proc.stderr.strip()[:500],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize the Vault multi-source timeline and work graph.")
    sub = parser.add_subparsers(dest="command", required=True)
    refresh = sub.add_parser("refresh")
    refresh.add_argument("--root", type=Path, default=ROOT, help="Vault root to aggregate into .state/timeline")
    refresh.add_argument("--days", type=int, default=DEFAULT_DAYS)
    refresh.add_argument("--repo-events", type=int, default=DEFAULT_REPO_EVENTS)
    refresh.add_argument("--artifact-events", type=int, default=DEFAULT_ARTIFACT_EVENTS)
    refresh.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    refresh.add_argument("--no-github", action="store_true")
    refresh.add_argument("--rebuild", action="store_true", help="discard the materialized corpus and perform an explicit horizon backfill")
    refresh.add_argument("--quiet", action="store_true")
    install = sub.add_parser("install-task")
    install.add_argument("--minutes", type=int, default=DEFAULT_REFRESH_MINUTES)
    sub.add_parser("task-status")
    query = sub.add_parser("query")
    query.add_argument("--root", type=Path, default=ROOT, help="Vault root containing .state/timeline")
    query.add_argument("query", nargs="?", default="")
    query.add_argument("--view", choices=("general", "project", "errors"), default="general")
    query.add_argument("--project")
    query.add_argument("--thread")
    query.add_argument("--days", type=int)
    query.add_argument("--limit", type=int, default=20)
    query.add_argument("--no-workers", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "refresh":
        result = materialize(
            root=args.root,
            days=args.days,
            repo_events_per_repo=args.repo_events,
            artifact_events_limit=args.artifact_events,
            max_events=args.max_events,
            include_github=not args.no_github,
            rebuild=args.rebuild,
        )
        if not args.quiet:
            print(json.dumps(result, ensure_ascii=False))
        # A concurrent materializer already holding the atomic refresh lock is an
        # intentional successful no-op for periodic scheduling. Reporting it as a
        # process failure makes Task Scheduler look unhealthy even though duplicate
        # aggregation was correctly prevented.
        if result.get("status") == "ALREADY_RUNNING":
            return 0
        return 0 if result.get("ok") else 1
    if args.command == "install-task":
        result = install_task(minutes=args.minutes)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if args.command == "task-status":
        result = task_status()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    result = query_materialized(
        root=args.root,
        query=args.query,
        view=args.view,
        project=args.project,
        thread=args.thread,
        days=args.days,
        limit=args.limit,
        include_workers=not args.no_workers,
    )
    if result is None:
        print(json.dumps({"status": "MISSING", "error": "materialized timeline not available"}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
