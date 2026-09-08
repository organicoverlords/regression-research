#!/usr/bin/env python3
"""Generic OMEN-first execution for portable source/test workloads.

The routing cohort still owns machine admission. This helper only provides the
missing generic OMEN execution surface. It keeps a per-repository acceleration
cache on OMEN NVMe, transfers only content changes after the cache is warm, then
copies that cache into an isolated ephemeral workspace before running one
Linux-compatible command. The cache is never the command's writable workspace.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import stat
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
OMEN_CACHE_ROOT = PurePosixPath("/mnt/ue/worker-cache")
CACHE_MANIFEST_NAME = ".swarm-exec-manifest.json"
CACHE_CONTROL_NAME = ".swarm-exec-control.json"
CACHE_PROTOCOL_PREFIX = b"SWARM_EXEC_CACHE_MANIFEST "
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


def repo_cache_id(repo_root: Path) -> str:
    cp = _run(["git", "-C", str(repo_root), "config", "--get", "remote.origin.url"], timeout=5.0)
    if cp.returncode == 0 and cp.stdout.strip():
        identity = "origin\0" + cp.stdout.strip()
    else:
        identity = "path\0" + str(repo_root.resolve()).casefold()
    return hashlib.sha256(identity.encode("utf-8", errors="surrogatepass")).hexdigest()[:24]


def _safe_manifest_path(raw: str) -> PurePosixPath:
    rel = PurePosixPath(raw)
    if not raw or rel.is_absolute() or ".." in rel.parts:
        raise ValueError("SWARM_EXEC_UNSAFE_REPO_PATH")
    if raw in (CACHE_MANIFEST_NAME, CACHE_CONTROL_NAME):
        raise ValueError("SWARM_EXEC_RESERVED_REPO_PATH")
    return rel


def snapshot_manifest(repo_root: Path, paths: Iterable[Path]) -> dict[str, dict[str, int | str]]:
    manifest: dict[str, dict[str, int | str]] = {}
    for rel in paths:
        name = rel.as_posix()
        _safe_manifest_path(name)
        full = repo_root / rel
        try:
            st = full.lstat()
        except FileNotFoundError:
            continue
        mode = stat.S_IMODE(st.st_mode)
        if stat.S_ISLNK(st.st_mode):
            target = os.fsencode(os.readlink(full))
            digest = hashlib.sha256(target).hexdigest()
            manifest[name] = {"type": "symlink", "sha256": digest, "size": len(target), "mode": mode, "mtime_ns": st.st_mtime_ns}
        elif stat.S_ISREG(st.st_mode):
            h = hashlib.sha256()
            with full.open("rb") as fh:
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    h.update(chunk)
            manifest[name] = {"type": "file", "sha256": h.hexdigest(), "size": st.st_size, "mode": mode, "mtime_ns": st.st_mtime_ns}
    return manifest


def parse_remote_manifest(line: bytes) -> dict[str, dict[str, int | str]]:
    if not line.startswith(CACHE_PROTOCOL_PREFIX):
        raise ValueError("SWARM_EXEC_CACHE_PROTOCOL_FAILED")
    try:
        value = json.loads(line[len(CACHE_PROTOCOL_PREFIX):].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("SWARM_EXEC_CACHE_MANIFEST_INVALID") from exc
    if not isinstance(value, dict):
        raise ValueError("SWARM_EXEC_CACHE_MANIFEST_INVALID")
    for raw, entry in value.items():
        if not isinstance(raw, str) or not isinstance(entry, dict):
            raise ValueError("SWARM_EXEC_CACHE_MANIFEST_INVALID")
        _safe_manifest_path(raw)
    return value


def _content_identity(entry: dict[str, int | str] | None) -> tuple[object, ...] | None:
    if entry is None:
        return None
    return (entry.get("type"), entry.get("sha256"), entry.get("size"))


def manifest_delta(
    current: dict[str, dict[str, int | str]], remote: dict[str, dict[str, int | str]]
) -> tuple[list[Path], list[str]]:
    changed = [Path(raw) for raw, entry in current.items() if _content_identity(remote.get(raw)) != _content_identity(entry)]
    deleted = sorted(set(remote) - set(current))
    return changed, deleted


def _add_control_member(tf: tarfile.TarFile, manifest: dict[str, dict[str, int | str]], changed: list[Path], deleted: list[str]) -> None:
    data = json.dumps(
        {"manifest": manifest, "changed": [p.as_posix() for p in changed], "deleted": deleted},
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    info = tarfile.TarInfo(CACHE_CONTROL_NAME)
    info.size = len(data)
    info.mode = 0o600
    tf.addfile(info, io.BytesIO(data))

def ssh_args() -> list[str]:
    key = Path.home() / ".ssh" / "chatgpt-linux-aatuska-ed25519"
    if not key.is_file():
        raise ValueError("SWARM_EXEC_SSH_KEY_MISSING")
    return [
        "ssh", "-F", "NUL", "-4", "-i", str(key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        "-o", f"HostKeyAlias={swarm_route.OMEN_HOST_KEY_ALIAS}",
        f"{swarm_route.OMEN_USER}@{swarm_route.OMEN_HOST}",
    ]


def remote_script(work_id: str, command: str, cache_id: str, *, keep_workspace: bool = False) -> tuple[str, str]:
    safe = safe_work_id(work_id)
    if not re.fullmatch(r"[0-9a-f]{24}", cache_id):
        raise ValueError("SWARM_EXEC_BAD_CACHE_ID")
    final = str(OMEN_WORK_ROOT / safe)
    cache = str(OMEN_CACHE_ROOT / cache_id)
    cache_incoming = cache + f".incoming-{safe}-$$"
    cache_previous = cache + f".previous-{safe}-$$"
    cache_lock = cache + ".lock"
    payload = cache + f".payload-{safe}-$$.tar"
    keep = 1 if keep_workspace else 0
    script = f"""set -eu
final={shlex.quote(final)}
cache={shlex.quote(cache)}
cache_incoming={shlex.quote(cache_incoming)}
cache_previous={shlex.quote(cache_previous)}
cache_lock={shlex.quote(cache_lock)}
payload={shlex.quote(payload)}
manifest_name={shlex.quote(CACHE_MANIFEST_NAME)}
control_name={shlex.quote(CACHE_CONTROL_NAME)}
keep_workspace={keep}
published=0
cleanup() {{
  rc=$?
  trap - EXIT
  rm -f -- \"$payload\"
  rm -rf -- \"$cache_incoming\" \"$cache_previous\"
  if [ \"$keep_workspace\" -eq 0 ] && [ \"$published\" -eq 1 ]; then
    rm -rf -- \"$final\"
  fi
  exit \"$rc\"
}}
trap cleanup EXIT
mkdir -p -- {shlex.quote(str(OMEN_CACHE_ROOT))} {shlex.quote(str(OMEN_WORK_ROOT))}
exec 9>\"$cache_lock\"
flock 9
if [ -d \"$cache\" ] && [ -f \"$cache/$manifest_name\" ]; then
  printf 'SWARM_EXEC_CACHE_MANIFEST '
  cat \"$cache/$manifest_name\"
else
  printf '%s\\n' 'SWARM_EXEC_CACHE_MANIFEST {{}}'
fi
rm -rf -- \"$cache_incoming\" \"$cache_previous\"
mkdir -p -- \"$cache_incoming\"
if [ -d \"$cache\" ]; then cp -a -- \"$cache/.\" \"$cache_incoming/\"; fi
cat > \"$payload\"
tar -xf \"$payload\" -C \"$cache_incoming\" \"$control_name\"
python3 - \"$cache_incoming\" \"$control_name\" \"$manifest_name\" <<'PY'
import json, shutil, sys
from pathlib import Path, PurePosixPath
root=Path(sys.argv[1]); control_name=sys.argv[2]; manifest_name=sys.argv[3]
control=root/control_name
meta=json.loads(control.read_text(encoding='utf-8'))
def safe(raw):
    rel=PurePosixPath(raw)
    if not raw or rel.is_absolute() or '..' in rel.parts or raw in (control_name, manifest_name):
        raise SystemExit('SWARM_EXEC_REMOTE_UNSAFE_PATH')
    return rel
def remove_path(rel):
    p=root.joinpath(*safe(rel).parts)
    if p.is_symlink() or p.is_file():
        p.unlink(missing_ok=True)
    elif p.is_dir():
        shutil.rmtree(p)
for raw in meta.get('deleted', []): remove_path(raw)
for raw in meta.get('changed', []): remove_path(raw)
control.unlink(missing_ok=True)
(root/manifest_name).write_text(json.dumps(meta['manifest'],separators=(',',':'),sort_keys=True)+'\\n',encoding='utf-8')
PY
tar -xf \"$payload\" -C \"$cache_incoming\" --exclude=\"$control_name\"
python3 - \"$cache_incoming\" \"$manifest_name\" <<'PY'
import json, os, stat, sys
from pathlib import Path, PurePosixPath
root=Path(sys.argv[1]); manifest_name=sys.argv[2]
manifest=json.loads((root/manifest_name).read_text(encoding='utf-8'))
for raw, meta in manifest.items():
    rel=PurePosixPath(raw)
    if not raw or rel.is_absolute() or '..' in rel.parts:
        raise SystemExit('SWARM_EXEC_REMOTE_UNSAFE_PATH')
    p=root.joinpath(*rel.parts)
    if meta.get('type') == 'file' and p.is_file() and not p.is_symlink():
        os.chmod(p, int(meta.get('mode', 0o644)))
    try:
        ns=int(meta.get('mtime_ns', 0))
        if ns > 0: os.utime(p, ns=(ns,ns), follow_symlinks=False)
    except (NotImplementedError, PermissionError, FileNotFoundError):
        pass
PY
rm -f -- \"$payload\"
if [ -d \"$cache\" ]; then mv -- \"$cache\" \"$cache_previous\"; fi
if mv -- \"$cache_incoming\" \"$cache\"; then
  rm -rf -- \"$cache_previous\"
else
  if [ -d \"$cache_previous\" ] && [ ! -e \"$cache\" ]; then mv -- \"$cache_previous\" \"$cache\"; fi
  exit 74
fi
rm -rf -- \"$final\"
cp -a -- \"$cache\" \"$final\"
rm -f -- \"$final/$manifest_name\"
published=1
flock -u 9
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


def _forward_stdout(stream) -> None:
    if stream is None:
        return
    target = getattr(sys.stdout, "buffer", None)
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        if target is not None:
            target.write(chunk); target.flush()
        else:
            sys.stdout.write(chunk.decode("utf-8", errors="replace")); sys.stdout.flush()


def execute_omen(repo_root: Path, work_id: str, command: str, max_sync_mb: int, *, keep_workspace: bool = False) -> int:
    paths = snapshot_paths(repo_root)
    size = snapshot_bytes(repo_root, paths)
    limit = max_sync_mb * 1024 * 1024
    if size > limit:
        raise ValueError(f"SWARM_EXEC_SNAPSHOT_TOO_LARGE bytes={size} limit={limit}")
    current_manifest = snapshot_manifest(repo_root, paths)
    cache_id = repo_cache_id(repo_root)
    workspace, script = remote_script(work_id, command, cache_id, keep_workspace=keep_workspace)
    proc = subprocess.Popen(ssh_args() + [script], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    assert proc.stdin is not None and proc.stdout is not None
    try:
        line = proc.stdout.readline()
        remote_manifest = parse_remote_manifest(line)
        changed, deleted = manifest_delta(current_manifest, remote_manifest)
        delta_size = snapshot_bytes(repo_root, changed)
        print(json.dumps({
            "event": "SWARM_EXEC_OMEN_START", "work_id": work_id, "workspace": workspace,
            "snapshot_files": len(paths), "snapshot_bytes": size, "cache_id": cache_id,
            "cache_hit": bool(remote_manifest), "delta_files": len(changed), "delta_bytes": delta_size,
            "deleted_files": len(deleted),
        }, separators=(",", ":")), file=sys.stderr, flush=True)
        with tarfile.open(fileobj=proc.stdin, mode="w|") as tf:
            _add_control_member(tf, current_manifest, changed, deleted)
            for rel in changed:
                full = repo_root / rel
                if full.exists() or full.is_symlink():
                    tf.add(full, arcname=rel.as_posix(), recursive=False)
        proc.stdin.close()
        _forward_stdout(proc.stdout)
    except BrokenPipeError:
        with contextlib.suppress(Exception):
            proc.stdin.close()
    except Exception:
        with contextlib.suppress(Exception):
            proc.stdin.close()
        with contextlib.suppress(Exception):
            proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=2)
        raise
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
