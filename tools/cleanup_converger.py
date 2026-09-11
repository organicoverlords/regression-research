#!/usr/bin/env python3
"""Converge redundant P3/Vault/agents worktrees to a bounded safe boundary.

Operator cleanup plus a stricter worker-safe automatic mode. The command never force-removes a worktree, deletes a
branch, resets/rebases, fetches, or discards dirty/unanchored state. It loops
internally so a single invocation can absorb lanes that become safely idle.
For inactive preserved P3 lanes it may also reclaim only Git-ignored standard
Unreal build/cache directories; tracked Content, Saved, proof/evidence, and
dirty source are outside that cleanup surface.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
LOCALAPPDATA = Path(os.path.expandvars(r"%LOCALAPPDATA%"))
MCP_LOG_ROOT = LOCALAPPDATA / "ChatGPTMcpClean" / "minimal-connectors"
BUSY_CMD = LOCALAPPDATA / "BusyCoordinator" / "busy-python.cmd"

DEFAULT_REPOS = (
    ("P3", Path(r"C:\Users\Lauri\Documents\Unreal Projects\p3"), "p3:git-worktree-metadata"),
    ("Vault", Path(r"C:\Users\Lauri\Desktop\vault"), "organicoverlords/regression-research:git-worktree-metadata"),
    ("Agents", Path(r"C:\Users\Lauri\.agents"), "organicoverlords/agents:git-worktree-metadata"),
)
P3_GENERATED_DIR_NAMES = frozenset({"Binaries", "Intermediate", "DerivedDataCache"})
CLEANLINESS_PROBE_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class Worktree:
    path: Path
    head: str
    branch: str | None
    detached: bool
    locked: str | None = None


@dataclass
class Action:
    repo: str
    path: str
    action: str
    branch: str | None = None
    head: str | None = None
    reason: str | None = None


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )


def _git(
    repo: Path,
    *args: str,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return _run(["git", "-C", str(repo), *args], check=check, timeout=timeout)


def parse_worktrees(text: str) -> list[Worktree]:
    rows: list[Worktree] = []
    current: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("worktree "):
            if current:
                rows.append(_worktree_from_row(current))
            current = {"path": line[9:], "head": "", "branch": None, "detached": False, "locked": None}
        elif current is not None and line.startswith("HEAD "):
            current["head"] = line[5:]
        elif current is not None and line.startswith("branch "):
            ref = line[7:]
            current["branch"] = ref.removeprefix("refs/heads/")
        elif current is not None and line == "detached":
            current["detached"] = True
        elif current is not None and line.startswith("locked"):
            current["locked"] = line[7:].strip() if len(line) > 7 else "locked"
    if current:
        rows.append(_worktree_from_row(current))
    return rows


def _worktree_from_row(row: dict[str, Any]) -> Worktree:
    return Worktree(
        path=Path(str(row["path"]).replace("/", os.sep)),
        head=str(row.get("head", "")),
        branch=row.get("branch"),
        detached=bool(row.get("detached")),
        locked=row.get("locked"),
    )


def _norm_path(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(value))).replace("/", "\\")


def path_is_same_or_child(value: str | Path, root: str | Path) -> bool:
    value_norm = _norm_path(value).rstrip("\\")
    root_norm = _norm_path(root).rstrip("\\")
    return value_norm == root_norm or value_norm.startswith(root_norm + "\\")


def _parse_timestamp(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


def _tail_text(path: Path, max_bytes: int = 2_000_000) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
            handle.readline()
        return handle.read().decode("utf-8", errors="replace")


def recent_mcp_cwds(
    window_seconds: int,
    *,
    log_root: Path = MCP_LOG_ROOT,
    now: float | None = None,
) -> set[str]:
    # Reuse the canonical live-swarm bounded transport discovery/reader so
    # cleanup protects recent activity from every current MCP connector
    # instance, including a newer rotated archive selected for that instance.
    try:
        from tools.live_swarm import _discover_transport_sources, _read_window
    except ModuleNotFoundError:  # direct `python tools\cleanup_converger.py` entrypoint
        from live_swarm import _discover_transport_sources, _read_window

    now_ts = time.time() if now is None else now
    now_dt = datetime.fromtimestamp(now_ts, timezone.utc)
    cutoff_dt = now_dt - timedelta(seconds=window_seconds)
    result: set[str] = set()
    if not log_root.exists():
        return result
    try:
        sources, _discovery = _discover_transport_sources(log_root, cutoff_dt, now_dt)
    except OSError:
        return result
    cutoff_ts = cutoff_dt.timestamp()
    for source, _latest in sources:
        try:
            rows, _complete, _sample_bytes = _read_window(source, cutoff_dt)
        except OSError:
            continue
        for event in rows:
            cwd = event.get("cwd")
            at = _parse_timestamp(event.get("at"))
            if cwd and at is not None and at >= cutoff_ts:
                result.add(_norm_path(cwd))
    return result


def windows_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ParentProcessId,CommandLine | ConvertTo-Json -Compress",
    ]
    completed = _run(command, check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    return [row for row in payload if isinstance(row, dict)]


def process_targets_path(path: Path, processes: Iterable[dict[str, Any]], *, self_pid: int | None = None) -> bool:
    needle = _norm_path(path).lower()
    for row in processes:
        pid = row.get("ProcessId")
        if self_pid is not None and pid == self_pid:
            continue
        command_line = row.get("CommandLine")
        if not isinstance(command_line, str):
            continue
        if needle in _norm_path(command_line).lower():
            return True
    return False


def cwd_targets_path(path: Path, recent_cwds: Iterable[str]) -> bool:
    return any(path_is_same_or_child(cwd, path) for cwd in recent_cwds)


def worktree_linkage_is_missing(path: Path) -> bool:
    """Return True only when a listed worktree has no usable local Git linkage."""
    marker = path / ".git"
    if not marker.exists():
        return True
    if not marker.is_file():
        return False
    try:
        first_line = marker.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
    except (OSError, IndexError):
        return False
    prefix = "gitdir:"
    if not first_line.lower().startswith(prefix):
        return False
    target_text = first_line[len(prefix):].strip()
    if not target_text:
        return False
    target = Path(target_text)
    if not target.is_absolute():
        target = marker.parent / target
    return not target.exists()


def worktree_is_clean(
    path: Path, timeout_seconds: float = CLEANLINESS_PROBE_TIMEOUT_SECONDS
) -> bool | None:
    """Return clean/dirty, or None when the bounded Git probe times out.

    One porcelain status covers staged, unstaged, and untracked changes. This keeps
    the safety check conservative while avoiding three Git process launches per
    worktree on cleanup scans. Timeout remains fail-closed.
    """
    try:
        completed = _git(
            path,
            "status",
            "--porcelain=v1",
            "-z",
            "--untracked-files=normal",
            "--ignore-submodules=none",
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        raise RuntimeError(f"git status failed for {path}: {completed.stderr.strip()}")
    return not bool(completed.stdout)


def dirty_changes_match_origin_main(repo: Path, worktree: Worktree) -> bool | None:
    """Prove every dirty/untracked path is byte-identical to cached origin/main."""
    if not canonical_main_contains_head(repo, worktree):
        return False
    try:
        changed = _git(worktree.path, "diff", "--no-renames", "--name-only", "-z", "HEAD", "--", check=False, timeout=CLEANLINESS_PROBE_TIMEOUT_SECONDS)
        untracked = _git(worktree.path, "ls-files", "--others", "--exclude-standard", "-z", check=False, timeout=CLEANLINESS_PROBE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return None
    if changed.returncode != 0 or untracked.returncode != 0:
        return None
    paths = {item for item in (changed.stdout + untracked.stdout).split("\0") if item}
    if not paths:
        return None
    for relative in paths:
        local = worktree.path / relative
        main_blob = _git(repo, "rev-parse", "--verify", f"refs/remotes/origin/main:{relative}", check=False, timeout=CLEANLINESS_PROBE_TIMEOUT_SECONDS)
        if not local.exists():
            if main_blob.returncode == 0:
                return False
            continue
        if not local.is_file():
            return False
        local_blob = _git(worktree.path, "hash-object", "--", relative, check=False, timeout=CLEANLINESS_PROBE_TIMEOUT_SECONDS)
        if main_blob.returncode != 0 or local_blob.returncode != 0 or local_blob.stdout.strip() != main_blob.stdout.strip():
            return False
    return True


def _is_reparse_dir(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return True
    # Windows FILE_ATTRIBUTE_REPARSE_POINT. Skip symlinks/junction-like dirs so
    # cache cleanup can never recurse outside the worktree through a reparse.
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def generated_cache_dirs(path: Path) -> list[Path]:
    """Return only Git-ignored standard Unreal build/cache directories."""
    candidates: list[Path] = []
    for name in P3_GENERATED_DIR_NAMES:
        candidate = path / name
        if candidate.is_dir() and not _is_reparse_dir(candidate):
            candidates.append(candidate)
    plugins = path / "Plugins"
    if plugins.is_dir() and not _is_reparse_dir(plugins):
        for current_root, dir_names, _file_names in os.walk(plugins):
            current = Path(current_root)
            kept: list[str] = []
            for name in dir_names:
                candidate = current / name
                if _is_reparse_dir(candidate):
                    continue
                if name in P3_GENERATED_DIR_NAMES:
                    candidates.append(candidate)
                    continue  # do not recurse through generated output
                kept.append(name)
            dir_names[:] = kept

    ignored: list[Path] = []
    for candidate in sorted(set(candidates), key=lambda item: (len(item.parts), str(item).lower())):
        if any(path_is_same_or_child(candidate, parent) for parent in ignored):
            continue
        try:
            relative = candidate.relative_to(path)
        except ValueError:
            continue
        check = _git(path, "check-ignore", "-q", "--", str(relative), check=False)
        if check.returncode == 0:
            ignored.append(candidate)
    return ignored


def _current_worktree(repo: Path, path: Path) -> Worktree | None:
    needle = _norm_path(path)
    for item in parse_worktrees(_git(repo, "worktree", "list", "--porcelain").stdout):
        if _norm_path(item.path) == needle:
            return item
    return None


def _fresh_cache_guard(repo: Path, worktree: Worktree, window_seconds: int) -> str | None:
    current = _current_worktree(repo, worktree.path)
    if current is None:
        return "missing_registration"
    if current.head != worktree.head or current.branch != worktree.branch:
        return "worktree_identity_changed"
    if current.locked:
        return f"git_worktree_locked:{current.locked}"
    recent = recent_mcp_cwds(window_seconds)
    processes = windows_processes()
    if cwd_targets_path(worktree.path, recent):
        return "recent_mcp_cwd_activity"
    if process_targets_path(worktree.path, processes, self_pid=os.getpid()):
        return "external_process_targets_path"
    return None


def _cache_scope(repo_name: str, worktree: Worktree) -> str:
    leaf = worktree.path.name.replace(":", "_") or "worktree"
    return f"{repo_name.lower()}:generated-cache:{leaf}"


def _branch_ref_scope(repo_scope: str, worktree: Worktree) -> str | None:
    if not worktree.branch:
        return None
    namespace = repo_scope.split(":", 1)[0]
    return f"{namespace}:git-ref:refs/heads/{worktree.branch}"


def _clean_generated_cache_one(
    repo_name: str, repo: Path, worktree: Worktree, window_seconds: int
) -> Action:
    reason = _fresh_cache_guard(repo, worktree, window_seconds)
    if reason:
        return Action(repo_name, str(worktree.path), "SKIP", worktree.branch, worktree.head, reason)
    candidates = generated_cache_dirs(worktree.path)
    if not candidates:
        return Action(repo_name, str(worktree.path), "SKIP", worktree.branch, worktree.head, "no_generated_cache")

    removed: list[str] = []
    for candidate in candidates:
        try:
            relative = candidate.relative_to(worktree.path)
        except ValueError:
            continue
        # Re-prove ignore status immediately before each destructive directory
        # operation. Never remove a directory merely because its name matches.
        check = _git(worktree.path, "check-ignore", "-q", "--", str(relative), check=False)
        if check.returncode != 0 or _is_reparse_dir(candidate):
            continue
        try:
            shutil.rmtree(candidate)
        except OSError as exc:
            if removed:
                return Action(
                    repo_name,
                    str(worktree.path),
                    "CLEANED_GENERATED_CACHE",
                    worktree.branch,
                    worktree.head,
                    f"partial dirs={len(removed)} blocked={relative}:{exc.__class__.__name__}",
                )
            return Action(
                repo_name,
                str(worktree.path),
                "BLOCKED",
                worktree.branch,
                worktree.head,
                f"generated_cache_locked:{relative}:{exc.__class__.__name__}",
            )
        removed.append(str(relative))
    if not removed:
        return Action(repo_name, str(worktree.path), "SKIP", worktree.branch, worktree.head, "no_generated_cache")
    return Action(
        repo_name,
        str(worktree.path),
        "CLEANED_GENERATED_CACHE",
        worktree.branch,
        worktree.head,
        f"dirs={len(removed)}",
    )


def branch_ref_matches(repo: Path, worktree: Worktree) -> bool:
    if worktree.detached or not worktree.branch or not worktree.head:
        return False
    completed = _git(repo, "rev-parse", f"refs/heads/{worktree.branch}", check=False)
    return completed.returncode == 0 and completed.stdout.strip() == worktree.head


def exact_anchor_refs(repo: Path, worktree: Worktree) -> list[str]:
    """Return durable refs that point exactly at this worktree HEAD.

    Exact refs are one preservation proof for detached worktrees. Canonical-main
    ancestry is checked separately so an already-merged detached HEAD does not
    need a synthetic exact ref merely to make the checkout disposable. Remote
    symbolic HEAD aliases are ignored.
    """
    if not worktree.head:
        return []
    try:
        completed = _git(
            repo,
            "for-each-ref",
            "--format=%(refname)",
            "--points-at",
            worktree.head,
            "refs/heads",
            "refs/remotes",
            "refs/tags",
            check=False,
            timeout=CLEANLINESS_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return []
    if completed.returncode != 0:
        return []
    return [
        ref
        for ref in completed.stdout.splitlines()
        if ref and not (ref.startswith("refs/remotes/") and ref.endswith("/HEAD"))
    ]


def canonical_main_contains_head(repo: Path, worktree: Worktree) -> bool:
    """Return True when cached origin/main already contains the worktree HEAD.

    This is intentionally fetch-free. A stale local origin/main can only make the
    check conservative (False); cleanup never advances remote-tracking refs.
    """
    if not worktree.head:
        return False
    try:
        completed = _git(
            repo,
            "merge-base",
            "--is-ancestor",
            worktree.head,
            "refs/remotes/origin/main",
            check=False,
            timeout=CLEANLINESS_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


def worktree_anchor_matches(repo: Path, worktree: Worktree) -> bool:
    if worktree.detached or not worktree.branch:
        return bool(exact_anchor_refs(repo, worktree)) or canonical_main_contains_head(repo, worktree)
    return branch_ref_matches(repo, worktree)


def registered_paths(repo: Path) -> set[str]:
    completed = _git(repo, "worktree", "list", "--porcelain")
    return {_norm_path(row.path) for row in parse_worktrees(completed.stdout)}


def disk_free_gb(path: Path) -> float:
    return round(shutil.disk_usage(path).free / (1024**3), 1)


def busy_claim(actor: str, scope: str) -> tuple[bool, str]:
    if not BUSY_CMD.exists():
        return False, f"BusyCoordinator missing: {BUSY_CMD}"
    inspect = _run([str(BUSY_CMD), "inspect", scope], check=False)
    if inspect.returncode != 0:
        return False, inspect.stderr.strip() or inspect.stdout.strip()
    claim = _run([str(BUSY_CMD), "claim", actor, scope], check=False)
    if claim.returncode != 0 or '"ok":true' not in claim.stdout.lower():
        return False, claim.stderr.strip() or claim.stdout.strip()
    return True, claim.stdout.strip()


def busy_release(actor: str, scope: str, checkpoint: str) -> None:
    if not BUSY_CMD.exists():
        return
    _run([str(BUSY_CMD), "release", actor, scope, "--checkpoint", checkpoint], check=False)


def eligibility_reason(
    worktree: Worktree,
    *,
    recent_cwds: Iterable[str],
    processes: Iterable[dict[str, Any]],
    clean: bool | None,
    ref_matches: bool,
) -> str | None:
    if worktree.locked:
        return f"git_worktree_locked:{worktree.locked}"
    if (worktree.detached or not worktree.branch) and not ref_matches:
        return "detached_or_unanchored"
    if cwd_targets_path(worktree.path, recent_cwds):
        return "recent_mcp_cwd_activity"
    if process_targets_path(worktree.path, processes, self_pid=os.getpid()):
        return "external_process_targets_path"
    if clean is False:
        return "dirty"
    if not ref_matches:
        return "branch_ref_mismatch"
    return None


def _fresh_guard(repo: Path, worktree: Worktree, window_seconds: int) -> str | None:
    if not worktree.path.exists():
        return "missing"
    recent = recent_mcp_cwds(window_seconds)
    processes = windows_processes()
    if cwd_targets_path(worktree.path, recent):
        return "recent_mcp_cwd_activity"
    if process_targets_path(worktree.path, processes, self_pid=os.getpid()):
        return "external_process_targets_path"
    clean = worktree_is_clean(worktree.path)
    if clean is None:
        return "cleanliness_probe_timeout"
    if clean is False:
        return "dirty"
    if not worktree_anchor_matches(repo, worktree):
        return "detached_or_unanchored" if worktree.detached or not worktree.branch else "branch_ref_mismatch"
    return None


def _remove_one(repo_name: str, repo: Path, worktree: Worktree, window_seconds: int) -> Action:
    reason = _fresh_guard(repo, worktree, window_seconds)
    if reason:
        return Action(repo_name, str(worktree.path), "SKIP", worktree.branch, worktree.head, reason)

    completed = _git(repo, "worktree", "remove", str(worktree.path), check=False)
    if completed.returncode == 0:
        if not worktree_anchor_matches(repo, worktree):
            raise RuntimeError(f"preservation anchor changed after removal: {worktree.branch} {worktree.head}")
        return Action(repo_name, str(worktree.path), "REMOVED_WORKTREE", worktree.branch, worktree.head)

    # Windows can detach worktree metadata before filesystem deletion fails. Only
    # finish such a residue when an exact preservation anchor remains and fresh
    # live activity checks are clear. Otherwise leave it untouched.
    if _norm_path(worktree.path) in registered_paths(repo):
        return Action(repo_name, str(worktree.path), "BLOCKED", worktree.branch, worktree.head, "git_remove_failed_registered")
    if (worktree.path / ".git").exists() or not worktree_anchor_matches(repo, worktree):
        return Action(repo_name, str(worktree.path), "BLOCKED", worktree.branch, worktree.head, "detached_residue_not_proven_safe")

    recent = recent_mcp_cwds(window_seconds)
    processes = windows_processes()
    if cwd_targets_path(worktree.path, recent) or process_targets_path(worktree.path, processes, self_pid=os.getpid()):
        return Action(repo_name, str(worktree.path), "BLOCKED", worktree.branch, worktree.head, "detached_residue_active")
    try:
        shutil.rmtree(worktree.path)
    except OSError as exc:
        return Action(repo_name, str(worktree.path), "BLOCKED", worktree.branch, worktree.head, f"detached_residue_locked:{exc.__class__.__name__}")
    return Action(repo_name, str(worktree.path), "REMOVED_RESIDUE", worktree.branch, worktree.head)


def scan_repo(
    repo_name: str,
    repo: Path,
    window_seconds: int,
    *,
    require_contained: bool = False,
    allow_generated_cache: bool | None = None,
) -> tuple[list[Worktree], list[Worktree], list[Action]]:
    if allow_generated_cache is None:
        allow_generated_cache = not require_contained
    worktrees = parse_worktrees(_git(repo, "worktree", "list", "--porcelain").stdout)
    recent = recent_mcp_cwds(window_seconds)
    processes = windows_processes()
    candidates: list[Worktree] = []
    cache_candidates: list[Worktree] = []
    observations: list[Action] = []
    for worktree in worktrees[1:]:
        cache_guarded = bool(worktree.locked or cwd_targets_path(worktree.path, recent) or process_targets_path(worktree.path, processes, self_pid=os.getpid()))
        preliminary = eligibility_reason(
            worktree, recent_cwds=recent, processes=processes, clean=None,
            ref_matches=worktree_anchor_matches(repo, worktree),
        )
        if preliminary and (preliminary.startswith("git_worktree_locked:") or preliminary in {"detached_or_unanchored", "recent_mcp_cwd_activity", "external_process_targets_path", "branch_ref_mismatch"}):
            observations.append(Action(repo_name, str(worktree.path), "PRESERVE", worktree.branch, worktree.head, preliminary))
            if repo_name == "P3" and allow_generated_cache and not cache_guarded and generated_cache_dirs(worktree.path):
                cache_candidates.append(worktree)
            continue
        try:
            clean = worktree_is_clean(worktree.path)
        except RuntimeError:
            # `git worktree list` can retain a registration after its linked worktree
            # metadata is gone. The directory itself may still exist as residue, so
            # path existence alone is not enough to decide whether `git status` failed
            # on a real worktree. Only suppress the error when Git linkage is absent.
            if worktree_linkage_is_missing(worktree.path):
                observations.append(Action(repo_name, str(worktree.path), "PRESERVE", worktree.branch, worktree.head, "missing_worktree_registration"))
                continue
            raise
        if clean is None:
            observations.append(Action(repo_name, str(worktree.path), "PRESERVE", worktree.branch, worktree.head, "cleanliness_probe_timeout"))
            continue
        reason = eligibility_reason(worktree, recent_cwds=recent, processes=processes, clean=clean, ref_matches=True)
        if reason:
            if reason == "dirty" and canonical_main_contains_head(repo, worktree):
                redundant = dirty_changes_match_origin_main(repo, worktree)
                if redundant is True:
                    reason = "dirty_redundant_in_origin_main"
                elif redundant is False:
                    reason = "dirty_unique_contained_in_origin_main"
                else:
                    reason = "dirty_contained_unclassified"
            observations.append(Action(repo_name, str(worktree.path), "PRESERVE", worktree.branch, worktree.head, reason))
            if repo_name == "P3" and allow_generated_cache and not cache_guarded and generated_cache_dirs(worktree.path):
                cache_candidates.append(worktree)
            continue
        if require_contained and not canonical_main_contains_head(repo, worktree):
            if worktree.detached or not worktree.branch:
                observations.append(Action(repo_name, str(worktree.path), "PRESERVE", worktree.branch, worktree.head, "detached_not_contained_in_origin_main"))
                continue
            # Clean idle branch worktrees are disposable execution surfaces even when unmerged.
            # The exact HEAD remains durably anchored by the branch ref.
        candidates.append(worktree)
    return candidates, cache_candidates, observations

def summarize_actions(actions: list[Action]) -> dict[str, Any]:
    final_by_path: dict[tuple[str, str], Action] = {}
    for row in actions:
        final_by_path[(row.repo, row.path)] = row
    compact_actions = list(final_by_path.values())
    progress_events = [
        row
        for row in actions
        if row.action in {"REMOVED_WORKTREE", "REMOVED_RESIDUE", "CLEANED_GENERATED_CACHE"}
    ]
    removed_paths = {
        (row.repo, row.path)
        for row in progress_events
        if row.action in {"REMOVED_WORKTREE", "REMOVED_RESIDUE"}
    }
    cache_cleaned_paths = {
        (row.repo, row.path) for row in progress_events if row.action == "CLEANED_GENERATED_CACHE"
    }
    blocked = [row for row in compact_actions if row.action == "BLOCKED"]
    return {
        "removed_count": len(removed_paths),
        "generated_cache_cleanup_count": len(cache_cleaned_paths),
        "blocked_count": len(blocked),
        "progress_events": [row.__dict__ for row in progress_events],
        "actions": [row.__dict__ for row in compact_actions],
    }


def hygiene_snapshot(window_seconds: int, repo_names: set[str] | None = None) -> dict[str, Any]:
    repos: list[dict[str, Any]] = []
    totals = {"auxiliary_count": 0, "dirty_count": 0, "contained_dirty_count": 0, "redundant_dirty_count": 0, "unique_dirty_count": 0, "safe_reap_count": 0, "active_count": 0}
    active_reasons = {"recent_mcp_cwd_activity", "external_process_targets_path"}
    for repo_name, repo, _scope in DEFAULT_REPOS:
        if repo_names is not None and repo_name not in repo_names:
            continue
        if not repo.exists():
            continue
        candidates, _cache, observations = scan_repo(repo_name, repo, window_seconds, require_contained=True)
        actions = observations + [Action(repo_name, str(item.path), "SAFE_REAP", item.branch, item.head, "clean_idle_durably_anchored") for item in candidates]
        reasons = [row.reason or "" for row in actions]
        row = {
            "repo": repo_name,
            "auxiliary_count": len(actions),
            "dirty_count": sum(reason.startswith("dirty") for reason in reasons),
            "contained_dirty_count": sum(reason in {"dirty_redundant_in_origin_main", "dirty_unique_contained_in_origin_main", "dirty_contained_unclassified"} for reason in reasons),
            "redundant_dirty_count": reasons.count("dirty_redundant_in_origin_main"),
            "unique_dirty_count": sum(reason in {"dirty_unique_contained_in_origin_main", "dirty_contained_unclassified", "dirty"} for reason in reasons),
            "safe_reap_count": len(candidates),
            "active_count": sum(reason in active_reasons or reason.startswith("git_worktree_locked:") for reason in reasons),
            "actions": [action.__dict__ for action in actions],
        }
        repos.append(row)
        for key in totals:
            totals[key] += row[key]
    return {**totals, "repos": repos}


def converge(
    *,
    apply: bool,
    max_rounds: int,
    stable_rounds: int,
    settle_seconds: float,
    window_seconds: int,
    actor: str,
    safe_auto: bool = False,
    pressure_auto: bool = False,
    repo_names: set[str] | None = None,
) -> dict[str, Any]:
    existing_repos = [
        (name, path, scope)
        for name, path, scope in DEFAULT_REPOS
        if path.exists() and (repo_names is None or name in repo_names)
    ]
    effective_apply = apply or safe_auto or pressure_auto
    if not existing_repos:
        raise RuntimeError("no configured repositories exist")
    before_free = disk_free_gb(existing_repos[0][1])
    actions: list[Action] = []
    stable = 0
    rounds_run = 0

    for round_no in range(1, max_rounds + 1):
        rounds_run = round_no
        round_progress = 0
        round_candidates = 0
        for repo_name, repo, scope in existing_repos:
            # Missing worktree directories leave prunable Git metadata behind. In apply mode,
            # clear only that stale registration before scanning so a vanished temp lane cannot
            # crash cleanliness probes or block unrelated safe cleanup. Git worktree prune never
            # removes a live worktree directory or branch.
            if effective_apply:
                _git(repo, "worktree", "prune", check=False)
            candidates, cache_candidates, observations = scan_repo(
                repo_name,
                repo,
                window_seconds,
                require_contained=(safe_auto or pressure_auto),
                allow_generated_cache=pressure_auto or not (safe_auto or pressure_auto),
            )
            if safe_auto:
                cache_candidates = []
            actions.extend(observations)
            round_candidates += len(candidates) + len(cache_candidates)
            if not effective_apply:
                actions.extend(Action(repo_name, str(item.path), "WOULD_REMOVE", item.branch, item.head) for item in candidates)
                actions.extend(
                    Action(repo_name, str(item.path), "WOULD_CLEAN_GENERATED_CACHE", item.branch, item.head, f"dirs={len(generated_cache_dirs(item.path))}")
                    for item in cache_candidates
                )
                continue

            if candidates:
                claimed, detail = busy_claim(actor, scope)
                if not claimed:
                    actions.append(Action(repo_name, str(repo), "BLOCKED", reason=f"busy_claim_failed:{detail}"))
                else:
                    removed_here = 0
                    try:
                        for item in candidates:
                            branch_scope = _branch_ref_scope(scope, item)
                            if branch_scope:
                                branch_claimed, branch_detail = busy_claim(actor, branch_scope)
                                if not branch_claimed:
                                    actions.append(
                                        Action(
                                            repo_name,
                                            str(item.path),
                                            "BLOCKED",
                                            item.branch,
                                            item.head,
                                            f"branch_busy_claim_failed:{branch_detail}",
                                        )
                                    )
                                    continue
                            try:
                                result = _remove_one(repo_name, repo, item, window_seconds)
                                actions.append(result)
                                if result.action in {"REMOVED_WORKTREE", "REMOVED_RESIDUE"}:
                                    round_progress += 1
                                    removed_here += 1
                            finally:
                                if branch_scope:
                                    busy_release(
                                        actor,
                                        branch_scope,
                                        f"cleanup converger round {round_no}: candidate branch-ref guard for {item.path.name}",
                                    )
                        _git(repo, "worktree", "prune", check=False)
                    finally:
                        busy_release(
                            actor,
                            scope,
                            f"cleanup converger round {round_no}: removed {removed_here}; non-force branch-preserving operator cleanup",
                        )

            for item in cache_candidates:
                cache_scope = _cache_scope(repo_name, item)
                claimed, detail = busy_claim(actor, cache_scope)
                if not claimed:
                    actions.append(Action(repo_name, str(item.path), "BLOCKED", item.branch, item.head, f"cache_busy_claim_failed:{detail}"))
                    continue
                try:
                    result = _clean_generated_cache_one(repo_name, repo, item, window_seconds)
                    actions.append(result)
                    if result.action == "CLEANED_GENERATED_CACHE":
                        round_progress += 1
                finally:
                    busy_release(
                        actor,
                        cache_scope,
                        f"cleanup converger round {round_no}: generated-cache pass for {item.path.name}; ignored Unreal build outputs only",
                    )

        if not effective_apply:
            break
        if round_progress:
            stable = 0
        else:
            stable += 1
        if stable >= stable_rounds:
            break
        if round_no < max_rounds and settle_seconds > 0:
            time.sleep(settle_seconds)

    after_free = disk_free_gb(existing_repos[0][1])
    summary = summarize_actions(actions)
    return {
        "mode": "pressure-auto" if pressure_auto else ("safe-auto" if safe_auto else ("apply" if apply else "dry-run")),
        "operator_only": bool(apply and not safe_auto and not pressure_auto),
        "safe_auto": safe_auto,
        "pressure_auto": pressure_auto,
        "rounds_run": rounds_run,
        "stable_rounds_required": stable_rounds,
        **{key: summary[key] for key in ("removed_count", "generated_cache_cleanup_count", "blocked_count")},
        "disk_free_before_gb": before_free,
        "disk_free_after_gb": after_free,
        "disk_free_delta_gb": round(after_free - before_free, 1),
        "action_events_total": len(actions),
        "progress_events": summary["progress_events"],
        "actions": summary["actions"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply safe non-force removals; default is dry-run")
    parser.add_argument("--safe-auto", action="store_true", help="worker-safe: remove only clean idle worktrees already contained in cached origin/main")
    parser.add_argument("--pressure-auto", action="store_true", help="bounded pressure pass: safe-auto worktree convergence plus guarded P3 ignored generated-cache reclaim")
    parser.add_argument("--operator-ack", action="store_true", help="required with --apply; not required for automatic bounded modes")
    parser.add_argument("--repo", action="append", choices=[name for name, _path, _scope in DEFAULT_REPOS], help="limit to one or more configured repos")
    parser.add_argument("--max-rounds", type=int, default=8)
    parser.add_argument("--stable-rounds", type=int, default=2)
    parser.add_argument("--settle-seconds", type=float, default=5.0)
    parser.add_argument("--activity-window-seconds", type=int, default=300)
    parser.add_argument("--actor", default="ChatGPT:operator-cleanup-converger")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    automatic_modes = int(bool(args.safe_auto)) + int(bool(args.pressure_auto))
    if (args.apply and automatic_modes) or automatic_modes > 1:
        print("ERROR: choose exactly one of --apply, --safe-auto, or --pressure-auto", file=sys.stderr)
        return 2
    if args.apply and not args.operator_ack:
        print("ERROR: --apply requires --operator-ack; workers must not self-administer sibling lanes", file=sys.stderr)
        return 2
    if args.max_rounds < 1 or args.stable_rounds < 1 or args.activity_window_seconds < 1 or args.settle_seconds < 0:
        print("ERROR: invalid convergence bounds", file=sys.stderr)
        return 2
    result = converge(
        apply=args.apply,
        max_rounds=args.max_rounds,
        stable_rounds=args.stable_rounds,
        settle_seconds=args.settle_seconds,
        window_seconds=args.activity_window_seconds,
        actor=args.actor,
        safe_auto=args.safe_auto,
        pressure_auto=args.pressure_auto,
        repo_names=set(args.repo) if args.repo else None,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
