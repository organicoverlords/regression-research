from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
import hashlib
import json
import math
import os
import pickle
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from functools import lru_cache
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
    from .memory_timeline import _event_anchors, build_continuity_graph, build_timeline, build_timeline_snapshots, is_forensic_error_event
    from .repo_timeline import RepoSpec, collect_repo_history, discover_repo_specs, tracked_artifact_events
    from .worker_report_history import worker_history_events
except ImportError:
    from memory_bank import DEFAULT_MANUAL_WORKER_HISTORY, DEFAULT_WORKER_HISTORY, build_overview, load_bank
    from memory_timeline import _event_anchors, build_continuity_graph, build_timeline, build_timeline_snapshots, is_forensic_error_event
    from repo_timeline import RepoSpec, collect_repo_history, discover_repo_specs, tracked_artifact_events
    from worker_report_history import worker_history_events

ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = ROOT / ".state" / "timeline"
STORE_PATH = STATE_ROOT / "timeline-store.json"
QUERY_INDEX_PATH = STATE_ROOT / "timeline-query-index.pkl"
QUERY_CACHE_ROOT = STATE_ROOT / "query-results"
BOOTSTRAP_PATH = STATE_ROOT / "bootstrap-memory-overview.json"
STATUS_PATH = STATE_ROOT / "status.json"
LOCK_PATH = STATE_ROOT / "refresh.lock"
QUERY_RESULT_CACHE_SECONDS = 30.0
QUERY_RESULT_CACHE_MAX_FILES = 128
QUERY_INDEX_SCHEMA = "vault.timeline.query-index.v1"

SCHEMA = "vault.timeline.materialized.v1"
BOOTSTRAP_SCHEMA = "vault.timeline.bootstrap.v1"
TASK_NAME = "Vault Timeline Materializer"
DEFAULT_DAYS: int | None = None
DEFAULT_REPO_EVENTS = 5000
DEFAULT_ARTIFACT_EVENTS = 2000
DEFAULT_REFRESH_MINUTES = 5
DEFAULT_MAX_EVENTS = 50000
DEFAULT_GITHUB_EVENTS_PER_KIND = 5000
DEFAULT_DELTA_GITHUB_EVENTS_PER_KIND = 200
DEFAULT_QUEUE_RUNS_PER_REPO = 50
DEFAULT_RUNNER_LOG_EVENTS = 10000
DEFAULT_DELTA_REPO_EVENTS_PER_REPO = 200
DEFAULT_DELTA_ARTIFACT_EVENTS = 500
DEFAULT_LIBRARY_ARTIFACT_EVENTS = 5000
DEFAULT_MACHINE_OBSERVATION_EVENTS = 5000
DEFAULT_HISTORICAL_EVIDENCE_EVENTS = 5000
DEFAULT_OVERLAP_MINUTES = 10
HISTORICAL_SOURCE_NAMES = {"library_artifacts", "mcp_history"}
HISTORICAL_EVIDENCE_FLOOR = datetime(2000, 1, 1, tzinfo=timezone.utc)
LOCK_STALE_MINUTES = 30
WORKER_ARCHIVE_SAMPLE_LIMIT = 5
WORKER_ARCHIVE_STALE_MINUTES = 90.0

_QUERY_STOP_WORDS = {
    "a", "again", "an", "and", "ask", "be", "by", "can", "could", "cross", "did", "do", "does", "figuring", "for",
    "from", "getting", "here", "history", "how", "i", "in", "is", "it", "its", "just", "keep", "make", "me", "my",
    "of", "on", "or", "our", "ours", "out", "please", "same", "so", "that", "the", "their", "them", "then", "there",
    "they", "this", "to", "us", "was", "we", "were", "what", "when", "why", "will", "with", "without", "would", "you",
    "your", "yours",
}
_QUERY_CONCEPT_GROUPS = (
    frozenset({"ram", "memory"}),
    frozenset({"paging", "pagefile"}),
    frozenset({"runner", "runners"}),
    frozenset({"proof", "evidence"}),
    frozenset({"review", "reviewed", "inspect", "inspecting", "inspection", "inspected"}),
    frozenset({"accepted", "acceptance"}),
    frozenset({"capture", "captures", "captured", "screenshot", "screenshots", "frame", "frames"}),
    frozenset({"visual", "visible", "render", "rendered", "image", "images", "picture", "pictures"}),
    frozenset({"transport", "delivery", "display", "displayed", "share", "shared", "show", "shown", "showing"}),
    frozenset({"again", "repeat", "repeated", "recurring", "recurrence"}),
    frozenset({"branch", "branches", "worktree", "worktrees"}),
    frozenset({"convergence", "converge", "converged", "merge", "merged", "integration", "integrated"}),
    frozenset({"reconnect", "reconnection", "connection", "connections"}),
    frozenset({"reroute", "rerouted", "routing", "route"}),
    frozenset({"regression", "incident"}),
    frozenset({"ci", "workflow", "action", "actions"}),
    frozenset({"pressure", "headroom", "commit"}),
)
_QUERY_CONCEPT_BY_TOKEN = {token: group for group in _QUERY_CONCEPT_GROUPS for token in group}
_QUERY_SOURCE_PRIOR = {"VAULT_MEMORY": 2.0, "WORKER_REPORT": 0.82, "GITHUB_ACTION": 0.9}
_QUERY_TOKEN_RE = re.compile(r"[a-z0-9]+")
_QUERY_WEIGHT_TO_CODE = {0.7: 1, 1.2: 2, 2.0: 3, 2.2: 4, 4.0: 5}
_QUERY_CODE_TO_WEIGHT = {code: weight for weight, code in _QUERY_WEIGHT_TO_CODE.items()}
_CAUSAL_QUERY_TOKENS = {"why", "cause", "causal", "because", "caused"}
_CAUSAL_CORRECTION_PHRASES = (
    "did not reproduce",
    "didn't reproduce",
    "not reproduce",
    "did not cause",
    "not the cause",
    "paging not sufficient",
    "not_proven",
    "causal falsifier",
    "causal link not proven",
    "causality not proven",
    "ruled out",
    "disproved",
)
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
LIBRARY_ARTIFACT_GLOBS = ("*library_screenshot*.jsonl", "*chatgpt_artifact_occurrences*.jsonl", "*library_artifact_occurrences*.jsonl")


def _dt(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _instant_key(value: Any) -> datetime:
    parsed = _dt(value)
    if parsed is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def _atomic_pickle(path: Path, payload: dict[str, Any]) -> None:
    """Write a trusted local derived read cache atomically; canonical JSON remains authoritative."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with tmp.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)


def _read_query_index(path: Path, *, generated_at: str) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            value = pickle.load(handle)
    except (OSError, EOFError, pickle.PickleError, AttributeError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("schema") != QUERY_INDEX_SCHEMA:
        return None
    if str(value.get("generated_at") or "") != generated_at:
        return None
    ids = value.get("ids")
    postings = value.get("postings")
    anchors = value.get("anchors")
    weight_codes = value.get("weight_codes")
    if (
        not isinstance(ids, list) or not isinstance(postings, dict) or not isinstance(anchors, list)
        or not isinstance(weight_codes, dict) or len(ids) != len(anchors)
    ):
        return None
    return value


def _store_generation_token(root: Path) -> str | None:
    try:
        stat = (root / ".state" / "timeline" / STORE_PATH.name).stat()
    except OSError:
        return None
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _run_process(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Run a child process without creating or showing a console window on Windows."""
    if os.name == "nt":
        kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if "startupinfo" not in kwargs and hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
            startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            kwargs["startupinfo"] = startupinfo
    return subprocess.run(*args, **kwargs)

def _run_json(command: list[str], *, timeout: int = 30) -> tuple[Any, str | None]:
    try:
        proc = _run_process(
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
        proc = _run_process(
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
        log = _run_process(
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
        patch = _run_process(
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
    snapshot_now: datetime | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    snapshot_now = snapshot_now or datetime.now().astimezone()
    coverage: dict[str, Any] = {"available": True, "repos": {}, "errors": [], "warnings": [], "snapshot_errors": []}
    for spec in specs:
        slug = _github_slug(spec)
        if not slug:
            continue
        repo_cov = {
            "project": spec.project,
            "issues": {"events": 0, "limit": limit_per_kind, "saturated": False},
            "prs": {"events": 0, "limit": limit_per_kind, "saturated": False},
            "actions": {"events": 0, "limit": limit_per_kind, "saturated": False},
            "queue": {
                "events": 0,
                "limit": DEFAULT_QUEUE_RUNS_PER_REPO,
                "queued": 0,
                "in_progress": 0,
                "available": True,
                "bounded": False,
                "complete": True,
                "absence_semantics": "NO_ACTIVE_RUNS_IN_COMPLETE_SNAPSHOT",
            },
            "builds": {
                "runs": 0,
                "completed": 0,
                "success": 0,
                "failure": 0,
                "cancelled": 0,
                "other": 0,
            },
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

        action_saturation_limit = limit_per_kind
        action_rows, err = _run_json([
            "gh", "run", "list", "--repo", slug, "--created", ">=" + since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "--limit", str(limit_per_kind),
            "--json", "databaseId,workflowName,status,conclusion,createdAt,updatedAt,headSha,headBranch,event,displayTitle,url",
        ])
        if err:
            fallback_limit = min(limit_per_kind, DEFAULT_DELTA_GITHUB_EVENTS_PER_KIND)
            fallback_rows, fallback_err = _run_json([
                "gh", "run", "list", "--repo", slug,
                "--created", ">=" + since.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "--limit", str(fallback_limit),
                "--json", "databaseId,workflowName,status,conclusion,createdAt,updatedAt,headSha,headBranch,event,displayTitle,url",
            ])
            if isinstance(fallback_rows, list) and not fallback_err:
                action_rows = fallback_rows
                action_saturation_limit = fallback_limit
                coverage["warnings"].append({
                    "repo": slug,
                    "source": "actions",
                    "error": err,
                    "fallback_limit": fallback_limit,
                })
            else:
                coverage["errors"].append({
                    "repo": slug,
                    "source": "actions",
                    "error": err,
                    "fallback_error": fallback_err,
                })
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

        queue_rows, queue_err = _run_json([
            "gh", "run", "list", "--repo", slug,
            "--limit", str(DEFAULT_QUEUE_RUNS_PER_REPO),
            "--json", "databaseId,workflowName,status,conclusion,createdAt,updatedAt,headSha,headBranch,event,displayTitle,url",
        ])
        if queue_err:
            coverage["snapshot_errors"].append({"repo": slug, "source": "queue", "error": queue_err})
        queue_rows = queue_rows if isinstance(queue_rows, list) else []
        queue_items = []
        for row in queue_rows:
            status = str(row.get("status") or "").casefold()
            if status not in {"queued", "in_progress"}:
                continue
            queue_items.append({
                "run_id": str(row.get("databaseId") or ""),
                "workflow": row.get("workflowName"),
                "status": row.get("status"),
                "created_at": row.get("createdAt"),
                "updated_at": row.get("updatedAt"),
                "head_sha": row.get("headSha"),
                "head_ref": row.get("headBranch"),
                "event": row.get("event"),
                "title": row.get("displayTitle"),
                "url": row.get("url"),
            })
        queue_bounded = len(queue_rows) >= DEFAULT_QUEUE_RUNS_PER_REPO
        queue_available = not bool(queue_err)
        queue_complete = queue_available and not queue_bounded
        repo_cov["queue"]["events"] = len(queue_items)
        repo_cov["queue"]["queued"] = sum(1 for row in queue_items if str(row.get("status") or "").casefold() == "queued")
        repo_cov["queue"]["in_progress"] = sum(1 for row in queue_items if str(row.get("status") or "").casefold() == "in_progress")
        repo_cov["queue"]["available"] = queue_available
        repo_cov["queue"]["bounded"] = queue_bounded
        repo_cov["queue"]["complete"] = queue_complete
        repo_cov["queue"]["absence_semantics"] = (
            "NO_ACTIVE_RUNS_IN_COMPLETE_SNAPSHOT"
            if queue_complete
            else "NO_MATCH_IS_NOT_PROOF_QUEUE_IS_EMPTY"
        )
        action_rows_for_counts = action_rows if isinstance(action_rows, list) else []
        conclusions = [str(row.get("conclusion") or "").casefold() for row in action_rows_for_counts]
        repo_cov["builds"] = {
            "runs": len(action_rows_for_counts),
            "completed": sum(1 for row in action_rows_for_counts if str(row.get("status") or "").casefold() == "completed"),
            "success": conclusions.count("success"),
            "failure": conclusions.count("failure"),
            "cancelled": conclusions.count("cancelled"),
            "other": sum(1 for value in conclusions if value not in {"success", "failure", "cancelled", ""}),
        }
        summary_at = snapshot_now.isoformat()
        queue_label = (
            "queue unknown"
            if not queue_available
            else f"queue sample {repo_cov['queue']['queued']} queued/{repo_cov['queue']['in_progress']} in progress"
            if queue_bounded
            else f"queue {repo_cov['queue']['queued']} queued/{repo_cov['queue']['in_progress']} in progress"
        )
        events.append({
            "id": f"github-action-summary:{slug}",
            "source_type": "GITHUB_ACTION_SUMMARY",
            "authority": "GITHUB_ACTIONS_HISTORY_AND_QUEUE_ORIENTATION_SNAPSHOT",
            "event_at": summary_at,
            "recorded_at": summary_at,
            "project": spec.project,
            "projects": [spec.project],
            "title": f"GitHub actions {slug}: {repo_cov['builds']['runs']} recent action runs; {queue_label}",
            "summary": f"completed={repo_cov['builds']['completed']} success={repo_cov['builds']['success']} failure={repo_cov['builds']['failure']}; queue={repo_cov['queue']['absence_semantics']}",
            "github_repo": slug,
            "current_only": True,
            "timeline_role": "ORIENTATION_SNAPSHOT_NOT_CURRENT_AUTHORITY",
            "live_truth_required": True,
            "build_counts": {
                **dict(repo_cov["builds"]),
                "scope": "since_source_watermark",
                "since": since.isoformat(),
            },
            "queue_counts": {
                "queued": repo_cov["queue"]["queued"],
                "in_progress": repo_cov["queue"]["in_progress"],
                "active_items_sampled": len(queue_items),
                "runs_scanned": len(queue_rows),
                "limit": DEFAULT_QUEUE_RUNS_PER_REPO,
                "available": queue_available,
                "bounded": queue_bounded,
                "complete": queue_complete,
                "absence_semantics": repo_cov["queue"]["absence_semantics"],
            },
            "queue_items": queue_items,
            "anchors": [f"github-actions:{slug}", f"github-queue:{slug}"],
            "refs": [str(row.get("run_id")) for row in queue_items if row.get("run_id")],
            "thread_id": f"actions:{slug}",
            "thread_source": "GITHUB_ACTIONS_AND_QUEUE",
        })
        repo_cov["issues"]["saturated"] = isinstance(issue_rows, list) and len(issue_rows) >= limit_per_kind
        repo_cov["prs"]["saturated"] = isinstance(pr_rows, list) and len(pr_rows) >= limit_per_kind
        repo_cov["actions"]["saturated"] = isinstance(action_rows, list) and len(action_rows) >= action_saturation_limit
        repo_cov["limit_per_kind"] = limit_per_kind
        # Only historical delta sources control the GitHub watermark/retry state.
        # The queue is a current bounded orientation snapshot; its cap/error must
        # never weaken historical absence semantics or pin the GitHub watermark.
        repo_cov["saturated_kinds"] = [
            kind for kind in ("issues", "prs", "actions")
            if bool(repo_cov[kind].get("saturated"))
        ]
        repo_cov["bounded_snapshot_kinds"] = ["queue"] if queue_bounded else []
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
    if "/chatgptmcpclean" in text:
        return "mcp"
    if "/.agents" in text or text.endswith("/.agents"):
        return "agents"
    if "/busycoordinator" in text:
        return "coordinator"
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


def mcp_replacement_events(*, since: datetime, limit: int = 1000) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project immutable MCP production replacement receipts as long-lived version history."""
    local = Path(os.path.expandvars(r"%LOCALAPPDATA%"))
    mcp_roots = [local / "ChatGPTMcpClean", local / "ChatGPTMcpMinimal"]
    events: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {"roots": [], "candidates": 0, "events": 0, "limit": limit, "saturated": False, "errors": []}
    for mcp_root in mcp_roots:
        replacement_root = mcp_root / ".state" / "production-replacement"
        if not replacement_root.exists():
            continue
        coverage["roots"].append(str(replacement_root))
        try:
            paths = sorted(replacement_root.glob("receipt-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        except OSError as exc:
            coverage["errors"].append(f"{replacement_root}:{type(exc).__name__}")
            continue
        coverage["candidates"] += len(paths)
        if len(paths) > limit:
            coverage["saturated"] = True
        for path in paths[:limit]:
            row = _read_json(path)
            if not row:
                continue
            event_at = row.get("recorded_at")
            if not _event_time_ok(event_at, since):
                continue
            request_id = str(row.get("request_id") or path.stem.removeprefix("receipt-")).strip()
            old_head = str(row.get("old_head") or "").strip().casefold()
            new_head = str(row.get("new_head") or "").strip().casefold()
            expected_head = str(row.get("expected_candidate_commit") or "").strip().casefold()
            old_generation = str(row.get("old_generation") or row.get("expected_current_generation") or "").strip()
            new_generation = str(row.get("new_generation") or "").strip()
            candidate_generation = str(row.get("candidate_generation") or "").strip()
            refs = [value for value in (old_head, new_head, expected_head, old_generation, new_generation, candidate_generation) if value]
            for value in (old_head, new_head, expected_head):
                if _SHA_RE.fullmatch(value):
                    refs.extend([value[:10], value[:7]])
            refs = sorted(set(refs))
            anchors = [f"mcp-replacement:{request_id.casefold()}"]
            anchors.extend(f"gitsha:{value}" for value in (old_head, new_head, expected_head) if _SHA_RE.fullmatch(value))
            anchors.extend(f"mcp-generation:{value.casefold()}" for value in (old_generation, new_generation, candidate_generation) if value)
            status = row.get("status")
            transition = f"{old_head[:10] or '?'} -> {new_head[:10] or expected_head[:10] or '?'}"
            events.append({
                "id": f"mcp-replacement:{mcp_root.name}:{request_id.casefold()}",
                "source_type": "MCP_EVENT",
                "authority": "LOCAL_MCP_PRODUCTION_REPLACEMENT_RECEIPT_HISTORY",
                "event_at": event_at,
                "recorded_at": event_at,
                "project": "chatgpt-mcp-clean",
                "projects": ["chatgpt-mcp-clean"],
                "title": f"MCP production replacement {transition}: {status}",
                "summary": "historical production replacement receipt; version/generation evidence only",
                "mcp_root": str(mcp_root),
                "mcp_event": "production_replacement",
                "request_id": request_id,
                "status": status,
                "runtime_changed": row.get("runtime_changed"),
                "old_head": old_head or None,
                "new_head": new_head or None,
                "expected_candidate_commit": expected_head or None,
                "old_generation": old_generation or None,
                "new_generation": new_generation or None,
                "candidate_generation": candidate_generation or None,
                "old_dist_sha256": row.get("old_dist_sha256"),
                "new_dist_sha256": row.get("new_dist_sha256"),
                "candidate_port": row.get("candidate_port"),
                "refs": refs,
                "anchors": sorted(set(anchors)),
                "thread_id": "mcp-production-replacement",
                "thread_source": "MCP_PRODUCTION_REPLACEMENT_RECEIPT",
                "retain_history": True,
            })
    events.sort(key=lambda event: _dt(event.get("event_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    coverage["events"] = len(events)
    return events, coverage


def coordinator_events(*, since: datetime, snapshot_now: datetime | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Capture current Busy collision state without promoting it to liveness/history authority."""
    del since
    snapshot_now = snapshot_now or datetime.now().astimezone()
    local = Path(os.path.expandvars(r"%LOCALAPPDATA%"))
    configured = os.environ.get("BUSY_STORE_PATH") or os.environ.get("MCP_BUSY_STORE_PATH")
    store = Path(configured) if configured else local / "ChatGPTMcpClean" / ".state" / "busy-claims.json"
    coverage: dict[str, Any] = {
        "path": str(store),
        "available": False,
        "events": 0,
        "stored_claim_records": 0,
        "stored_jobs": 0,
        "active_jobs": 0,
        "active_claim_scopes": 0,
        "expired_active_jobs": 0,
        "uncertain_active_jobs": 0,
        "operations": 0,
        "errors": [],
        "current_only": True,
        "coverage_role": "CURRENT_COLLISION_SNAPSHOT_NOT_HISTORICAL_INGESTION",
    }
    if not store.exists():
        coverage["errors"].append("STORE_MISSING")
        return [], coverage
    state = _read_json(store)
    if not isinstance(state, dict):
        coverage["errors"].append("STORE_UNREADABLE")
        return [], coverage
    raw_claims = state.get("claims") if isinstance(state.get("claims"), list) else []
    coordinator = state.get("coordinator") if isinstance(state.get("coordinator"), dict) else {}
    raw_jobs = coordinator.get("jobs") if isinstance(coordinator.get("jobs"), dict) else {}
    raw_operations = coordinator.get("operations") if isinstance(coordinator.get("operations"), dict) else {}
    claims = [row for row in raw_claims if isinstance(row, dict)]
    jobs = [row for row in raw_jobs.values() if isinstance(row, dict)]
    live_jobs: list[dict[str, Any]] = []
    expired_active_jobs = 0
    uncertain_active_jobs = 0
    for row in jobs:
        if str(row.get("state") or "").casefold() != "active":
            continue
        expiry = _dt(row.get("lease_expires_at"))
        if expiry is None:
            uncertain_active_jobs += 1
            continue
        if expiry <= snapshot_now.astimezone(expiry.tzinfo):
            expired_active_jobs += 1
            continue
        live_jobs.append(row)
    active_scopes = sorted({str(row.get("scope") or "") for row in live_jobs if row.get("scope")})[:32]
    snapshot = {
        "stored_claim_records": len(claims),
        "stored_jobs": len(jobs),
        "active_jobs": len(live_jobs),
        "active_claim_scopes": len(active_scopes),
        "expired_active_jobs": expired_active_jobs,
        "uncertain_active_jobs": uncertain_active_jobs,
        "operations": len(raw_operations),
        "active_scopes": active_scopes,
    }
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    event_at = snapshot_now.isoformat()
    event = {
        "id": "coordinator-state-snapshot",
        "source_type": "COORDINATOR_EVENT",
        "authority": "LOCAL_COORDINATOR_CURRENT_COLLISION_SNAPSHOT",
        "event_at": event_at,
        "recorded_at": event_at,
        "project": "coordinator",
        "projects": ["coordinator"],
        "title": f"Coordinator snapshot: {snapshot['active_jobs']} active leased jobs; {snapshot['active_claim_scopes']} active scopes",
        "summary": "Busy collision-control orientation only; not scheduler membership, process liveness, priority, or historical completeness",
        "coordinator_state": snapshot,
        "state_fingerprint": digest,
        "current_only": True,
        "timeline_role": "CONTEXT_ONLY_CURRENT_SNAPSHOT",
        "live_truth_required": True,
        "evidence_semantics": "COLLISION_ORIENTATION_ONLY_NOT_SCHEDULER_LIVENESS_OR_PRIORITY",
        "refs": active_scopes,
        "anchors": [f"coordinator-state:{digest}"],
        "thread_id": "coordinator",
        "thread_source": "COORDINATOR_STATE",
    }
    coverage.update({**snapshot, "available": True, "events": 1})
    return [event], coverage


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


def runner_log_events(*, since: datetime, limit: int = DEFAULT_RUNNER_LOG_EVENTS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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


def library_artifact_events(
    root: Path, *, since: datetime, limit: int = DEFAULT_LIBRARY_ARTIFACT_EVENTS
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Expand durable ChatGPT/Library provenance manifests into per-artifact history events."""
    evidence_root = root / "02 Evidence"
    paths: set[Path] = set()
    for pattern in LIBRARY_ARTIFACT_GLOBS:
        try:
            paths.update(path for path in evidence_root.glob(pattern) if path.is_file())
        except OSError:
            continue
    by_id: dict[str, dict[str, Any]] = {}
    coverage: dict[str, Any] = {"files": 0, "rows": 0, "events": 0, "limit": limit, "saturated": False, "errors": []}
    for path in sorted(paths):
        try:
            rows = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        except OSError as exc:
            coverage["errors"].append(f"{path.name}:{type(exc).__name__}")
            continue
        coverage["files"] += 1
        for line_number, raw in enumerate(rows, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                coverage["errors"].append(f"{path.name}:{line_number}:invalid_json")
                continue
            if not isinstance(row, dict):
                continue
            coverage["rows"] += 1
            event_at = (
                row.get("capture_time_local")
                or row.get("created_at_utc")
                or row.get("uploaded_at_utc")
                or row.get("observed_at")
                or row.get("modified_at_utc")
            )
            stamp = _dt(event_at)
            observed_at = row.get("observed_at") or row.get("indexed_at") or row.get("created_at_utc") or row.get("uploaded_at_utc") or event_at
            observed_stamp = _dt(observed_at)
            if stamp is None or observed_stamp is None or observed_stamp < since.astimezone(observed_stamp.tzinfo):
                continue
            file_id = str(row.get("library_file_id") or row.get("file_id") or "").strip()
            occurrence_id = str(row.get("occurrence_id") or "").strip()
            filename = str(row.get("filename") or row.get("name") or file_id or occurrence_id or "library artifact").strip()
            stable = file_id or occurrence_id
            if not stable:
                stable = hashlib.sha256(f"{path.name}:{line_number}:{filename}:{event_at}".encode("utf-8", "replace")).hexdigest()[:24]
            declared_type = str(row.get("artifact_type") or "").strip()
            artifact_type = declared_type or ("screenshot" if Path(filename).suffix.casefold() in IMAGE_SUFFIXES else "library_artifact")
            subject = str(row.get("subject") or row.get("description") or "").strip()
            summary = subject[:500] if subject else "ChatGPT Library/conversation artifact provenance observation"
            anchors = [f"library-file:{file_id.casefold()}" if file_id else f"library-artifact:{stable.casefold()}"]
            if occurrence_id:
                anchors.append(f"library-occurrence:{occurrence_id.casefold()}")
            text_path = str(row.get("text_path") or "").strip()
            refs = [value for value in (file_id, occurrence_id, text_path) if value]
            project = str(row.get("project") or "").strip() or None
            event = {
                "id": f"library-artifact:{stable.casefold()}",
                "source_type": "LIBRARY_ARTIFACT",
                "authority": "CHATGPT_LIBRARY_HISTORICAL_OBSERVATION",
                "event_at": stamp.isoformat(),
                "recorded_at": observed_stamp.isoformat(),
                "project": project,
                "projects": [project] if project else [],
                "title": f"{artifact_type}: {filename}",
                "summary": summary,
                "artifact_type": artifact_type,
                "filename": filename,
                "library_file_id": file_id or None,
                "occurrence_id": occurrence_id or None,
                "source_kind": row.get("source_kind"),
                "model_generated": row.get("model_generated"),
                "user_turn_index": row.get("user_turn_index"),
                "classification": row.get("classification"),
                "review_status": row.get("review_status"),
                "timestamp_source": row.get("timestamp_source") or ("LIBRARY_CREATED_AT" if row.get("created_at_utc") else None),
                "size_bytes": row.get("size_bytes"),
                "text_path": text_path or None,
                "text_sha256": row.get("text_sha256"),
                "tags": list(row.get("tags") or []),
                "manifest_path": path.relative_to(root).as_posix(),
                "refs": refs,
                "anchors": sorted(set(anchors)),
                "thread_id": f"library-file:{(file_id or stable).casefold()}",
                "thread_source": "CHATGPT_LIBRARY_FILE_ID",
                "retain_history": True,
            }
            by_id[event["id"]] = event
    events = sorted(
        by_id.values(),
        key=lambda event: (_dt(event.get("event_at")) or datetime.min.replace(tzinfo=timezone.utc), str(event.get("id") or "")),
        reverse=True,
    )
    coverage["saturated"] = len(events) > limit
    events = events[:limit]
    coverage["events"] = len(events)
    return events, coverage


def machine_observation_events(
    *, since: datetime, limit: int = DEFAULT_MACHINE_OBSERVATION_EVENTS
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Project persisted bootstrap PC observations as historical evidence, never live authority."""
    local = Path(os.path.expandvars(r"%LOCALAPPDATA%"))
    path = local / "ChatGPTMcpClean" / ".state" / "bootstrap-observations.jsonl"
    max_bytes = 4 * 1024 * 1024
    coverage: dict[str, Any] = {
        "path": str(path), "rows": 0, "events": 0, "limit": limit, "tail_bytes": max_bytes,
        "tail_truncated": False, "saturated": False, "errors": [],
    }
    try:
        coverage["tail_truncated"] = path.stat().st_size > max_bytes
    except OSError:
        pass
    events: list[dict[str, Any]] = []
    for line_number, raw in enumerate(_read_tail(path, max_bytes).decode("utf-8", "replace").splitlines(), 1):
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            coverage["errors"].append(f"line:{line_number}:invalid_json")
            continue
        if not isinstance(row, dict):
            continue
        coverage["rows"] += 1
        stamp = _dt(row.get("at"))
        if stamp is None or stamp < since.astimezone(stamp.tzinfo):
            continue
        free_gb = row.get("free_gb")
        title = f"machine snapshot: C free {free_gb} GB" if free_gb is not None else "machine snapshot"
        summary_fields = []
        for key in ("free_gb", "disk_used_gb", "physical_free_gb", "commit_headroom_gb", "commit_used_pct", "vram_free_mb", "gpu_utilization_pct"):
            if row.get(key) is not None:
                summary_fields.append(f"{key}={row.get(key)}")
        at_key = stamp.astimezone(timezone.utc).isoformat()
        event = {
            "id": f"machine-observation:{at_key}",
            "source_type": "MACHINE_OBSERVATION",
            "authority": "LOCAL_BOOTSTRAP_MACHINE_OBSERVATION_HISTORY",
            "event_at": stamp.isoformat(),
            "recorded_at": stamp.isoformat(),
            "title": title,
            "summary": "; ".join(summary_fields) or "persisted bootstrap machine observation",
            "artifact_type": "machine_snapshot",
            "drive": row.get("drive") or "C:",
            "free_gb": free_gb,
            "disk_used_gb": row.get("disk_used_gb"),
            "disk_total_gb": row.get("disk_total_gb"),
            "disk_used_pct": row.get("disk_used_pct"),
            "disk_status": row.get("disk_status"),
            "physical_free_gb": row.get("physical_free_gb"),
            "physical_free_pct": row.get("physical_free_pct"),
            "commit_used_gb": row.get("commit_used_gb"),
            "commit_limit_gb": row.get("commit_limit_gb"),
            "commit_headroom_gb": row.get("commit_headroom_gb"),
            "commit_used_pct": row.get("commit_used_pct"),
            "memory_status": row.get("memory_status"),
            "vram_used_mb": row.get("vram_used_mb"),
            "vram_free_mb": row.get("vram_free_mb"),
            "vram_total_mb": row.get("vram_total_mb"),
            "gpu_utilization_pct": row.get("gpu_utilization_pct"),
            "gpu_sample_status": row.get("gpu_sample_status"),
            "refs": [str(path)],
            "anchors": ["machine:pc-resource-history"],
            "thread_id": "machine:pc-resource-history",
            "thread_source": "BOOTSTRAP_OBSERVATION_LOG",
        }
        events.append(event)
    events.sort(key=lambda event: _dt(event.get("event_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    coverage["saturated"] = bool(coverage["tail_truncated"] or len(events) > limit)
    events = events[:limit]
    coverage["events"] = len(events)
    return events, coverage


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


def _build_sha_group_index(commit_to_group: dict[str, str]) -> tuple[list[str], list[int]]:
    shas = sorted(commit_to_group)
    return shas, sorted({len(sha) for sha in shas})


def _groups_for_sha_ref(
    ref: str,
    commit_to_group: dict[str, str],
    sorted_shas: list[str],
    sha_lengths: list[int],
) -> set[str]:
    """Resolve exact or abbreviated SHA evidence without scanning every commit."""
    low = str(ref or "").casefold()
    if not low:
        return set()
    out: set[str] = set()

    # A short evidence SHA may prefix one or more full commit SHAs. Bisect narrows
    # the search to that lexicographic prefix range instead of walking all commits.
    start = bisect_left(sorted_shas, low)
    end = bisect_right(sorted_shas, low + "￿")
    for sha in sorted_shas[start:end]:
        if sha.startswith(low):
            out.add(commit_to_group[sha])

    # Preserve the legacy inverse-prefix behavior for any unusually short commit
    # SHA stored in historical evidence.
    for length in sha_lengths:
        if length >= len(low):
            break
        group_id = commit_to_group.get(low[:length])
        if group_id is not None:
            out.add(group_id)
    return out


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

    sorted_commit_shas, commit_sha_lengths = _build_sha_group_index(commit_to_group)

    def groups_for_sha(ref: str) -> set[str]:
        return _groups_for_sha_ref(ref, commit_to_group, sorted_commit_shas, commit_sha_lengths)

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
                    "finding_tags": event.get("finding_tags") or [],
                    "summary": event.get("summary"),
                    "findings": event.get("findings"),
                    "validation": event.get("validation"),
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
        latest_candidates = (
            [str(commit.get("at") or "") for commit in row["commits"]]
            + [str(events_by_id[event_id].get("event_at") or "") for event_id in row["attached_event_ids"] if event_id in events_by_id]
        )
        row["latest_at"] = max(
            latest_candidates, key=lambda value: (_instant_key(value), value)
        ) if latest_candidates else None

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
            if not item["latest_at"] or _instant_key(stamp) > _instant_key(item["latest_at"]):
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
    workstream_rows.sort(key=lambda item: (_instant_key(item.get("latest_at")), item["anchor"]), reverse=True)

    group_list = list(group_rows.values())
    group_list.sort(key=lambda item: (_instant_key(item.get("latest_at")), item["work_id"]), reverse=True)
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


def _pid_liveness(pid: int) -> bool | None:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            open_process = kernel32.OpenProcess
            open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            open_process.restype = ctypes.c_void_p
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [ctypes.c_void_p]
            close_handle.restype = ctypes.c_int
            handle = open_process(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                close_handle(handle)
                return True
            error = ctypes.get_last_error()
            if error == 87:  # ERROR_INVALID_PARAMETER: no such process
                return False
            if error == 5:  # ERROR_ACCESS_DENIED still proves a process owns the PID
                return True
            return None
        except Exception:
            return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _lock_owner_liveness(path: Path) -> bool | None:
    try:
        first_line = path.read_text(encoding="ascii").splitlines()[0].strip()
        return _pid_liveness(int(first_line))
    except (OSError, ValueError, IndexError):
        return False


def _acquire_lock(path: Path) -> int | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            age = time.time() - path.stat().st_mtime
            if age > LOCK_STALE_MINUTES * 60 and _lock_owner_liveness(path) is False:
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
        return HISTORICAL_EVIDENCE_FLOOR if source in HISTORICAL_SOURCE_NAMES else horizon_since
    watermarks = previous.get("source_watermarks") if isinstance(previous.get("source_watermarks"), dict) else {}
    if source not in watermarks:
        return HISTORICAL_EVIDENCE_FLOOR if source in HISTORICAL_SOURCE_NAMES else horizon_since
    raw = watermarks.get(source) or previous.get("generated_at")
    stamp = _dt(raw)
    if stamp is None:
        return horizon_since
    candidate = stamp - timedelta(minutes=max(0, int(overlap_minutes)))
    if source in HISTORICAL_SOURCE_NAMES:
        return candidate
    return max(horizon_since.astimezone(candidate.tzinfo), candidate)


def _event_within_horizon(event: dict[str, Any], since: datetime) -> bool:
    stamp = _dt(event.get("event_at"))
    return bool(stamp and stamp >= since.astimezone(stamp.tzinfo))


def build_worker_archive_summary(
    events: Iterable[dict[str, Any]], *, now: datetime | None = None, horizon_days: int | None = None,
) -> dict[str, Any]:
    """Summarize timed archived worker quality from already-materialized worker events."""
    now = now or datetime.now(timezone.utc)
    latest_by_worker: dict[str, dict[str, Any]] = {}
    worker_ids_seen: set[str] = set()
    for event in events:
        if not isinstance(event, dict) or event.get("source_type") != "WORKER_REPORT":
            continue
        if str(event.get("population") or "timed").strip().casefold() != "timed":
            continue
        worker_id = str(event.get("automation_id") or "").strip()
        if not worker_id:
            continue
        finished = _dt(event.get("event_at"))
        if finished is None:
            continue
        finished = finished.astimezone(timezone.utc)
        worker_ids_seen.add(worker_id)
        previous = latest_by_worker.get(worker_id)
        if previous is not None and finished <= previous["_finished_dt"]:
            continue
        duration = event.get("duration_minutes")
        target = event.get("target_run_minutes")
        if not isinstance(target, (int, float)) or target <= 0:
            target = 24.0
        utilization = event.get("target_utilization_pct")
        if not isinstance(utilization, (int, float)) and isinstance(duration, (int, float)):
            utilization = round(float(duration) * 100 / float(target), 1)
        util = float(utilization) if isinstance(utilization, (int, float)) else None
        if util is None:
            classification = "UNKNOWN"
        elif util < 25:
            classification = "SEVERELY_PREMATURE"
        elif util < 60:
            classification = "PREMATURE"
        elif util < 80:
            classification = "SHORT"
        else:
            classification = "ON_TARGET"
        age_minutes = max(0.0, (now.astimezone(timezone.utc) - finished).total_seconds() / 60.0)
        latest_by_worker[worker_id] = {
            "_finished_dt": finished,
            "automation_id": worker_id,
            "display_label": event.get("display_label") or event.get("worker"),
            "finished_at": event.get("event_at"),
            "age_minutes": round(age_minutes, 1),
            "report_freshness": "STALE" if age_minutes >= WORKER_ARCHIVE_STALE_MINUTES else "RECENT",
            "duration_minutes": round(float(duration), 2) if isinstance(duration, (int, float)) else None,
            "target_minutes": round(float(target), 2),
            "target_utilization_pct": round(util, 1) if util is not None else None,
            "classification": classification,
        }
    latest_archived = sorted(
        latest_by_worker.values(), key=lambda item: item["_finished_dt"], reverse=True
    )[:WORKER_ARCHIVE_SAMPLE_LIMIT]
    for item in latest_archived:
        item.pop("_finished_dt", None)
    util_values = [
        float(item["target_utilization_pct"]) for item in latest_archived
        if isinstance(item.get("target_utilization_pct"), (int, float))
    ]
    duration_values = [
        float(item["duration_minutes"]) for item in latest_archived
        if isinstance(item.get("duration_minutes"), (int, float))
    ]
    attention = [
        {
            "worker": item.get("display_label"),
            "duration_minutes": item.get("duration_minutes"),
            "target_minutes": item.get("target_minutes"),
            "utilization_pct": item.get("target_utilization_pct"),
            "classification": item.get("classification"),
            "age_minutes": item.get("age_minutes"),
        }
        for item in latest_archived
        if item.get("report_freshness") == "RECENT"
        and item.get("classification") in {"SHORT", "PREMATURE", "SEVERELY_PREMATURE"}
    ]
    stale_reports = [
        {
            "worker": item.get("display_label"),
            "age_minutes": item.get("age_minutes"),
            "last_archived_classification": item.get("classification"),
        }
        for item in latest_archived if item.get("report_freshness") == "STALE"
    ]
    scope = "timed_worker_reports_in_materialized_horizon"
    return {
        "available": True,
        "generated_at": now.isoformat(),
        "read_mode": "MATERIALIZED_ONLY",
        "population_scope": scope,
        "horizon_days": horizon_days,
        "target_run_minutes": 24.0,
        "stale_after_minutes": WORKER_ARCHIVE_STALE_MINUTES,
        "evidence_semantics": "archived_run_quality_only_not_current_worker_liveness_or_scheduler_membership",
        "current_scheduler_membership": {
            "available": False,
            "authority": "ChatGPT Automations state",
            "reason": "current enabled scheduler membership is not derivable from worker report history",
        },
        "latest_archived_per_worker": latest_archived,
        "archive_sample": {
            "selection": "five_most_recent_latest_timed_archives_in_materialized_horizon",
            "sample_limit": WORKER_ARCHIVE_SAMPLE_LIMIT,
            "sampled_worker_count": len(latest_archived),
            "historical_worker_ids_seen": len(worker_ids_seen),
            "population_scope": scope,
            "average_latest_duration_minutes": round(sum(duration_values) / len(duration_values), 2) if duration_values else None,
            "average_latest_utilization_pct": round(sum(util_values) / len(util_values), 1) if util_values else None,
            "on_target_count": sum(1 for item in latest_archived if item.get("classification") == "ON_TARGET"),
            "short_or_worse_count": len(attention),
            "stale_report_count": len(stale_reports),
        },
        "attention": attention,
        "stale_reports": stale_reports,
        "classification": {"ON_TARGET": ">=80%", "SHORT": "60-79%", "PREMATURE": "25-59%", "SEVERELY_PREMATURE": "<25%"},
    }


def _bootstrap_worker_projection(summary: dict[str, Any]) -> dict[str, Any]:
    """Keep the bootstrap worker projection tiny while preserving aggregate quality signals."""
    keys = (
        "available", "generated_at", "read_mode", "population_scope", "horizon_days",
        "evidence_semantics", "current_scheduler_membership", "archive_sample", "attention", "stale_reports",
    )
    return {key: summary.get(key) for key in keys if key in summary}


def _merge_materialized_events(
    previous_events: Iterable[dict[str, Any]],
    delta_events: Iterable[dict[str, Any]],
    *,
    since: datetime,
) -> list[dict[str, Any]]:
    """Merge history by stable ID; current-only snapshots must be re-emitted each refresh."""
    by_id: dict[str, dict[str, Any]] = {}
    for is_previous, rows in ((True, previous_events), (False, delta_events)):
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            if is_previous and raw.get("current_only"):
                continue
            if not raw.get("retain_history") and not _event_within_horizon(raw, since):
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
    if source == "library_artifacts":
        return bool(coverage.get("saturated")) or bool(coverage.get("errors"))
    if source == "machine":
        return bool(coverage.get("saturated")) or bool(coverage.get("errors"))
    if source == "github":
        return bool(coverage.get("saturated")) or bool(coverage.get("errors"))
    if source == "mcp":
        return bool(coverage.get("receipts_saturated")) or bool(coverage.get("errors"))
    if source == "mcp_history":
        return bool(coverage.get("saturated")) or bool(coverage.get("errors"))
    if source == "runner_logs":
        return bool(coverage.get("saturated")) or bool(coverage.get("errors"))
    if source == "coordinator":
        # Coordinator data is a current collision-orientation snapshot, not a
        # historical ingestion lane. Missing/uncertain state must not freeze
        # timeline watermarks or weaken historical no-match semantics.
        return False
    return False


def materialize(
    *,
    root: Path = ROOT,
    state_root: Path | None = None,
    now: datetime | None = None,
    days: int | None = DEFAULT_DAYS,
    repo_events_per_repo: int = DEFAULT_REPO_EVENTS,
    artifact_events_limit: int = DEFAULT_ARTIFACT_EVENTS,
    max_events: int = DEFAULT_MAX_EVENTS,
    include_github: bool = True,
    github_events_per_kind: int = DEFAULT_GITHUB_EVENTS_PER_KIND,
    runner_events_limit: int = DEFAULT_RUNNER_LOG_EVENTS,
    rebuild: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    now = now or datetime.now().astimezone()
    horizon_since = HISTORICAL_EVIDENCE_FLOOR if days is None else now - timedelta(days=max(1, int(days)))
    state_root = state_root or (root / ".state" / "timeline")
    store_path = state_root / STORE_PATH.name
    query_index_path = state_root / QUERY_INDEX_PATH.name
    bootstrap_path = state_root / BOOTSTRAP_PATH.name
    status_path = state_root / STATUS_PATH.name
    lock_path = state_root / LOCK_PATH.name

    lock_fd = _acquire_lock(lock_path)
    if lock_fd is None:
        current = _read_json(status_path) or {}
        return {
            "ok": False,
            "status": "ALREADY_RUNNING",
            "coalesced": True,
            "readable_while_refresh": store_path.is_file(),
            "generated_at": current.get("generated_at"),
            "refresh_mode": current.get("refresh_mode"),
            "current_status": current.get("status"),
            "store_path": str(store_path),
            "query_index_path": str(query_index_path),
            "bootstrap_path": str(bootstrap_path),
            "path": str(lock_path),
        }
    try:
        os.write(lock_fd, f"{os.getpid()}\n".encode("ascii"))
        previous = None if rebuild else _read_json(store_path)
        previous_timeline = previous.get("timeline") if isinstance(previous, dict) and isinstance(previous.get("timeline"), dict) else None
        incremental = bool(previous_timeline and isinstance(previous_timeline.get("events"), list))
        refresh_mode = "INCREMENTAL" if incremental else "BACKFILL"
        previous_event_rows = []
        if previous_timeline:
            previous_event_rows.extend(previous_timeline.get("events", []) or [])
            previous_event_rows.extend(previous_timeline.get("historical_evidence_events", []) or [])
        previous_events = [
            dict(event) for event in previous_event_rows
            if isinstance(event, dict) and event.get("source_type") != "VAULT_MEMORY"
        ]

        source_names = ("repos", "workers", "artifacts", "local_artifacts", "library_artifacts", "machine", "github", "mcp", "mcp_history", "runner_logs", "coordinator")
        source_since = {
            name: _materialized_source_since(previous if incremental else None, name, horizon_since=horizon_since)
            for name in source_names
        }

        specs = discover_repo_specs(vault_root=root)
        project_to_slug, _ = _repo_maps(specs)
        entries = load_bank(root / "memory" / "memory-bank.jsonl")

        # One-time bounded self-heal for materialized Git rows created before commit
        # bodies/changed paths were indexed. Re-read only affected repo streams inside
        # the existing horizon, then preserve prior graph enrichment such as patch-id.
        legacy_repo_projects = {
            str(event.get("project") or "")
            for event in previous_events
            if event.get("source_type") == "GIT_COMMIT"
            and ("body" not in event or "changed_paths" not in event)
            and str(event.get("project") or "")
        }
        legacy_repo_repair_delta: list[dict[str, Any]] = []
        if incremental and legacy_repo_projects:
            repair_specs = [spec for spec in specs if spec.project in legacy_repo_projects]
            repair_report = collect_repo_history(
                repair_specs, limit_per_repo=repo_events_per_repo, since=horizon_since
            )
            previous_by_id = {str(event.get("id") or ""): event for event in previous_events}
            for event in repair_report.get("events") or []:
                repaired = dict(event)
                prior = previous_by_id.get(str(repaired.get("id") or ""), {})
                for key in ("branch_refs", "patch_id"):
                    if prior.get(key) not in (None, "", [], {}):
                        repaired[key] = prior[key]
                legacy_repo_repair_delta.append(repaired)

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
        library_delta, library_coverage = library_artifact_events(root, since=source_since["library_artifacts"])
        machine_delta, machine_coverage = machine_observation_events(since=source_since["machine"])

        github_delta: list[dict[str, Any]] = []
        github_coverage: dict[str, Any] = {"available": False, "skipped": True}
        if include_github:
            github_limit = min(github_events_per_kind, DEFAULT_DELTA_GITHUB_EVENTS_PER_KIND) if incremental else github_events_per_kind
            github_delta, github_coverage = github_events(
                specs,
                since=source_since["github"],
                limit_per_kind=github_limit,
                snapshot_now=now,
            )

        mcp_delta, mcp_coverage = mcp_events(
            since=source_since["mcp"], root=root, project_to_slug=project_to_slug
        )
        mcp_history_delta, mcp_history_coverage = mcp_replacement_events(since=source_since["mcp_history"])
        runner_delta, runner_coverage = runner_log_events(
            since=source_since["runner_logs"], limit=runner_events_limit
        )
        coordinator_delta, coordinator_coverage = coordinator_events(
            since=source_since["coordinator"], snapshot_now=now
        )
        supplemental_delta = [
            *github_delta,
            *mcp_delta,
            *mcp_history_delta,
            *runner_delta,
            *coordinator_delta,
            *local_delta,
            *library_delta,
            *machine_delta,
        ]
        all_delta = [*legacy_repo_repair_delta, *repo_delta, *worker_delta, *artifact_delta, *supplemental_delta]

        merged_external = _merge_materialized_events(
            previous_events, all_delta, since=horizon_since
        )
        active_external = [event for event in merged_external if _event_within_horizon(event, horizon_since)]
        historical_evidence_events = [event for event in merged_external if event.get("retain_history")]
        historical_evidence_events.sort(
            key=lambda event: (_dt(event.get("event_at")) or datetime.min.replace(tzinfo=timezone.utc), str(event.get("id") or "")),
            reverse=True,
        )
        historical_evidence_events = historical_evidence_events[:DEFAULT_HISTORICAL_EVIDENCE_EVENTS]
        repo_events = [event for event in active_external if event.get("source_type") == "GIT_COMMIT"]
        worker_events = [event for event in active_external if event.get("source_type") == "WORKER_REPORT"]
        worker_archive = build_worker_archive_summary(worker_events, now=now, horizon_days=days)
        artifact_events = [event for event in active_external if event.get("source_type") == "TRACKED_ARTIFACT"]
        supplemental = [
            event for event in active_external
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
            "library_artifacts": library_coverage,
            "machine": machine_coverage,
            "github": github_coverage,
            "mcp": mcp_coverage,
            "mcp_history": mcp_history_coverage,
            "runner_logs": runner_coverage,
            "coordinator": coordinator_coverage,
        }
        saturated_sources = [
            name for name in source_names
            if _coverage_saturated(name, delta_coverage.get(name, {}))
        ]
        skipped_sources = [
            name for name in source_names
            if isinstance(delta_coverage.get(name), dict) and delta_coverage[name].get("skipped") is True
        ]

        previous_watermarks = previous.get("source_watermarks") if isinstance(previous, dict) and isinstance(previous.get("source_watermarks"), dict) else {}
        source_watermarks: dict[str, str] = {}
        for name in source_names:
            if name in skipped_sources or (refresh_mode == "INCREMENTAL" and name in saturated_sources):
                source_watermarks[name] = str(previous_watermarks.get(name) or (previous or {}).get("generated_at") or source_since[name].isoformat())
            else:
                source_watermarks[name] = now.isoformat()

        previous_ingestion = previous.get("ingestion") if isinstance(previous, dict) and isinstance(previous.get("ingestion"), dict) else {}
        previous_backfill_incomplete = set(str(value) for value in previous_ingestion.get("backfill_incomplete_sources", []) if str(value).strip())
        backfill_incomplete_sources = (
            sorted(set(saturated_sources) | set(skipped_sources))
            if refresh_mode == "BACKFILL"
            else sorted(previous_backfill_incomplete | set(skipped_sources))
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
                "legacy_repo_events_reenriched": len(legacy_repo_repair_delta),
                "retained_previous_external_events": len(previous_events),
                "merged_external_events": len(merged_external),
                "saturated_sources": saturated_sources,
                "skipped_sources": skipped_sources,
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
        _enrich_memory_search_text(timeline.get("events", []), entries)
        timeline["historical_evidence_events"] = historical_evidence_events
        timeline["worker_archive"] = worker_archive
        continuity_graph = build_continuity_graph(timeline["events"])
        timeline["continuity_graph"] = continuity_graph
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
            "skipped_sources": skipped_sources,
            "backfill_incomplete_sources": backfill_incomplete_sources,
            "retry_sources": retry_sources,
            "historical_evidence_events": len(historical_evidence_events),
            "timeline_truncated": bool(timeline.get("truncated")),
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
                "skipped_sources": skipped_sources,
                "backfill_incomplete_sources": backfill_incomplete_sources,
                "retry_sources": retry_sources,
            },
            "timeline": timeline,
        }
        _atomic_json(store_path, store_payload)

        # Compact multi-reader index: canonical JSON remains the complete source. The
        # sidecar stores only token postings plus normalized lineage anchors so distinct
        # queries can narrow/rank the full rich events without repeating work across agents.
        query_events: dict[str, dict[str, Any]] = {}
        for raw in [*(timeline.get("events", []) or []), *(timeline.get("historical_evidence_events", []) or [])]:
            if isinstance(raw, dict) and raw.get("id"):
                query_events[str(raw["id"])] = raw
        query_ids = list(query_events)
        postings: dict[str, list[int]] = defaultdict(list)
        weight_codes: dict[str, bytearray] = defaultdict(bytearray)
        query_anchors: list[list[str]] = []
        for index, event in enumerate(query_events.values()):
            best_weight_by_token: dict[str, float] = {}
            for weight, tokens in _event_query_fields(event):
                for token in tokens:
                    if weight > best_weight_by_token.get(token, 0.0):
                        best_weight_by_token[token] = weight
            for token, weight in best_weight_by_token.items():
                postings[token].append(index)
                weight_codes[token].append(_QUERY_WEIGHT_TO_CODE[weight])
            query_anchors.append(_event_anchors(event))
        _atomic_pickle(query_index_path, {
            "schema": QUERY_INDEX_SCHEMA,
            "generated_at": str(store_payload.get("generated_at") or ""),
            "ids": query_ids,
            "postings": dict(postings),
            "weight_codes": {token: bytes(codes) for token, codes in weight_codes.items()},
            "anchors": query_anchors,
        })

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
            "timeline_truncated": bool(timeline.get("truncated")),
            "coverage_status": "HISTORICAL_INCOMPLETE" if (backfill_incomplete_sources or timeline.get("truncated")) else ("COMPLETE_MATERIALIZED_HISTORY" if days is None else "COMPLETE_WITHIN_MATERIALIZED_HORIZON"),
            "absence_semantics": "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE" if (backfill_incomplete_sources or timeline.get("truncated")) else ("NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HISTORY_AND_ENABLED_SOURCES_ONLY" if days is None else "NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HORIZON_AND_ENABLED_SOURCES_ONLY"),
            "live_truth_required": True,
            "historical_evidence_events": len(historical_evidence_events),
            "work_graph": {
                "semantics": "IMPLEMENTATION_EQUIVALENCE_NOT_INCIDENT_IDENTITY",
                **graph["summary"],
            },
        }
        compact = _fit_memory_overview_budget(compact)
        _atomic_json(bootstrap_path, {
            "schema": BOOTSTRAP_SCHEMA,
            "generated_at": now.isoformat(),
            "overview": compact,
            "workers": _bootstrap_worker_projection(worker_archive),
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
            "continuity_graph": continuity_graph["summary"],
            "worker_archive": worker_archive["archive_sample"],
            "work_graph": graph["summary"],
            "store_path": str(store_path),
            "query_index_path": str(query_index_path),
            "bootstrap_path": str(bootstrap_path),
            "store_bytes": store_path.stat().st_size,
            "query_index_bytes": query_index_path.stat().st_size,
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
    timeline_truncated = bool(timeline.get("truncated") or meta.get("timeline_truncated"))
    horizon_days = payload.get("horizon_days")
    if horizon_days is None:
        horizon_days = meta.get("horizon_days")
    complete_coverage_status = "COMPLETE_MATERIALIZED_HISTORY" if horizon_days is None else "COMPLETE_WITHIN_MATERIALIZED_HORIZON"
    coverage_status = "HISTORICAL_INCOMPLETE" if (incomplete or timeline_truncated) else complete_coverage_status
    absence_unsafe_reasons: list[str] = []
    if status != "FRESH":
        absence_unsafe_reasons.append("MATERIALIZATION_STALE")
    if incomplete:
        absence_unsafe_reasons.append("HISTORICAL_BACKFILL_INCOMPLETE")
    if timeline_truncated:
        absence_unsafe_reasons.append("MATERIALIZED_EVENT_CAP_TRUNCATED")
    if retry:
        absence_unsafe_reasons.append("DELTA_RETRY_PENDING")
    absence_semantics = (
        "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE"
        if absence_unsafe_reasons
        else ("NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HISTORY_AND_ENABLED_SOURCES_ONLY" if horizon_days is None else "NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HORIZON_AND_ENABLED_SOURCES_ONLY")
    )
    return {
        "status": status,
        "as_of": generated_at or None,
        "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
        "stale_after_seconds": round(stale_after_seconds, 1),
        "refresh_minutes": refresh_minutes,
        "refresh_mode": meta.get("refresh_mode") or ingestion.get("mode"),
        "horizon_days": horizon_days,
        "read_mode": "MATERIALIZED_ONLY",
        "coverage_status": coverage_status,
        "backfill_incomplete_sources": incomplete,
        "saturated_sources": saturated,
        "retry_sources": retry,
        "timeline_truncated": timeline_truncated,
        "absence_semantics": absence_semantics,
        "absence_unsafe_reasons": absence_unsafe_reasons,
        "live_truth_required": True,
    }


def _simple_query_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


@lru_cache(maxsize=256)
def _query_concepts(query: str) -> tuple[frozenset[str], ...]:
    concepts: list[frozenset[str]] = []
    seen: set[frozenset[str]] = set()
    for token in _QUERY_TOKEN_RE.findall(query.casefold()):
        if token in _QUERY_STOP_WORDS:
            continue
        concept = _QUERY_CONCEPT_BY_TOKEN.get(token, frozenset({_simple_query_token(token)}))
        if concept not in seen:
            seen.add(concept)
            concepts.append(concept)
    return tuple(concepts)


def _query_tokens(value: Any) -> set[str]:
    return set(_QUERY_TOKEN_RE.findall(str(value or "").casefold()))


def _event_query_fields(event: dict[str, Any]) -> list[tuple[float, set[str]]]:
    cached = event.get("_query_fields_cache")
    if isinstance(cached, list) and len(cached) == 5:
        try:
            return [(float(weight), set(tokens)) for weight, tokens in cached]
        except (TypeError, ValueError):
            pass
    metadata = " ".join([
        " ".join(str(value) for value in event.get("tags", []) or []),
        str(event.get("scope") or ""),
        str(event.get("semantic_category") or ""),
        str(event.get("primary_domain") or ""),
        str(event.get("project") or ""),
        " ".join(str(value) for value in event.get("projects", []) or []),
        str(event.get("worker") or ""),
        str(event.get("artifact_type") or ""),
    ])
    links = " ".join([
        " ".join(str(value) for value in event.get("refs", []) or []),
        " ".join(str(value) for value in event.get("anchors", []) or []),
        " ".join(str(value) for value in event.get("evidence", []) or []),
    ])
    rich_search = " ".join([
        str(event.get("_search_text") or ""),
        str(event.get("body") or ""),
        " ".join(str(value) for value in event.get("changed_paths", []) or []),
        str(event.get("findings") or ""),
        str(event.get("validation") or ""),
        str(event.get("outcome") or ""),
    ])
    return [
        (4.0, _query_tokens(event.get("title"))),
        (2.0, _query_tokens(event.get("summary"))),
        (1.2, _query_tokens(rich_search)),
        (2.2, _query_tokens(metadata)),
        (0.7, _query_tokens(links)),
    ]


def _event_matches_identity_query(event: dict[str, Any], query: str) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return True
    hay = " ".join([
        str(event.get("title") or ""),
        str(event.get("summary") or ""),
        str(event.get("project") or ""),
        str(event.get("worker") or ""),
        " ".join(str(value) for value in event.get("refs", []) or []),
        " ".join(str(value) for value in event.get("anchors", []) or []),
        str(event.get("thread_id") or ""),
        " ".join(str(value) for value in event.get("case_anchors", []) or []),
    ]).casefold()
    return tokens <= set(_QUERY_TOKEN_RE.findall(hay))


def _minimum_query_matches(concept_count: int) -> int:
    """Require more independent concepts as a natural-language query gets richer."""
    if concept_count <= 1:
        return 1
    if concept_count <= 4:
        return 2
    if concept_count <= 7:
        return 3
    return 4


def _is_causal_correction_event(event: dict[str, Any]) -> bool:
    hay = " ".join([
        str(event.get("title") or ""),
        str(event.get("summary") or ""),
        str(event.get("_search_text") or ""),
    ]).casefold()
    return any(phrase in hay for phrase in _CAUSAL_CORRECTION_PHRASES)


def _event_matches_query(event: dict[str, Any], query: str) -> bool:
    concepts = _query_concepts(query)
    if not concepts:
        return True
    fields = _event_query_fields(event)
    merged = set().union(*(tokens for _, tokens in fields))
    matched = sum(1 for concept in concepts if merged & concept)
    return matched >= (2 if len(concepts) >= 2 else 1)


def _rank_query_events(events: list[dict[str, Any]], query: str, *, corpus_size_override: int | None = None) -> list[tuple[float, dict[str, Any]]]:
    concepts = _query_concepts(query)
    if not concepts:
        return [(1.0, event) for event in events]
    fields_by_id = [_event_query_fields(event) for event in events]
    document_frequency = [0] * len(concepts)
    for fields in fields_by_id:
        merged = set().union(*(tokens for _, tokens in fields))
        for index, concept in enumerate(concepts):
            if merged & concept:
                document_frequency[index] += 1
    corpus_size = max(1, int(corpus_size_override) if corpus_size_override is not None else len(events))
    minimum_matches = _minimum_query_matches(len(concepts))
    causal_query = bool(_query_tokens(query) & _CAUSAL_QUERY_TOKENS)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for event, fields in zip(events, fields_by_id):
        matched = 0
        score = 0.0
        for index, concept in enumerate(concepts):
            best_weight = max((weight for weight, tokens in fields if tokens & concept), default=0.0)
            if not best_weight:
                continue
            matched += 1
            rarity = math.log(1.0 + (corpus_size + 1.0) / (document_frequency[index] + 1.0))
            score += best_weight * rarity
        causal_correction = causal_query and _is_causal_correction_event(event)
        required_matches = min(minimum_matches, 3) if causal_correction else minimum_matches
        if matched < required_matches:
            continue
        coverage = matched / min(len(concepts), 6)
        score *= 0.75 + (1.35 * coverage)
        score *= _QUERY_SOURCE_PRIOR.get(str(event.get("source_type") or ""), 1.0)
        if causal_correction:
            score *= 2.25
        ranked.append((score, event))
    ranked.sort(
        key=lambda item: (item[0], str(item[1].get("event_at") or ""), str(item[1].get("id") or "")),
        reverse=True,
    )
    return ranked


def _rank_query_events_indexed(
    events: list[dict[str, Any]],
    query: str,
    index: dict[str, Any],
    *,
    corpus_size_override: int | None = None,
) -> list[tuple[float, dict[str, Any]]] | None:
    concepts = _query_concepts(query)
    if not concepts:
        return [(1.0, event) for event in events]
    ids = index.get("ids") if isinstance(index.get("ids"), list) else []
    postings = index.get("postings") if isinstance(index.get("postings"), dict) else {}
    weight_codes = index.get("weight_codes") if isinstance(index.get("weight_codes"), dict) else {}
    position_by_id = {str(event_id): position for position, event_id in enumerate(ids)}
    allowed_positions = {
        position_by_id[event_id]
        for event in events
        if (event_id := str(event.get("id") or "")) in position_by_id
    }
    event_by_position = {position_by_id[str(event.get("id") or "")]: event for event in events if str(event.get("id") or "") in position_by_id}
    if not allowed_positions:
        return []

    best_weights: list[dict[int, float]] = []
    document_frequency: list[int] = []
    for concept in concepts:
        best: dict[int, float] = {}
        for token in concept:
            rows = postings.get(token)
            codes = weight_codes.get(token)
            if not isinstance(rows, list) or not isinstance(codes, (bytes, bytearray)) or len(rows) != len(codes):
                continue
            for position, code in zip(rows, codes):
                if position not in allowed_positions:
                    continue
                weight = _QUERY_CODE_TO_WEIGHT.get(int(code), 0.0)
                if weight > best.get(position, 0.0):
                    best[position] = weight
        best_weights.append(best)
        document_frequency.append(len(best))

    corpus_size = max(1, int(corpus_size_override) if corpus_size_override is not None else len(events))
    minimum_matches = _minimum_query_matches(len(concepts))
    causal_query = bool(_query_tokens(query) & _CAUSAL_QUERY_TOKENS)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for position, event in event_by_position.items():
        matched = 0
        score = 0.0
        for concept_index, best in enumerate(best_weights):
            weight = best.get(position, 0.0)
            if not weight:
                continue
            matched += 1
            rarity = math.log(1.0 + (corpus_size + 1.0) / (document_frequency[concept_index] + 1.0))
            score += weight * rarity
        causal_correction = causal_query and _is_causal_correction_event(event)
        required_matches = min(minimum_matches, 3) if causal_correction else minimum_matches
        if matched < required_matches:
            continue
        coverage = matched / min(len(concepts), 6)
        score *= 0.75 + (1.35 * coverage)
        score *= _QUERY_SOURCE_PRIOR.get(str(event.get("source_type") or ""), 1.0)
        if causal_correction:
            score *= 2.25
        ranked.append((score, event))
    ranked.sort(
        key=lambda item: (item[0], str(item[1].get("event_at") or ""), str(item[1].get("id") or "")),
        reverse=True,
    )
    return ranked


def _memory_search_text(entry: dict[str, Any]) -> str:
    values = [
        str(entry.get("text") or ""),
        " ".join(str(value) for value in entry.get("source_messages", []) or []),
        str(entry.get("interpretation") or ""),
        str(entry.get("confidence_reason") or ""),
    ]
    return " ".join(value for value in values if value)[:6000]


def _enrich_memory_search_text(events: Iterable[dict[str, Any]], entries: Iterable[dict[str, Any]]) -> None:
    by_id = {str(entry.get("id") or ""): entry for entry in entries if isinstance(entry, dict) and entry.get("id")}
    for event in events:
        if event.get("source_type") != "VAULT_MEMORY":
            continue
        source = by_id.get(str(event.get("id") or ""))
        if source:
            event["_search_text"] = _memory_search_text(source)


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
        "sha", "short_sha", "patch_id", "branch_refs", "decorations", "repo_path", "repo_state", "changed_paths",
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
    for key, limit in (("title", 260), ("summary", 480), ("body", 600), ("outcome", 240), ("remaining_gate", 240), ("findings", 300), ("stop_reason", 200)):
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


def _query_index_candidate_ids(index: dict[str, Any], query: str) -> set[str] | None:
    concepts = _query_concepts(query)
    if not concepts:
        return None
    ids = index.get("ids") if isinstance(index.get("ids"), list) else []
    postings = index.get("postings") if isinstance(index.get("postings"), dict) else {}
    positions: set[int] = set()
    for concept in concepts:
        for token in concept:
            rows = postings.get(token)
            if isinstance(rows, list):
                positions.update(int(value) for value in rows if isinstance(value, int) and 0 <= value < len(ids))
    return {str(ids[position]) for position in positions}


def _apply_query_index_anchors(events: Iterable[dict[str, Any]], index: dict[str, Any]) -> None:
    ids = index.get("ids") if isinstance(index.get("ids"), list) else []
    anchors = index.get("anchors") if isinstance(index.get("anchors"), list) else []
    by_id = {str(event_id): position for position, event_id in enumerate(ids)}
    for event in events:
        position = by_id.get(str(event.get("id") or ""))
        if position is None or position >= len(anchors) or not isinstance(anchors[position], list):
            continue
        event["_all_anchors_cache"] = list(anchors[position])


def _query_cache_key(generated_at: str, *, query: str, view: str, project: str | None, thread: str | None, days: int | None, limit: int, include_workers: bool) -> str:
    payload = {
        "generated_at": generated_at,
        "query": " ".join(query.split()).casefold(),
        "view": view,
        "project": project.casefold() if project else None,
        "thread": thread,
        "days": days,
        "limit": int(limit),
        "include_workers": bool(include_workers),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_query_result_cache(root: Path, key: str) -> tuple[dict[str, Any] | None, float | None]:
    path = root / ".state" / "timeline" / QUERY_CACHE_ROOT.name / f"{key}.json"
    try:
        age = max(0.0, time.time() - path.stat().st_mtime)
        if age > QUERY_RESULT_CACHE_SECONDS:
            return None, age
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return (payload, age) if isinstance(payload, dict) else (None, age)
    except (OSError, json.JSONDecodeError):
        return None, None


def _write_query_result_cache(root: Path, key: str, result: dict[str, Any]) -> None:
    cache_root = root / ".state" / "timeline" / QUERY_CACHE_ROOT.name
    path = cache_root / f"{key}.json"
    try:
        _atomic_json(path, result)
        files = sorted(cache_root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        for stale in files[QUERY_RESULT_CACHE_MAX_FILES:]:
            stale.unlink(missing_ok=True)
    except OSError:
        pass


def _refresh_cached_query_result(result: dict[str, Any], cache_age: float | None) -> dict[str, Any]:
    refreshed = dict(result)
    materialized = dict(refreshed.get("materialized") or {})
    as_of = _dt(materialized.get("as_of"))
    if as_of is not None:
        now = datetime.now().astimezone()
        current_age = max(0.0, (now - as_of.astimezone(now.tzinfo)).total_seconds())
        stale_after = float(materialized.get("stale_after_seconds") or DEFAULT_REFRESH_MINUTES * 180.0)
        materialized["age_seconds"] = round(current_age, 1)
        stale = current_age > stale_after
        materialized["status"] = "STALE" if stale else "FRESH"
        reasons = {str(value) for value in materialized.get("absence_unsafe_reasons", []) if str(value)}
        if stale:
            reasons.add("MATERIALIZATION_STALE")
        else:
            reasons.discard("MATERIALIZATION_STALE")
        materialized["absence_unsafe_reasons"] = sorted(reasons)
        complete_absence_semantics = (
            "NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HISTORY_AND_ENABLED_SOURCES_ONLY"
            if materialized.get("horizon_days") is None
            else "NO_MATCH_MEANS_NO_MATCH_IN_THE_MATERIALIZED_HORIZON_AND_ENABLED_SOURCES_ONLY"
        )
        materialized["absence_semantics"] = (
            "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE" if reasons else complete_absence_semantics
        )
        refreshed["materialized"] = materialized
    refreshed["query_cache"] = {
        "used": True,
        "age_seconds": round(cache_age or 0.0, 3),
        "max_age_seconds": QUERY_RESULT_CACHE_SECONDS,
    }
    return refreshed



_LESSON_GENERIC_TOKENS = {
    "after", "again", "already", "before", "branch", "commit", "current", "exact", "failed", "failure",
    "file", "files", "fixed", "issue", "later", "main", "only", "path", "paths", "project", "report",
    "accepted", "correctly", "coverage", "result", "same", "source", "still", "test", "tests", "through", "tool", "using", "verified", "worker",
}


_LESSON_TRAILER_RE = re.compile(
    r"(?i)^\s*(?:co-authored-by|signed-off-by|reviewed-by|acked-by|tested-by|change-id)\s*:"
)
_LESSON_CONCEPT_GROUPS = {
    "deform": {"deform", "deformed", "deforming", "deformation", "deformations"},
    "skin": {"skin", "skins", "skinned", "skinning", "binding", "bindings", "bind", "bound"},
    "weight": {"weight", "weights", "weighted", "weighting"},
    "rig": {"rig", "rigs", "rigged", "rigger", "rigging", "armature", "armatures", "skeleton", "skeletons"},
    "export": {"export", "exports", "exported", "exporter", "exporting"},
    "animation": {"animate", "animated", "animation", "animations", "clip", "clips", "keyframe", "keyframes", "playback", "replay", "replayed"},
    "proof": {"proof", "prove", "proved", "proven", "verify", "verified", "verifier", "verification", "validate", "validated", "validation", "gate", "gated"},
    "surface": {"surface", "surfaces", "geodesic", "adjacency", "weld", "welded", "welding"},
    "limb": {"limb", "limbs", "leg", "legs", "arm", "arms", "wing", "wings", "tail", "tails"},
}
_LESSON_CONCEPT_BY_TOKEN = {
    token: concept for concept, tokens in _LESSON_CONCEPT_GROUPS.items() for token in tokens
}
_LESSON_CORRECTIVE_TOKENS = {
    "broken", "cause", "caused", "correct", "corrected", "disproved", "failed", "failing", "failure", "false",
    "fix", "fixed", "instead", "invalid", "lost", "missing", "prevent", "prevented", "rejected", "repair", "repaired",
    "wrong", "zero", "unreachable", "drift", "inverted", "shear", "shears",
}
_LESSON_PROCESS_TOKENS = {
    "authorship", "batch", "batches", "branch", "branches", "chain", "chains", "commit", "committed", "job", "jobs",
    "queue", "queued", "session", "sessions", "scaffold", "supervisor", "supervisors", "survive", "survives",
    "uncommitted", "untracked", "usage", "wait", "waiting", "workflow", "worktree", "worktrees",
}


def _clean_lesson_body(value: Any) -> str:
    """Remove commit trailers/metadata that cannot be a technical lesson by themselves."""
    lines = []
    for raw in str(value or "").splitlines():
        line = raw.strip()
        if not line or _LESSON_TRAILER_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _lesson_concepts(value: Any) -> set[str]:
    return {
        concept
        for token in _query_tokens(value)
        if (concept := _LESSON_CONCEPT_BY_TOKEN.get(token)) is not None
    }


def _lesson_candidate_text(event: dict[str, Any]) -> str:
    source = str(event.get("source_type") or "")
    body = _clean_lesson_body(event.get("body"))
    if source == "GIT_COMMIT":
        return body
    if source == "WORKER_REPORT":
        return " ".join(str(event.get(field) or "") for field in ("findings", "validation", "summary", "outcome")).strip()
    if source == "VAULT_MEMORY":
        return " ".join(str(event.get(field) or "") for field in ("text", "conclusion", "summary", "body")).strip()
    return " ".join([
        str(event.get("findings") or ""),
        str(event.get("validation") or ""),
        body,
        str(event.get("summary") or ""),
    ]).strip()


def _lesson_candidate_quality(event: dict[str, Any], text: str) -> float:
    """Reject metadata-only candidates and favor corrective technical evidence over process narration."""
    tokens = _query_tokens(text)
    content = {
        token for token in tokens
        if len(token) >= 3 and token not in _QUERY_STOP_WORDS and token not in _LESSON_GENERIC_TOKENS
    }
    if len(content) < 6:
        return 0.0
    corrective = len(tokens & _LESSON_CORRECTIVE_TOKENS)
    process = len(tokens & _LESSON_PROCESS_TOKENS)
    quality = 1.0 + min(0.55, len(content) / 80.0) + min(1.0, corrective * 0.16) - min(1.15, process * 0.20)
    if str(event.get("source_type") or "") == "GIT_COMMIT" and corrective >= 2:
        quality += 0.20
    if process >= 3 and process > corrective:
        quality *= 0.35
    return max(0.2, quality)


def _lesson_text(event: dict[str, Any]) -> str:
    """Prefer technical evidence fields over identity-heavy report titles when expanding a task query."""
    technical = " ".join([
        str(event.get("findings") or ""),
        str(event.get("validation") or ""),
        _clean_lesson_body(event.get("body")),
        str(event.get("scope") or ""),
    ]).strip()
    if technical:
        return technical
    return " ".join([
        str(event.get("summary") or ""),
        str(event.get("outcome") or ""),
        str(event.get("title") or ""),
    ])


def _lesson_packet(
    query: str,
    *,
    selected: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    query_index: dict[str, Any] | None,
    limit: int = 6,
) -> dict[str, Any]:
    """Build a bounded historical-prior packet from the existing query corpus only."""
    packet_limit = min(8, max(3, int(limit)))
    base = {
        "authority": "DERIVED_HISTORICAL_PRIORS_ONLY",
        "validation": "SLICE1_RETRIEVAL_ONLY_NOT_VALIDATED",
        "live_truth_required": True,
        "nonblocking": True,
        "query": " ".join(query.split()),
        "items": [],
    }
    if not query:
        return {**base, "status": "NOT_REQUESTED"}
    seeds = [event for event in selected[:4] if isinstance(event, dict)]
    if not seeds:
        return {**base, "status": "NO_SEED_MATCH"}

    query_tokens = _query_tokens(query)
    seed_counts: Counter[str] = Counter()
    for event in seeds:
        seed_counts.update(_query_tokens(_lesson_text(event)))

    postings = query_index.get("postings") if isinstance(query_index, dict) and isinstance(query_index.get("postings"), dict) else {}
    corpus_size = max(1, len(candidates))
    expansion_ranked: list[tuple[float, str, int]] = []
    for token, count in seed_counts.items():
        if (
            len(token) < 4 or token.isdigit() or token in query_tokens or token in _QUERY_STOP_WORDS
            or token in _LESSON_GENERIC_TOKENS
        ):
            continue
        rows = postings.get(token)
        if isinstance(rows, list):
            df = len(rows)
        else:
            df = sum(1 for event in candidates if token in set().union(*(tokens for _, tokens in _event_query_fields(event))))
        # A bridge term must reach beyond the seed and must not be generic across the corpus.
        if df < 2 or df > max(40, int(corpus_size * 0.18)):
            continue
        score = float(count) * math.log(1.0 + (corpus_size + 1.0) / (df + 1.0))
        expansion_ranked.append((score, token, df))
    expansion_ranked.sort(key=lambda item: (item[0], -item[2], item[1]), reverse=True)
    expansion = [token for _, token, _ in expansion_ranked[:16]]
    expansion_weights = {token: score for score, token, _ in expansion_ranked[:16]}
    if not expansion:
        return {
            **base,
            "status": "NO_BRIDGE_TERMS",
            "seed_event_ids": [str(event.get("id") or "") for event in seeds if event.get("id")],
        }

    concepts = _query_concepts(query)
    query_lesson_concepts = _lesson_concepts(query)
    seed_lesson_concepts: set[str] = set()
    for event in seeds:
        seed_lesson_concepts.update(_lesson_concepts(_lesson_text(event)))
    seed_ids = {str(event.get("id") or "") for event in seeds}
    ranked: list[tuple[float, dict[str, Any], list[str]]] = []
    lesson_sources = {"GIT_COMMIT", "WORKER_REPORT", "VAULT_MEMORY", "TRACKED_ARTIFACT", "LOCAL_ARTIFACT", "LIBRARY_ARTIFACT"}
    for event in candidates:
        source = str(event.get("source_type") or "")
        if source not in lesson_sources:
            continue
        event_id = str(event.get("id") or "")
        if event_id in seed_ids:
            continue
        candidate_text = _lesson_candidate_text(event)
        quality = _lesson_candidate_quality(event, candidate_text)
        if quality <= 0.0:
            continue
        merged = set().union(*(tokens for _, tokens in _event_query_fields(event)))
        overlaps = [token for token in expansion if token in merged]
        query_hits = sum(1 for concept in concepts if merged & concept)
        candidate_lesson_concepts = _lesson_concepts(candidate_text)
        direct_lesson_hits = len(query_lesson_concepts & candidate_lesson_concepts)
        bridge_lesson_hits = len(seed_lesson_concepts & candidate_lesson_concepts)
        if query_hits < 1 and direct_lesson_hits < 1 and bridge_lesson_hits < 3:
            continue
        if query_hits < 1 and direct_lesson_hits < 1 and candidate_lesson_concepts == {"proof"}:
            continue
        process_hits = len(_query_tokens(candidate_text) & _LESSON_PROCESS_TOKENS)
        if query_hits < 1 and process_hits >= 3:
            continue
        if query_hits < 1 and direct_lesson_hits < 1 and len(overlaps) < 3 and bridge_lesson_hits < 2:
            continue
        corrective_hits = len(_query_tokens(candidate_text) & _LESSON_CORRECTIVE_TOKENS)
        corrective_weight = 3.0 if source == "GIT_COMMIT" else 0.75
        score = (
            sum(expansion_weights.get(token, 0.0) for token in overlaps)
            + (2.0 * query_hits)
            + (2.5 * direct_lesson_hits)
            + (1.25 * bridge_lesson_hits)
            + (corrective_weight * min(4, corrective_hits))
        )
        score *= {
            "GIT_COMMIT": 1.35,
            "TRACKED_ARTIFACT": 1.12,
            "LOCAL_ARTIFACT": 1.0,
            "WORKER_REPORT": 0.78,
            "VAULT_MEMORY": 0.72,
        }.get(source, 0.9)
        if event.get("body"):
            score *= 1.12
        score *= quality
        ranked.append((score, event, overlaps))
    ranked.sort(
        key=lambda item: (item[0], str(item[1].get("event_at") or ""), str(item[1].get("id") or "")),
        reverse=True,
    )

    # Prefer cross-project transfer when it exists, but never discard same-project history:
    # a soft first pass defers only the fifth+ item from one project, then fills any remaining slots.
    per_project_soft_cap = max(2, packet_limit - 3)
    primary: list[tuple[float, dict[str, Any], list[str]]] = []
    deferred: list[tuple[float, dict[str, Any], list[str]]] = []
    project_counts: Counter[str] = Counter()
    for row in ranked:
        project_key = str(row[1].get("project") or "").casefold()
        if project_key and project_counts[project_key] >= per_project_soft_cap:
            deferred.append(row)
            continue
        primary.append(row)
        if project_key:
            project_counts[project_key] += 1

    items: list[dict[str, Any]] = []
    seen_subjects: set[tuple[str, str]] = set()
    for score, event, overlaps in [*primary, *deferred]:
        project = str(event.get("project") or "")
        subject = _subject_key(event.get("title")) or str(event.get("title") or "").casefold()
        subject_key = (project.casefold(), subject)
        if subject and subject_key in seen_subjects:
            continue
        if subject:
            seen_subjects.add(subject_key)
        anchors = list(event.get("anchors", []) or [])
        sha = str(event.get("sha") or "").strip()
        if sha:
            anchors.insert(0, f"gitsha:{sha}")
        conclusion = (
            _clip_query_value(_clean_lesson_body(event.get("body")), 440)
            or _clip_query_value(event.get("findings"), 440)
            or _clip_query_value(event.get("summary"), 440)
            or _clip_query_value(event.get("outcome"), 440)
            or _clip_query_value(event.get("title"), 440)
        )
        item = {
            "source_event_id": event.get("id"),
            "source_type": event.get("source_type"),
            "project": event.get("project"),
            "event_at": event.get("event_at"),
            "title": _clip_query_value(event.get("title"), 220),
            "conclusion": conclusion,
            "relevance_terms": overlaps[:6],
            "evidence_anchors": anchors[:6],
        }
        changed_paths = [str(value) for value in event.get("changed_paths", []) or [] if str(value).strip()]
        if changed_paths:
            item["changed_paths"] = changed_paths[:6]
        items.append({key: value for key, value in item.items() if value not in (None, "", [], {})})
        if len(items) >= packet_limit:
            break

    return {
        **base,
        "status": "READY" if items else "NO_RELATED_PRIORS",
        "seed_event_ids": [str(event.get("id") or "") for event in seeds if event.get("id")],
        "expansion_terms": expansion[:12],
        "items": items,
    }


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
    store_generation = _store_generation_token(root)
    cache_key = _query_cache_key(
        store_generation, query=query, view=view, project=project, thread=thread, days=days, limit=limit, include_workers=include_workers
    ) if store_generation else None
    if cache_key:
        cached_result, cache_age = _read_query_result_cache(root, cache_key)
        if cached_result is not None:
            return _refresh_cached_query_result(cached_result, cache_age)

    payload = load_materialized(root=root)
    if not payload:
        return None
    timeline = payload.get("timeline")
    if not isinstance(timeline, dict):
        return None
    query_index = _read_query_index(
        root / ".state" / "timeline" / QUERY_INDEX_PATH.name,
        generated_at=str(payload.get("generated_at") or ""),
    )
    event_rows = [*(timeline.get("events", []) or []), *(timeline.get("historical_evidence_events", []) or [])]
    by_id: dict[str, dict[str, Any]] = {}
    for raw in event_rows:
        if not isinstance(raw, dict):
            continue
        event_id = str(raw.get("id") or "").strip()
        if event_id:
            by_id[event_id] = dict(raw)
    events = list(by_id.values())
    now = datetime.now().astimezone()
    since = now - timedelta(days=days) if days is not None else None
    candidates: list[dict[str, Any]] = []
    for event in events:
        if not include_workers and event.get("source_type") == "WORKER_REPORT":
            continue
        if project:
            project_key = project.casefold()
            event_projects = {str(event.get("project") or "").casefold()}
            event_projects.update(str(value).casefold() for value in event.get("projects", []) or [])
            event_projects.discard("")
            if project_key not in event_projects:
                continue
        if thread and str(event.get("thread_id") or "") != thread:
            continue
        stamp = _dt(event.get("event_at"))
        if since is not None and (stamp is None or stamp < since.astimezone(stamp.tzinfo)):
            continue
        if view == "errors" and not is_forensic_error_event(event):
            continue
        candidates.append(event)
    if query:
        rank_candidates = candidates
        if query_index is not None:
            indexed_ids = _query_index_candidate_ids(query_index, query)
            if indexed_ids is not None:
                rank_candidates = [event for event in candidates if str(event.get("id") or "") in indexed_ids]
        ranked_events = (
            _rank_query_events_indexed(rank_candidates, query, query_index, corpus_size_override=len(candidates))
            if query_index is not None else None
        )
        if ranked_events is None:
            ranked_events = _rank_query_events(rank_candidates, query, corpus_size_override=len(candidates))
        selected = [event for _, event in ranked_events]
    else:
        selected = sorted(
            candidates,
            key=lambda event: (str(event.get("event_at") or ""), str(event.get("id") or "")),
            reverse=True,
        )
    if query_index is not None:
        _apply_query_index_anchors(selected, query_index)
    # Graphs are stored across the entire horizon. Enforce explicit event
    # filters before topical matching so an empty filtered result cannot
    # accidentally expand back into unrelated historical work.
    event_filters = bool(project or thread or days is not None or view == "errors" or not include_workers)
    eligible_ids = {str(event.get("id") or "") for event in candidates}
    eligible_commits = {
        (str(event.get("project") or "").casefold(), str(event.get("sha") or "").casefold())
        for event in candidates if event.get("source_type") == "GIT_COMMIT" and event.get("sha")
    }
    effective_limit = min(500, max(1, int(limit)))
    graph_limit = min(6, effective_limit)
    selected_ids = {str(event.get("id") or "") for event in selected}
    selected_commits = {
        (str(event.get("project") or "").casefold(), str(event.get("sha") or "").casefold())
        for event in selected if event.get("source_type") == "GIT_COMMIT" and event.get("sha")
    }
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
            if _event_matches_identity_query(identity_probe, query):
                selected_attachment_ids.add(event_id)

    def compact_group(row: dict[str, Any]) -> dict[str, Any]:
        workers = []
        for worker in row.get("workers", []) or []:
            if not isinstance(worker, dict):
                continue
            item = {key: worker.get(key) for key in (
                "worker", "duration_minutes", "allocated_duration_minutes",
                "target_utilization_pct", "outcome", "summary", "finding_tags", "findings", "validation",
            ) if worker.get(key) not in (None, [], "")}
            for field, clip in (("outcome", 240), ("summary", 300), ("findings", 420), ("validation", 320)):
                value = str(item.get(field) or "")
                if len(value) > clip:
                    item[field] = value[: clip - 3].rstrip() + "..."
            workers.append(item)
        return {
            key: row.get(key) for key in (
                "work_id", "project", "title", "subject_key", "commit_count",
                "equivalent_commit_count", "branch_refs", "cross_branch",
                "github_anchors", "commits", "source_counts", "evidence_forms",
                "efficiency", "latest_at",
            ) if row.get(key) not in (None, [], {})
        } | ({"workers": workers} if workers else {})

    stored_continuity = timeline.get("continuity_graph") if isinstance(timeline.get("continuity_graph"), dict) else {}
    all_cases = stored_continuity.get("cases", []) if isinstance(stored_continuity.get("cases"), list) else []

    def case_matches_query(case: dict[str, Any]) -> bool:
        if not query:
            return True
        return _event_matches_identity_query({
            "title": case.get("latest_title") or "",
            "summary": " ".join(str(value) for value in case.get("traits", []) or []),
            "refs": case.get("anchors", []) or [],
            "anchors": [case.get("case_id") or ""],
            "thread_id": case.get("case_id") or "",
            "case_anchors": case.get("anchors", []) or [],
        }, query)

    matched_cases: list[dict[str, Any]] = []
    for case in all_cases:
        if not isinstance(case, dict):
            continue
        member_ids = set(str(value) for value in case.get("event_ids", []) or [])
        selected_overlap = bool(member_ids & selected_ids)
        if event_filters and not (member_ids & eligible_ids):
            continue
        if query and not selected_overlap and not case_matches_query(case):
            continue
        matched_cases.append(case)

    case_limit = min(8, effective_limit)

    def compact_case(case: dict[str, Any]) -> dict[str, Any]:
        member_ids = [str(value) for value in case.get("event_ids", []) or []]
        signal_ids = [str(value) for value in case.get("signal_event_ids", []) or []]
        result = {key: case.get(key) for key in (
            "case_id", "anchors", "severity", "traits", "observation_count", "signal_observation_count",
            "source_families", "evidence_forms", "classification_quality", "legacy_dependent_fields",
            "latest_event_at", "latest_signal_at", "latest_title", "latest_source_type",
        ) if case.get(key) not in (None, [], {})}
        result["event_ids"] = member_ids[:16]
        result["signal_event_ids"] = signal_ids[:16]
        if len(member_ids) > 16:
            result["event_ids_truncated"] = True
        if len(signal_ids) > 16:
            result["signal_event_ids_truncated"] = True
        return result

    eligible_work_ids: set[str] = set()
    matched_groups: list[dict[str, Any]] = []
    for row in all_graph_groups:
        if project and str(row.get("project") or "").casefold() != project.casefold():
            continue
        attached = set(str(value) for value in row.get("attached_event_ids", []) or [])
        commit_overlap = any(
            (str(row.get("project") or "").casefold(), str(commit.get("sha") or "").casefold())
            in eligible_commits for commit in row.get("commits", []) or []
        )
        if event_filters and not (commit_overlap or attached & eligible_ids):
            continue
        eligible_work_ids.add(str(row.get("work_id") or ""))
        selected_commit_overlap = any(
            (str(row.get("project") or "").casefold(), str(commit.get("sha") or "").casefold())
            in selected_commits for commit in row.get("commits", []) or []
        )
        if query and not selected_commit_overlap and not _event_matches_query({"title": row.get("title"), "refs": row.get("github_anchors", [])}, query) and not (attached & selected_attachment_ids):
            continue
        matched_groups.append(row)

    matched_similar: list[dict[str, Any]] = []
    for row in graph.get("similar_commit_groups", []) if isinstance(graph.get("similar_commit_groups"), list) else []:
        if project and str(row.get("project") or "").casefold() != project.casefold():
            continue
        if event_filters and str(row.get("work_id") or "") not in eligible_work_ids:
            continue
        if query and not _event_matches_query({"title": row.get("title"), "refs": row.get("branch_refs", [])}, query):
            continue
        matched_similar.append(row)

    materialized = materialized_health(payload, now=now)
    materialized["schema"] = payload.get("schema")
    lesson_packet = _lesson_packet(
        query,
        selected=selected,
        candidates=candidates,
        query_index=query_index,
        limit=min(8, max(3, effective_limit)),
    )

    result = {
        "schema_version": timeline.get("schema_version"),
        "authority": timeline.get("authority"),
        "contract": timeline.get("contract"),
        "debugging_boundary": {
            "timeline_role": "HISTORICAL_ORIENTATION_AND_LINEAGE",
            "current_diagnosis": "VERIFY_THE_OWNING_LIVE_REPO_RUNTIME_SCHEDULER_OR_COORDINATOR",
            "absence_semantics": materialized["absence_semantics"],
            "narrative_order": "CONTINUITY_CASES>WORK_GRAPH>EVIDENCE_DENSITY>CONTEXT_ONLY_CORROBORATION",
            "observation_semantics": "EVIDENCE_DENSITY_NOT_CASE_COUNT",
            "broad_github_anchor_semantics": "CONTEXT_ONLY_NEVER_CASE_IDENTITY",
            "snapshot_case_arrays": "BOUNDED_EXAMPLES_NOT_COMPLETE_GRAPH",
            "continuity_graph": ("FULL_MATERIALIZED_HISTORY_QUERYABLE" if materialized.get("horizon_days") is None else "FULL_MATERIALIZED_HORIZON_QUERYABLE"),
        },
        "materialized": materialized,
        "view": view,
        "project": project.casefold() if project else None,
        "query": " ".join(query.split()),
        "thread": thread,
        "snapshots": build_timeline_snapshots(selected, now=now) if selected else {"authority": "DERIVED_HISTORY_ONLY", "windows": []},
        "continuity_graph": {
            "semantics": stored_continuity.get("semantics") or "STRONG_ANCHOR_CASE_IDENTITY",
            "scope": "QUERY_MATCHED" if query or event_filters else "BOUNDED_OVERVIEW",
            "summary": {
                "matched_cases": len(matched_cases),
                "returned_cases": min(len(matched_cases), case_limit),
                "store_cases": len(all_cases),
            },
            "store_summary": stored_continuity.get("summary", {}),
            "cases": [compact_case(case) for case in matched_cases[:case_limit]],
        },
        "lesson_packet": lesson_packet,
        "work_graph": {
            "semantics": "IMPLEMENTATION_EQUIVALENCE_NOT_INCIDENT_IDENTITY",
            "scope": "QUERY_MATCHED" if query or event_filters else "BOUNDED_OVERVIEW",
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
        "lesson_packet": lesson_packet,
        "evidence_density": {
            "matching_observations": len(selected),
            "returned_observations": min(len(selected), effective_limit),
            "semantics": "OBSERVATION_VOLUME_IS_EVIDENCE_DENSITY_NOT_CASE_COUNT",
        },
        "matching_events": len(selected),
        "events": [_compact_query_event(event) for event in selected[:effective_limit]],
        "truncated": len(selected) > effective_limit,
    }
    result["query_cache"] = {"used": False, "age_seconds": 0.0, "max_age_seconds": QUERY_RESULT_CACHE_SECONDS}
    # Cache only when the canonical store is still the exact generation observed
    # before this query began. A refresh published mid-query makes the computed
    # result generation-ambiguous, so publishing it under the newer key would let
    # stale evidence survive the correction that just replaced it.
    effective_generation = _store_generation_token(root)
    if store_generation and effective_generation == store_generation:
        effective_key = _query_cache_key(
            store_generation, query=query, view=view, project=project, thread=thread, days=days, limit=limit, include_workers=include_workers
        )
        _write_query_result_cache(root, effective_key, result)
    return result


def _schtasks_encoding() -> str:
    return "oem" if os.name == "nt" else "utf-8"


def _emit_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=True))


def install_task(*, minutes: int = DEFAULT_REFRESH_MINUTES) -> dict[str, Any]:
    minutes = max(1, int(minutes))
    action = f'"{sys.executable}" "{Path(__file__).resolve()}" refresh --quiet'
    command = [
        "schtasks.exe", "/Create", "/F", "/TN", TASK_NAME,
        "/SC", "MINUTE", "/MO", str(minutes), "/TR", action,
    ]
    try:
        proc = _run_process(command, capture_output=True, text=True, encoding=_schtasks_encoding(), errors="replace", check=False, timeout=30)
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
        proc = _run_process(
            ["schtasks.exe", "/Query", "/TN", TASK_NAME, "/FO", "LIST", "/V"],
            capture_output=True, text=True, encoding=_schtasks_encoding(), errors="replace", check=False, timeout=15,
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
    refresh.add_argument("--days", type=int, default=DEFAULT_DAYS, help="optional explicit materialization window; default retains history regardless of age")
    refresh.add_argument("--repo-events", type=int, default=DEFAULT_REPO_EVENTS)
    refresh.add_argument("--artifact-events", type=int, default=DEFAULT_ARTIFACT_EVENTS)
    refresh.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS)
    refresh.add_argument("--github-events", type=int, default=DEFAULT_GITHUB_EVENTS_PER_KIND)
    refresh.add_argument("--runner-events", type=int, default=DEFAULT_RUNNER_LOG_EVENTS)
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
            github_events_per_kind=args.github_events,
            runner_events_limit=args.runner_events,
            rebuild=args.rebuild,
        )
        if not args.quiet:
            _emit_json(result)
        # A concurrent materializer already holding the atomic refresh lock is an
        # intentional successful no-op for periodic scheduling. Reporting it as a
        # process failure makes Task Scheduler look unhealthy even though duplicate
        # aggregation was correctly prevented.
        if result.get("status") == "ALREADY_RUNNING":
            return 0
        return 0 if result.get("ok") else 1
    if args.command == "install-task":
        result = install_task(minutes=args.minutes)
        _emit_json(result)
        return 0 if result.get("ok") else 1
    if args.command == "task-status":
        result = task_status()
        _emit_json(result)
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
    _emit_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
