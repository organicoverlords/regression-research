#!/usr/bin/env python3
"""Generic OMEN-first execution for portable source/test workloads.

The routing cohort still owns machine admission. This helper only provides the
missing generic OMEN execution surface: it snapshots the current Git working
copy (tracked + untracked, excluding ignored files) into an atomic NVMe
workspace and executes one Linux-compatible command there over one SSH session.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tarfile
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm_route

DEFAULT_MAX_SYNC_MB = 768
OMEN_WORK_ROOT = PurePosixPath("/mnt/ue/worker-workspaces")
OMEN_TOOL_ENV = "/mnt/ue/worker-tools/env.sh"
OMEN_PYTHON_PACKAGES = "/mnt/ue/worker-tools/python-packages"


def _run(args: list[str], *, cwd: Path | None = None, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(cwd) if cwd else None, capture_output=True, text=True, timeout=timeout, check=False)


def safe_work_id(work_id: str) -> str:
    if not swarm_route.WORK_ID_RE.fullmatch(work_id):
        raise ValueError("SWARM_EXEC_BAD_WORK_ID")
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", work_id).strip("._-")
    if not safe:
        raise ValueError("SWARM_EXEC_BAD_WORK_ID")
    return safe[:96]


def git_root(path: Path) -> Path:
    cp = _run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], timeout=8.0)
    if cp.returncode != 0:
        raise ValueError("SWARM_EXEC_GIT_ROOT_REQUIRED")
    return Path(cp.stdout.strip()).resolve()


def snapshot_paths(repo_root: Path) -> list[Path]:
    submodules = _run(["git", "-C", str(repo_root), "ls-files", "-s", "-z"], timeout=20.0)
    if submodules.returncode != 0:
        raise ValueError("SWARM_EXEC_GIT_INDEX_FAILED")
    for entry in submodules.stdout.split("\0"):
        if entry.startswith("160000 "):
            raise ValueError("SWARM_EXEC_SUBMODULE_UNSUPPORTED")
    cp = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-co", "--exclude-standard", "-z"],
        capture_output=True, timeout=30.0, check=False,
    )
    if cp.returncode != 0:
        raise ValueError("SWARM_EXEC_SNAPSHOT_LIST_FAILED")
    out: list[Path] = []
    seen: set[str] = set()
    for raw in cp.stdout.decode("utf-8", errors="surrogateescape").split("\0"):
        if not raw or raw in seen:
            continue
        seen.add(raw)
        rel = Path(raw)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("SWARM_EXEC_UNSAFE_REPO_PATH")
        full = repo_root / rel
        if full.is_file() or full.is_symlink():
            out.append(rel)
    return out


def snapshot_bytes(repo_root: Path, paths: Iterable[Path]) -> int:
    total = 0
    for rel in paths:
        try:
            total += (repo_root / rel).lstat().st_size
        except FileNotFoundError:
            continue
    return total


def ssh_args() -> list[str]:
    key = Path.home() / ".ssh" / "chatgpt-linux-aatuska-ed25519"
    if not key.is_file():
        raise ValueError("SWARM_EXEC_SSH_KEY_MISSING")
    return [
        "ssh", "-F", "NUL", "-4", "-i", str(key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        "-o", f"HostKeyAlias={swarm_route.OMEN_HOST_KEY_ALIAS}",
        f"{swarm_route.OMEN_USER}@{swarm_route.OMEN_HOST}",
    ]


def remote_script(work_id: str, command: str, *, keep_workspace: bool = False) -> tuple[str, str]:
    safe = safe_work_id(work_id)
    final = str(OMEN_WORK_ROOT / safe)
    incoming = final + ".incoming"
    previous = final + ".previous"
    keep = 1 if keep_workspace else 0
    script = f"""set -eu
final={shlex.quote(final)}
incoming={shlex.quote(incoming)}
previous={shlex.quote(previous)}
keep_workspace={keep}
published=0
cleanup() {{
  rc=$?
  trap - EXIT
  rm -rf -- \"$incoming\"
  if [ \"$published\" -eq 0 ] && [ -e \"$previous\" ] && [ ! -e \"$final\" ]; then
    mv -- \"$previous\" \"$final\"
  fi
  rm -rf -- \"$previous\"
  if [ \"$keep_workspace\" -eq 0 ] && [ \"$published\" -eq 1 ]; then
    rm -rf -- \"$final\"
  fi
  exit \"$rc\"
}}
trap cleanup EXIT
rm -rf -- \"$incoming\"
mkdir -p -- \"$incoming\"
tar -xf - -C \"$incoming\"
rm -rf -- \"$previous\"
if [ -e \"$final\" ]; then mv -- \"$final\" \"$previous\"; fi
mv -- \"$incoming\" \"$final\"
published=1
. {shlex.quote(OMEN_TOOL_ENV)}
export PYTHONPATH={shlex.quote(OMEN_PYTHON_PACKAGES)}:${{PYTHONPATH:-}}
cd -- \"$final\"
set +e
bash -c {shlex.quote(command)}
rc=$?
set -e
exit \"$rc\"
"""
    return final, script


def execute_omen(repo_root: Path, work_id: str, command: str, max_sync_mb: int, *, keep_workspace: bool = False) -> int:
    paths = snapshot_paths(repo_root)
    size = snapshot_bytes(repo_root, paths)
    limit = max_sync_mb * 1024 * 1024
    if size > limit:
        raise ValueError(f"SWARM_EXEC_SNAPSHOT_TOO_LARGE bytes={size} limit={limit}")
    workspace, script = remote_script(work_id, command, keep_workspace=keep_workspace)
    print(json.dumps({
        "event": "SWARM_EXEC_OMEN_START", "work_id": work_id, "workspace": workspace,
        "snapshot_files": len(paths), "snapshot_bytes": size,
    }, separators=(",", ":")), file=sys.stderr, flush=True)
    proc = subprocess.Popen(ssh_args() + [script], stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        with tarfile.open(fileobj=proc.stdin, mode="w|") as tf:
            for rel in paths:
                full = repo_root / rel
                if full.exists() or full.is_symlink():
                    tf.add(full, arcname=rel.as_posix(), recursive=False)
        proc.stdin.close()
    except BrokenPipeError:
        with contextlib.suppress(Exception):
            proc.stdin.close()
    rc = proc.wait()
    print(json.dumps({"event": "SWARM_EXEC_OMEN_DONE", "work_id": work_id, "exit_code": rc}, separators=(",", ":")), file=sys.stderr, flush=True)
    return rc


def command_from_args(args: argparse.Namespace) -> str:
    if args.command:
        if args.argv:
            raise ValueError("SWARM_EXEC_COMMAND_AMBIGUOUS")
        return args.command
    argv = list(args.argv or [])
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise ValueError("SWARM_EXEC_COMMAND_REQUIRED")
    return shlex.join(argv)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Execute portable work on the cohort-assigned OMEN NVMe workspace")
    p.add_argument("--state", type=Path, default=swarm_route.default_state_path())
    p.add_argument("--work-id", required=True)
    p.add_argument("--kind", choices=("portable", "portable-light"), default="portable")
    p.add_argument("--repo-root", type=Path, default=Path.cwd())
    p.add_argument("--command")
    p.add_argument("--max-sync-mb", type=int, default=DEFAULT_MAX_SYNC_MB)
    p.add_argument("--refresh-probe", action="store_true")
    p.add_argument("--keep-lease", action="store_true")
    p.add_argument("--keep-workspace", action="store_true", help="retain the OMEN snapshot after execution for debugging")
    p.add_argument("argv", nargs=argparse.REMAINDER)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.max_sync_mb < 1 or args.max_sync_mb > 8192:
            raise ValueError("SWARM_EXEC_BAD_SYNC_LIMIT")
        command = command_from_args(args)
        root = git_root(args.repo_root)
        assignment = swarm_route.route_work(args.state, args.work_id, args.kind, swarm_route.DEFAULT_TTL_SECONDS, args.refresh_probe)
        print(json.dumps({
            "event": "SWARM_EXEC_ROUTE", "work_id": args.work_id, "kind": args.kind,
            "route": assignment.get("route"), "reason": assignment.get("reason"),
            "decision_id": assignment.get("decision_id"),
        }, separators=(",", ":")), file=sys.stderr, flush=True)
        try:
            if assignment.get("route") != "omen":
                print(json.dumps({"error": "SWARM_EXEC_NON_OMEN_ASSIGNMENT", "route": assignment.get("route"), "reason": assignment.get("reason")}), file=sys.stderr)
                return 75
            return execute_omen(root, args.work_id, command, args.max_sync_mb, keep_workspace=args.keep_workspace)
        finally:
            if not args.keep_lease:
                swarm_route.release_work(args.state, args.work_id)
    except (ValueError, TimeoutError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
