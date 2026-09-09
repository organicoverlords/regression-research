from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from tools.cleanup_converger import (
        busy_claim, busy_release, canonical_main_contains_head,
        cwd_targets_path, parse_worktrees, process_targets_path,
        recent_mcp_cwds, windows_processes, worktree_anchor_matches,
    )
except ModuleNotFoundError:
    from cleanup_converger import (
        busy_claim, busy_release, canonical_main_contains_head,
        cwd_targets_path, parse_worktrees, process_targets_path,
        recent_mcp_cwds, windows_processes, worktree_anchor_matches,
    )

QUARANTINE_ROOT = Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "VaultWorktreeQuarantine" / "auto"
def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], text=True, capture_output=True,
        encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )


def ensure_canonical_main(repo: Path, window_seconds: int = 600) -> dict:
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=normal")
    if status.returncode != 0:
        return {"status": "error", "error": status.stderr.strip()}
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if status.stdout:
        return {"status": "dirty_blocked", "branch": branch}
    if branch == "main":
        return {"status": "current", "branch": branch}
    recent = recent_mcp_cwds(window_seconds)
    processes = windows_processes()
    if cwd_targets_path(repo, recent) or process_targets_path(repo, processes, self_pid=os.getpid()):
        return {"status": "active_wrong_branch", "branch": branch}
    switched = _git(repo, "switch", "main")
    if switched.returncode != 0:
        return {"status": "switch_failed", "branch": branch, "error": switched.stderr.strip()}
    return {"status": "restored", "from_branch": branch, "branch": "main"}
def _dirty_age_seconds(path: Path, status_z: str, now: float) -> float:
    newest = path.stat().st_mtime
    tokens = [item for item in status_z.split("\0") if item]
    index = 0
    while index < len(tokens):
        token = tokens[index]
        code = token[:2] if len(token) >= 3 else ""
        relative = token[3:] if len(token) >= 3 else token
        candidates = [relative]
        if ("R" in code or "C" in code) and index + 1 < len(tokens):
            index += 1
            candidates.append(tokens[index])
        for item in candidates:
            try:
                newest = max(newest, (path / item).stat().st_mtime)
            except OSError:
                pass
        index += 1
    return max(0.0, now - newest)


def _branch_scope(repo_scope: str, branch: str | None) -> str | None:
    if not branch:
        return None
    namespace = repo_scope.split(":", 1)[0]
    return f"{namespace}:git-ref:refs/heads/{branch}"
def quarantine_pressure(
    repo_name: str, repo: Path, repo_scope: str, *, max_dirty: int = 6,
    min_idle_seconds: int = 3600, window_seconds: int = 600,
    actor: str = "ChatGPT:scheduled-worktree-hygiene",
) -> dict:
    listed = _git(repo, "worktree", "list", "--porcelain")
    if listed.returncode != 0:
        return {"status": "error", "error": listed.stderr.strip()}
    recent = recent_mcp_cwds(window_seconds)
    processes = windows_processes()
    now = time.time()
    dirty_total = 0
    candidates = []
    for worktree in parse_worktrees(listed.stdout)[1:]:
        path = worktree.path
        if not path.exists():
            continue
        status = _git(path, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
        if status.returncode != 0 or not status.stdout:
            continue
        dirty_total += 1
        if cwd_targets_path(path, recent) or process_targets_path(path, processes, self_pid=os.getpid()):
            continue
        age = _dirty_age_seconds(path, status.stdout, now)
        if age < min_idle_seconds or not worktree_anchor_matches(repo, worktree):
            continue
        if (worktree.detached or not worktree.branch) and not canonical_main_contains_head(repo, worktree):
            continue
        candidates.append((age, worktree, status.stdout))
    need = max(0, dirty_total - max_dirty)
    if need == 0:
        return {"status": "within_limit", "dirty_before": dirty_total, "quarantined": 0}
    claimed, detail = busy_claim(actor, repo_scope)
    if not claimed:
        return {"status": "metadata_busy", "dirty_before": dirty_total, "quarantined": 0, "detail": detail}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = QUARANTINE_ROOT / repo_name / stamp
    entries = []
    moved = 0
    try:
        for _age, worktree, status_z in sorted(candidates, key=lambda row: row[0], reverse=True):
            if moved >= need:
                break
            branch_scope = _branch_scope(repo_scope, worktree.branch)
            branch_claimed = False
            if branch_scope:
                branch_claimed, _branch_detail = busy_claim(actor, branch_scope)
                if not branch_claimed:
                    continue
            try:
                if not worktree.path.exists() or cwd_targets_path(worktree.path, recent):
                    continue
                live_processes = windows_processes()
                if process_targets_path(worktree.path, live_processes, self_pid=os.getpid()):
                    continue
                current = _git(worktree.path, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
                if current.returncode != 0 or not current.stdout:
                    continue
                root.mkdir(parents=True, exist_ok=True)
                safe = re.sub(r"[^A-Za-z0-9._-]+", "_", worktree.path.name)[:96]
                destination = root / f"{moved + 1:02d}-{safe}"
                shutil.move(str(worktree.path), str(destination))
                if worktree.path.exists() or not destination.exists():
                    raise RuntimeError("quarantine move verification failed")
                entries.append({
                    "original_path": str(worktree.path), "quarantine_path": str(destination),
                    "head": worktree.head, "branch": worktree.branch,
                    "status_porcelain": current.stdout.replace("\0", "\\0"),
                })
                moved += 1
            except OSError:
                continue
            finally:
                if branch_scope and branch_claimed:
                    busy_release(actor, branch_scope, f"worktree hygiene quarantine guard for {worktree.path.name}")
        if moved:
            _git(repo, "worktree", "prune")
            payload = {
                "schema": "worktree-quarantine.v1", "at": stamp, "repo": repo_name,
                "issue": 900, "entries": entries,
            }
            (root / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    finally:
        busy_release(actor, repo_scope, f"worktree hygiene quarantine moved={moved}")
    return {
        "status": "quarantined" if moved else "pressure_unresolved",
        "dirty_before": dirty_total, "quarantined": moved,
        "manifest": str(root / "manifest.json") if moved else None,
    }
