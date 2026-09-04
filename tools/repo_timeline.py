from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

PRODUCT_ROOTS = {
    "lowvram": r"C:\Users\Lauri\Desktop\lowvram3d-repo",
    "tiny3d": r"C:\Users\Lauri\Desktop\tiny3d",
    "p3": r"C:\Users\Lauri\Documents\Unreal Projects\p3",
}

ISSUE_REF_RE = re.compile(r"#(?P<number>\d+)\b")


@dataclass(frozen=True)
class RepoSpec:
    project: str
    path: Path


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


def discover_repo_specs(*, vault_root: Path | None = None) -> list[RepoSpec]:
    """Discover the known product repos used by this historical Git index."""
    specs: list[RepoSpec] = []
    seen: set[str] = set()
    for project, raw in PRODUCT_ROOTS.items():
        path = Path(os.path.expandvars(raw))
        if not (path / ".git").exists():
            continue
        key = str(path.resolve()).casefold()
        if key in seen:
            continue
        seen.add(key)
        specs.append(RepoSpec(project=project, path=path))
    if vault_root is not None and (vault_root / ".git").exists():
        key = str(vault_root.resolve()).casefold()
        if key not in seen:
            specs.append(RepoSpec(project="vault", path=vault_root))
    return specs

def parse_repo_arg(value: str) -> RepoSpec:
    project, sep, path = value.partition("=")
    if not sep or not project.strip() or not path.strip():
        raise ValueError("repo must use PROJECT=PATH")
    return RepoSpec(project=project.strip().casefold(), path=Path(path.strip()))



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
    events: list[dict[str, Any]] = []
    for spec in specs:
        events.extend(git_commit_events(spec, limit=limit_per_repo, since=since))
    events.sort(key=lambda event: (datetime.fromisoformat(event["event_at"].replace("Z", "+00:00")), event["id"]), reverse=True)
    return {
        "authority": "LOCAL_REPO_HISTORY",
        "contract": "local Git history only; no network fetch and no memory authority",
        "events": events,
    }
