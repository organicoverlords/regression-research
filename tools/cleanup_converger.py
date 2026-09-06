#!/usr/bin/env python3
"""Converge redundant P3/Vault worktrees to a bounded safe boundary.

Operator-only cleanup. The command never force-removes a worktree, deletes a
branch, resets/rebases, fetches, or discards dirty/unanchored state. It loops
internally so a single invocation can absorb lanes that become safely idle
while it is running.
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
    ("Vault", Path(r"C:\Users\Lauri\Desktop\vault"), "regression-research:git-worktree-metadata"),
)


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


def _run(command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", "-C", str(repo), *args], check=check)


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
    # Reuse Stack Atlas' bounded tail reader and the same canonical newest
    # transport source. Recursive enumeration of every historical clone made a
    # single cleanup round take tens of seconds and did not improve authority.
    try:
        from tools.stack_atlas import _read_jsonl_window
    except ModuleNotFoundError:  # direct `python tools\cleanup_converger.py` entrypoint
        from stack_atlas import _read_jsonl_window

    now_ts = time.time() if now is None else now
    cutoff_dt = datetime.fromtimestamp(now_ts, timezone.utc) - timedelta(seconds=window_seconds)
    result: set[str] = set()
    if not log_root.exists():
        return result
    try:
        logs = sorted(
            log_root.glob("clone-*/transport.jsonl"),
            key=lambda candidate: candidate.stat().st_mtime if candidate.exists() else 0,
            reverse=True,
        )
    except OSError:
        return result
    if not logs:
        return result
    source = logs[0]
    archive_dir = source.with_name(f"{source.name}.archive")
    if archive_dir.is_dir():
        try:
            newest_archive = max(
                (candidate for candidate in archive_dir.iterdir() if candidate.is_file() and candidate.suffix.lower() == ".jsonl"),
                key=lambda candidate: candidate.stat().st_mtime,
                default=None,
            )
            if newest_archive is not None and newest_archive.stat().st_mtime > source.stat().st_mtime:
                source = newest_archive
        except OSError:
            pass
    try:
        rows, _complete, _sample_bytes = _read_jsonl_window(source, cutoff_dt)
    except OSError:
        return result
    cutoff_ts = cutoff_dt.timestamp()
    for event in rows:
        if not isinstance(event, dict):
            continue
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


def worktree_is_clean(path: Path) -> bool:
    for args in (("diff-files", "--quiet", "--"), ("diff-index", "--cached", "--quiet", "HEAD", "--")):
        completed = _git(path, *args, check=False)
        if completed.returncode == 1:
            return False
        if completed.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed for {path}: {completed.stderr.strip()}")
    process = subprocess.Popen(
        ["git", "-C", str(path), "ls-files", "--others", "--exclude-standard", "-z"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    first = process.stdout.read(1)
    if first:
        process.kill()
        process.communicate()
        return False
    _stdout, stderr = process.communicate()
    if process.returncode:
        raise RuntimeError(f"git ls-files failed for {path}: {stderr.decode(errors='replace').strip()}")
    return True


def branch_ref_matches(repo: Path, worktree: Worktree) -> bool:
    if worktree.detached or not worktree.branch or not worktree.head:
        return False
    completed = _git(repo, "rev-parse", f"refs/heads/{worktree.branch}", check=False)
    return completed.returncode == 0 and completed.stdout.strip() == worktree.head


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
    if worktree.detached or not worktree.branch:
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
    if not worktree_is_clean(worktree.path):
        return "dirty"
    if not branch_ref_matches(repo, worktree):
        return "branch_ref_mismatch"
    return None


def _remove_one(repo_name: str, repo: Path, worktree: Worktree, window_seconds: int) -> Action:
    reason = _fresh_guard(repo, worktree, window_seconds)
    if reason:
        return Action(repo_name, str(worktree.path), "SKIP", worktree.branch, worktree.head, reason)

    completed = _git(repo, "worktree", "remove", str(worktree.path), check=False)
    if completed.returncode == 0:
        if not branch_ref_matches(repo, worktree):
            raise RuntimeError(f"branch anchor changed after removal: {worktree.branch} {worktree.head}")
        return Action(repo_name, str(worktree.path), "REMOVED_WORKTREE", worktree.branch, worktree.head)

    # Windows can detach worktree metadata before filesystem deletion fails. Only
    # finish such a residue when the exact branch anchor remains and fresh live
    # activity checks are clear. Otherwise leave it untouched.
    if _norm_path(worktree.path) in registered_paths(repo):
        return Action(repo_name, str(worktree.path), "BLOCKED", worktree.branch, worktree.head, "git_remove_failed_registered")
    if (worktree.path / ".git").exists() or not branch_ref_matches(repo, worktree):
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


def scan_repo(repo_name: str, repo: Path, window_seconds: int) -> tuple[list[Worktree], list[Action]]:
    worktrees = parse_worktrees(_git(repo, "worktree", "list", "--porcelain").stdout)
    recent = recent_mcp_cwds(window_seconds)
    processes = windows_processes()
    candidates: list[Worktree] = []
    observations: list[Action] = []
    for worktree in worktrees[1:]:
        # Cheap guards first: do not run expensive status checks on active or
        # detached/unanchored lanes that can never be removed by this tool.
        preliminary = eligibility_reason(
            worktree,
            recent_cwds=recent,
            processes=processes,
            clean=None,
            ref_matches=branch_ref_matches(repo, worktree),
        )
        if preliminary and (preliminary.startswith("git_worktree_locked:") or preliminary in {"detached_or_unanchored", "recent_mcp_cwd_activity", "external_process_targets_path", "branch_ref_mismatch"}):
            observations.append(Action(repo_name, str(worktree.path), "PRESERVE", worktree.branch, worktree.head, preliminary))
            continue
        clean = worktree_is_clean(worktree.path)
        reason = eligibility_reason(
            worktree,
            recent_cwds=recent,
            processes=processes,
            clean=clean,
            ref_matches=True,
        )
        if reason:
            observations.append(Action(repo_name, str(worktree.path), "PRESERVE", worktree.branch, worktree.head, reason))
        else:
            candidates.append(worktree)
    return candidates, observations


def converge(
    *,
    apply: bool,
    max_rounds: int,
    stable_rounds: int,
    settle_seconds: float,
    window_seconds: int,
    actor: str,
) -> dict[str, Any]:
    existing_repos = [(name, path, scope) for name, path, scope in DEFAULT_REPOS if path.exists()]
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
            candidates, observations = scan_repo(repo_name, repo, window_seconds)
            actions.extend(observations)
            round_candidates += len(candidates)
            if not candidates:
                continue
            if not apply:
                actions.extend(Action(repo_name, str(item.path), "WOULD_REMOVE", item.branch, item.head) for item in candidates)
                continue

            claimed, detail = busy_claim(actor, scope)
            if not claimed:
                actions.append(Action(repo_name, str(repo), "BLOCKED", reason=f"busy_claim_failed:{detail}"))
                continue
            removed_here = 0
            try:
                for item in candidates:
                    result = _remove_one(repo_name, repo, item, window_seconds)
                    actions.append(result)
                    if result.action in {"REMOVED_WORKTREE", "REMOVED_RESIDUE"}:
                        round_progress += 1
                        removed_here += 1
                _git(repo, "worktree", "prune", check=False)
            finally:
                busy_release(
                    actor,
                    scope,
                    f"cleanup converger round {round_no}: removed {removed_here}; non-force branch-preserving operator cleanup",
                )

        if not apply:
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
    final_by_path: dict[tuple[str, str], Action] = {}
    for row in actions:
        final_by_path[(row.repo, row.path)] = row
    compact_actions = list(final_by_path.values())
    removed = [row for row in compact_actions if row.action in {"REMOVED_WORKTREE", "REMOVED_RESIDUE"}]
    blocked = [row for row in compact_actions if row.action == "BLOCKED"]
    return {
        "mode": "apply" if apply else "dry-run",
        "operator_only": True,
        "rounds_run": rounds_run,
        "stable_rounds_required": stable_rounds,
        "removed_count": len(removed),
        "blocked_count": len(blocked),
        "disk_free_before_gb": before_free,
        "disk_free_after_gb": after_free,
        "disk_free_delta_gb": round(after_free - before_free, 1),
        "action_events_total": len(actions),
        "actions": [row.__dict__ for row in compact_actions],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="apply safe non-force removals; default is dry-run")
    parser.add_argument("--operator-ack", action="store_true", help="required with --apply; workers must not self-administer sibling lanes")
    parser.add_argument("--max-rounds", type=int, default=8)
    parser.add_argument("--stable-rounds", type=int, default=2)
    parser.add_argument("--settle-seconds", type=float, default=5.0)
    parser.add_argument("--activity-window-seconds", type=int, default=300)
    parser.add_argument("--actor", default="ChatGPT:operator-cleanup-converger")
    return parser


def main() -> int:
    args = build_parser().parse_args()
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
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
