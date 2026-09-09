#!/usr/bin/env python3
"""Release one finished worker's own secondary Git worktree, fail-closed.

This helper is intentionally narrow. It never scans for sibling cleanup
candidates and never uses force removal. The worker-report archiver launches it
out-of-band after finalization so report completion never waits on filesystem
cleanup.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    from .cleanup_converger import (
        Worktree,
        parse_worktrees,
        process_targets_path,
        windows_processes,
        worktree_anchor_matches,
        worktree_is_clean,
    )
except ImportError:
    from cleanup_converger import (
        Worktree,
        parse_worktrees,
        process_targets_path,
        windows_processes,
        worktree_anchor_matches,
        worktree_is_clean,
    )


def _norm(path: Path | str) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _git(cwd: Path, *args: str, timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )


def worktree_root(path: Path) -> Path | None:
    try:
        proc = _git(path, "rev-parse", "--show-toplevel", timeout=5.0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return Path(proc.stdout.strip())


def registered_context(path: Path) -> tuple[Path, Worktree, list[Worktree]] | None:
    root = worktree_root(path)
    if root is None:
        return None
    try:
        proc = _git(root, "worktree", "list", "--porcelain", timeout=10.0)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    rows = parse_worktrees(proc.stdout)
    if not rows:
        return None
    target = next((row for row in rows if _norm(row.path) == _norm(root)), None)
    if target is None:
        return None
    return rows[0].path, target, rows


def release_own_worktree(path: Path) -> dict[str, Any]:
    context = registered_context(path)
    if context is None:
        return {"ok": True, "action": "PRESERVE", "reason": "not_registered_worktree", "path": str(path)}
    repo, target, _rows = context
    if _norm(repo) == _norm(target.path):
        return {"ok": True, "action": "PRESERVE", "reason": "primary_worktree", "path": str(target.path)}
    if target.locked:
        return {
            "ok": True,
            "action": "PRESERVE",
            "reason": f"git_worktree_locked:{target.locked}",
            "path": str(target.path),
        }

    try:
        clean = worktree_is_clean(target.path)
    except (OSError, RuntimeError):
        return {"ok": True, "action": "PRESERVE", "reason": "cleanliness_probe_error", "path": str(target.path)}
    if clean is None:
        return {"ok": True, "action": "PRESERVE", "reason": "cleanliness_probe_timeout", "path": str(target.path)}
    if clean is False:
        return {"ok": True, "action": "PRESERVE", "reason": "dirty", "path": str(target.path)}
    if not worktree_anchor_matches(repo, target):
        reason = "detached_or_unanchored" if target.detached or not target.branch else "branch_ref_mismatch"
        return {"ok": True, "action": "PRESERVE", "reason": reason, "path": str(target.path)}

    try:
        processes = windows_processes()
    except (OSError, RuntimeError, subprocess.TimeoutExpired):
        return {"ok": True, "action": "PRESERVE", "reason": "process_probe_error", "path": str(target.path)}
    # A healthy Windows host always has processes. Treat an empty probe as unknown
    # rather than as evidence that the lane is idle.
    if os.name == "nt" and not processes:
        return {"ok": True, "action": "PRESERVE", "reason": "process_probe_empty", "path": str(target.path)}
    if process_targets_path(target.path, processes, self_pid=os.getpid()):
        return {"ok": True, "action": "PRESERVE", "reason": "external_process_targets_path", "path": str(target.path)}

    # Re-read identity immediately before the non-force remove. Git itself rechecks
    # dirtiness, so a write racing this guard fails closed rather than being forced.
    fresh = registered_context(target.path)
    if fresh is None:
        return {"ok": True, "action": "PRESERVE", "reason": "registration_changed", "path": str(target.path)}
    fresh_repo, current, _ = fresh
    if (
        _norm(fresh_repo) != _norm(repo)
        or current.head != target.head
        or current.branch != target.branch
        or current.detached != target.detached
        or current.locked
    ):
        return {"ok": True, "action": "PRESERVE", "reason": "worktree_identity_changed", "path": str(target.path)}
    if not worktree_anchor_matches(repo, current):
        return {"ok": True, "action": "PRESERVE", "reason": "preservation_anchor_changed", "path": str(target.path)}

    try:
        removed = _git(repo, "worktree", "remove", str(current.path), timeout=60.0)
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": True, "action": "PRESERVE", "reason": "git_remove_error", "path": str(current.path)}
    if removed.returncode != 0:
        return {
            "ok": True,
            "action": "PRESERVE",
            "reason": "git_remove_refused",
            "path": str(current.path),
            "detail": (removed.stderr or removed.stdout).strip()[:500],
        }
    if not worktree_anchor_matches(repo, current):
        return {
            "ok": False,
            "action": "ANCHOR_REGRESSION",
            "reason": "preservation_anchor_changed_after_remove",
            "path": str(current.path),
        }
    return {
        "ok": True,
        "action": "REMOVED_OWN_WORKTREE",
        "path": str(current.path),
        "branch": current.branch,
        "head": current.head,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=3.0)
    parser.add_argument("--quiet", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.delay_seconds > 0:
        time.sleep(min(float(args.delay_seconds), 30.0))
    result = release_own_worktree(args.path)
    if not args.quiet:
        print(json.dumps(result))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
