from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ISSUE_REF_RE = re.compile(r"#(?P<number>\d+)\b")


@dataclass(frozen=True)
class RepoSpec:
    project: str
    path: Path


def default_operator_live(vault_root: Path) -> Path:
    # Canonical Vault is usually a Desktop sibling of DevProgressBoard, while
    # development worktrees may live one directory deeper under vault-worktrees.
    bases = [vault_root.parent, vault_root.parent.parent, vault_root.parent.parent.parent]
    for base in bases:
        candidate = base / "DevProgressBoard" / "state" / "operator-live.json"
        if candidate.is_file():
            return candidate
    return vault_root.parent / "DevProgressBoard" / "state" / "operator-live.json"


def _run_git(path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _git_value(path: Path, *args: str) -> str | None:
    proc = _run_git(path, *args, check=False)
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value or None


def discover_repo_specs(operator_live: Path | None, *, vault_root: Path | None = None) -> list[RepoSpec]:
    """Discover canonical project repos from live operator metadata, with Vault optional.

    The operator file is only a path registry here. Commit history is read directly
    from each local Git object database, so stale dashboard event projections do not
    become the timeline source of truth.
    """
    specs: list[RepoSpec] = []
    seen: set[tuple[str, str]] = set()
    if operator_live is not None and operator_live.is_file():
        try:
            raw = json.loads(operator_live.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        for item in raw.get("repos") or []:
            if not isinstance(item, dict) or not item.get("available"):
                continue
            project = str(item.get("id") or "").strip().casefold()
            path_text = str(item.get("path") or "").strip()
            if not project or not path_text:
                continue
            path = Path(path_text)
            key = (project, str(path.resolve()).casefold()) if path.exists() else (project, path_text.casefold())
            if key in seen:
                continue
            seen.add(key)
            specs.append(RepoSpec(project=project, path=path))
    if vault_root is not None and (vault_root / ".git").exists():
        key = ("vault", str(vault_root.resolve()).casefold())
        if key not in seen:
            specs.append(RepoSpec(project="vault", path=vault_root))
    return specs


def parse_repo_arg(value: str) -> RepoSpec:
    project, sep, path = value.partition("=")
    if not sep or not project.strip() or not path.strip():
        raise ValueError("repo must use PROJECT=PATH")
    return RepoSpec(project=project.strip().casefold(), path=Path(path.strip()))


def repo_snapshot(spec: RepoSpec) -> dict[str, Any]:
    path = spec.path
    available = path.is_dir() and _run_git(path, "rev-parse", "--git-dir", check=False).returncode == 0
    snapshot: dict[str, Any] = {
        "project": spec.project,
        "path": str(path),
        "available": available,
        "source_type": "LOCAL_GIT",
    }
    if not available:
        return snapshot
    snapshot.update({
        "branch": _git_value(path, "branch", "--show-current"),
        "head": _git_value(path, "rev-parse", "HEAD"),
        "origin": _git_value(path, "remote", "get-url", "origin"),
    })
    proc = _run_git(path, "status", "--porcelain=v1", check=False)
    if proc.returncode == 0:
        snapshot["dirty_entries"] = len([line for line in proc.stdout.splitlines() if line.strip()])
    return snapshot


def _refs_from_title(title: str) -> list[str]:
    return [f"#{match.group('number')}" for match in ISSUE_REF_RE.finditer(title)]


def _git_log_rows(path: Path, revisions: list[str], *, limit: int, since: datetime | None = None) -> list[tuple[str, str, str, str]]:
    args = ["log", *revisions, "--date-order", f"--max-count={min(200, max(1, int(limit)))}"]
    if since is not None:
        args.append(f"--since={since.isoformat()}")
    args.append("--format=%H%x1f%cI%x1f%s%x1f%D")
    proc = _run_git(path, *args, check=False)
    if proc.returncode != 0:
        return []
    rows: list[tuple[str, str, str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        sha, event_at, title, decorations = parts
        try:
            datetime.fromisoformat(event_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        rows.append((sha, event_at, title, decorations))
    return rows


def _event_from_row(spec: RepoSpec, row: tuple[str, str, str, str], *, origin: str | None) -> dict[str, Any]:
    sha, event_at, title, decorations = row
    return {
        "id": f"git:{spec.project}:{sha}",
        "source_type": "GIT_COMMIT",
        "authority": "REPO_HISTORY",
        "event_at": event_at,
        "project": spec.project,
        "projects": [spec.project],
        "title": title,
        "summary": title,
        "sha": sha,
        "short_sha": sha[:10],
        "refs": _refs_from_title(title),
        "decorations": decorations,
        "repo_path": str(spec.path),
        "origin": origin,
        "repo_state": "ALL_BRANCHES",
        "thread_id": f"repo:{spec.project}",
        "thread_source": "PROJECT_REPO_STREAM",
    }


def git_commit_events(spec: RepoSpec, *, limit: int = 20, since: datetime | None = None) -> list[dict[str, Any]]:
    """Return one bounded date-ordered chronology across every local/remote branch ref.

    No branch, including main/default, receives a privileged quota. Decorations preserve
    the refs that make each commit reachable so workers can orient from the actual live
    workstreams instead of treating one integration branch as the project timeline.
    """
    if limit <= 0 or not spec.path.is_dir():
        return []
    if _run_git(spec.path, "rev-parse", "--git-dir", check=False).returncode != 0:
        return []
    origin = _git_value(spec.path, "remote", "get-url", "origin")
    rows = _git_log_rows(spec.path, ["--all"], limit=limit, since=since)
    events = [_event_from_row(spec, row, origin=origin) for row in rows]
    events.sort(key=lambda event: (datetime.fromisoformat(event["event_at"].replace("Z", "+00:00")), event["id"]), reverse=True)
    return events

def collect_repo_history(specs: Iterable[RepoSpec], *, limit_per_repo: int = 20, since: datetime | None = None) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for spec in specs:
        snapshots.append(repo_snapshot(spec))
        events.extend(git_commit_events(spec, limit=limit_per_repo, since=since))
    events.sort(key=lambda event: (datetime.fromisoformat(event["event_at"].replace("Z", "+00:00")), event["id"]), reverse=True)
    return {
        "authority": "LOCAL_REPO_HISTORY",
        "contract": "local Git history only; no network fetch and no memory authority",
        "repo_snapshots": snapshots,
        "events": events,
    }
