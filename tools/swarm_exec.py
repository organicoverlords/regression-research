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
import base64
import contextlib
import hashlib
import io
import json
import os
import stat
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm_route

DEFAULT_MAX_SYNC_MB = 768
OMEN_WORK_ROOT = PurePosixPath("/mnt/ue/worker-workspaces")
OMEN_CACHE_ROOT = PurePosixPath("/mnt/ue/worker-cache")
CACHE_MANIFEST_NAME = ".swarm-exec-manifest.json"
CACHE_CONTROL_NAME = ".swarm-exec-control.json"
CACHE_PROTOCOL_PREFIX = b"SWARM_EXEC_CACHE_MANIFEST "
GIT_PROVENANCE_VERSION = 1
GIT_PROVENANCE_COMMIT_LIMIT = 128
MAX_GIT_PROVENANCE_BYTES = 16 * 1024 * 1024
OMEN_TOOL_ENV = "/mnt/ue/worker-tools/env.sh"
OMEN_PYTHON_PACKAGES = "/mnt/ue/worker-tools/python-packages"
GHBUF_DEFAULT_LOCAL_ADDR = "127.0.0.1:19427"
GHBUF_REMOTE_PORT_BASE = 20000
GHBUF_REMOTE_PORT_SPAN = 20000


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


def git_provenance_payload(repo_root: Path) -> tuple[dict[str, object], int]:
    """Build bounded ancestry/tree/index metadata for native Git inspection on OMEN."""
    head_cp = _run(["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD^{commit}"], timeout=8.0)
    if head_cp.returncode != 0 or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head_cp.stdout.strip()):
        raise ValueError("SWARM_EXEC_GIT_HEAD_REQUIRED")
    head = head_cp.stdout.strip().lower()
    branch_cp = _run(["git", "-C", str(repo_root), "symbolic-ref", "--quiet", "--short", "HEAD"], timeout=5.0)
    branch = branch_cp.stdout.strip() if branch_cp.returncode == 0 and branch_cp.stdout.strip() else None
    config: dict[str, str] = {}
    for key in ("core.autocrlf", "core.filemode", "core.symlinks", "core.ignorecase"):
        config_cp = _run(["git", "-C", str(repo_root), "config", "--get", key], timeout=5.0)
        value = config_cp.stdout.strip() if config_cp.returncode == 0 else ""
        if value:
            config[key] = value
    history_cp = _run([
        "git", "-C", str(repo_root), "rev-list", f"--max-count={GIT_PROVENANCE_COMMIT_LIMIT}", "--parents", "HEAD"
    ], timeout=20.0)
    objects_cp = _run([
        "git", "-C", str(repo_root), "rev-list", "--objects", "--no-object-names", "--filter=blob:none",
        f"--max-count={GIT_PROVENANCE_COMMIT_LIMIT}", "HEAD"
    ], timeout=30.0)
    head_objects_cp = _run([
        "git", "-C", str(repo_root), "rev-list", "--objects", "--no-object-names", "--max-count=1", "HEAD"
    ], timeout=30.0)
    if (
        history_cp.returncode != 0
        or objects_cp.returncode != 0
        or head_objects_cp.returncode != 0
        or not objects_cp.stdout.strip()
        or not head_objects_cp.stdout.strip()
    ):
        raise ValueError("SWARM_EXEC_GIT_TREE_FAILED")
    history_rows = [line.split() for line in history_cp.stdout.splitlines() if line.strip()]
    commits = [row[0] for row in history_rows if row]
    commit_set = set(commits)
    shallow = sorted({row[0] for row in history_rows if len(row) > 1 and any(parent not in commit_set for parent in row[1:])})
    objects = list(dict.fromkeys(
        line.strip()
        for line in [*objects_cp.stdout.splitlines(), *head_objects_cp.stdout.splitlines()]
        if line.strip()
    ))
    pack_proc = subprocess.run(
        ["git", "-C", str(repo_root), "pack-objects", "--stdout"],
        input=("\n".join(objects) + "\n").encode("ascii"), capture_output=True, timeout=30.0, check=False,
    )
    if pack_proc.returncode != 0 or not pack_proc.stdout:
        raise ValueError("SWARM_EXEC_GIT_OBJECT_PACK_FAILED")
    index_proc = subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "-s", "-z"],
        capture_output=True, timeout=30.0, check=False,
    )
    if index_proc.returncode != 0:
        raise ValueError("SWARM_EXEC_GIT_INDEX_FAILED")
    payload: dict[str, object] = {
        "version": GIT_PROVENANCE_VERSION,
        "head": head,
        "branch": branch,
        "config": config,
        "shallow": shallow,
        "pack_b64": base64.b64encode(pack_proc.stdout).decode("ascii"),
        "index_b64": base64.b64encode(index_proc.stdout).decode("ascii"),
    }
    encoded_size = len(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    if encoded_size > MAX_GIT_PROVENANCE_BYTES:
        raise ValueError(f"SWARM_EXEC_GIT_PROVENANCE_TOO_LARGE bytes={encoded_size} limit={MAX_GIT_PROVENANCE_BYTES}")
    return payload, encoded_size


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


LOCAL_HASH_CACHE_VERSION = 1


def local_hash_cache_path(repo_root: Path) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".cache")) / "SwarmRouting" / "swarm-exec-hashes"
    identity = str(repo_root.resolve()).casefold()
    key = hashlib.sha256(identity.encode("utf-8", errors="surrogatepass")).hexdigest()[:24]
    return base / f"{key}.json"


def _local_fingerprint(st: os.stat_result, kind: str) -> list[int | str]:
    return [
        kind,
        int(st.st_size),
        int(stat.S_IMODE(st.st_mode)),
        int(st.st_mtime_ns),
        int(st.st_ctime_ns),
        int(getattr(st, "st_ino", 0)),
        int(getattr(st, "st_dev", 0)),
    ]


def _load_local_hash_cache(path: Path) -> dict[str, dict[str, object]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict) or value.get("version") != LOCAL_HASH_CACHE_VERSION:
        return {}
    entries = value.get("entries")
    return entries if isinstance(entries, dict) else {}


def _write_local_hash_cache(path: Path, entries: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"version": LOCAL_HASH_CACHE_VERSION, "entries": entries}, fh, separators=(",", ":"), sort_keys=True)
            fh.write("\n")
            fh.flush()
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def cached_snapshot_manifest(
    repo_root: Path, paths: Iterable[Path], *, cache_file: Path | None = None
) -> tuple[dict[str, dict[str, int | str]], int, int, int]:
    cache_path = cache_file or local_hash_cache_path(repo_root)
    old = _load_local_hash_cache(cache_path)
    new: dict[str, dict[str, object]] = {}
    manifest: dict[str, dict[str, int | str]] = {}
    total = hits = misses = 0
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
            size = len(target)
            fingerprint = _local_fingerprint(st, "symlink")
            misses += 1
            kind = "symlink"
        elif stat.S_ISREG(st.st_mode):
            kind = "file"
            size = int(st.st_size)
            fingerprint = _local_fingerprint(st, kind)
            cached = old.get(name)
            digest = ""
            if isinstance(cached, dict) and cached.get("fingerprint") == fingerprint:
                candidate = cached.get("sha256")
                if isinstance(candidate, str) and re.fullmatch(r"[0-9a-f]{64}", candidate):
                    digest = candidate
            if digest:
                hits += 1
            else:
                h = hashlib.sha256()
                try:
                    with full.open("rb") as fh:
                        while True:
                            chunk = fh.read(1024 * 1024)
                            if not chunk:
                                break
                            h.update(chunk)
                except FileNotFoundError:
                    continue
                digest = h.hexdigest()
                misses += 1
        else:
            continue
        total += size
        manifest[name] = {"type": kind, "sha256": digest, "size": size, "mode": mode, "mtime_ns": st.st_mtime_ns}
        new[name] = {"fingerprint": fingerprint, "sha256": digest}
    if new != old:
        try:
            _write_local_hash_cache(cache_path, new)
        except OSError:
            pass
    return manifest, total, hits, misses


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


def _add_control_member(
    tf: tarfile.TarFile, manifest: dict[str, dict[str, int | str]], changed: list[Path], deleted: list[str],
    git_provenance: dict[str, object],
) -> None:
    data = json.dumps(
        {"manifest": manifest, "changed": [p.as_posix() for p in changed], "deleted": deleted, "git": git_provenance},
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    info = tarfile.TarInfo(CACHE_CONTROL_NAME)
    info.size = len(data)
    info.mode = 0o600
    tf.addfile(info, io.BytesIO(data))

def _ghbuf_bin() -> str | None:
    found = shutil.which("ghbuf")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / ("ghbuf.exe" if os.name == "nt" else "ghbuf")
    return str(local) if local.is_file() else None


def gh_buffer_local_target() -> tuple[str, int]:
    raw = os.environ.get("GHBUF_ADDR", GHBUF_DEFAULT_LOCAL_ADDR).strip()
    match = re.fullmatch(r"(127\.0\.0\.1|localhost):([0-9]{1,5})", raw, flags=re.IGNORECASE)
    if not match:
        raise ValueError("SWARM_EXEC_GHBUF_LOOPBACK_REQUIRED")
    port = int(match.group(2))
    if port < 1 or port > 65535:
        raise ValueError("SWARM_EXEC_GHBUF_BAD_PORT")
    return "127.0.0.1", port


def select_gh_buffer_remote_port(work_id: str, *, pid: int | None = None) -> int:
    safe_work_id(work_id)
    process_id = os.getpid() if pid is None else pid
    digest = hashlib.sha256(f"{work_id}\0{process_id}".encode("utf-8")).digest()
    return GHBUF_REMOTE_PORT_BASE + int.from_bytes(digest[:4], "big") % GHBUF_REMOTE_PORT_SPAN


def gh_buffer_forward_args(remote_port: int, local_host: str, local_port: int) -> list[str]:
    if local_host != "127.0.0.1":
        raise ValueError("SWARM_EXEC_GHBUF_LOOPBACK_REQUIRED")
    if not (1 <= remote_port <= 65535 and 1 <= local_port <= 65535):
        raise ValueError("SWARM_EXEC_GHBUF_BAD_PORT")
    return [
        "-o", "ExitOnForwardFailure=yes",
        "-R", f"127.0.0.1:{remote_port}:{local_host}:{local_port}",
    ]


def ensure_gh_buffer_sidecar(local_host: str, local_port: int, *, timeout: float = 4.0) -> None:
    ghbuf = _ghbuf_bin()
    if not ghbuf:
        raise ValueError("SWARM_EXEC_GHBUF_UNAVAILABLE")
    env = dict(os.environ)
    env["GHBUF_ADDR"] = f"{local_host}:{local_port}"
    proc = subprocess.run(
        [ghbuf, "ping"], capture_output=True, text=True, timeout=timeout, check=False, env=env
    )
    if proc.returncode != 0:
        raise ValueError("SWARM_EXEC_GHBUF_SIDECAR_UNAVAILABLE")


def ssh_args(
    *, gh_buffer_remote_port: int | None = None, gh_buffer_local_host: str = "127.0.0.1",
    gh_buffer_local_port: int = 19427,
) -> list[str]:
    key = Path.home() / ".ssh" / "chatgpt-linux-aatuska-ed25519"
    if not key.is_file():
        raise ValueError("SWARM_EXEC_SSH_KEY_MISSING")
    args = [
        "ssh", "-F", "NUL", "-4", "-i", str(key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
        "-o", f"HostKeyAlias={swarm_route.OMEN_HOST_KEY_ALIAS}",
    ]
    if gh_buffer_remote_port is not None:
        args.extend(gh_buffer_forward_args(gh_buffer_remote_port, gh_buffer_local_host, gh_buffer_local_port))
    args.append(f"{swarm_route.OMEN_USER}@{swarm_route.OMEN_HOST}")
    return args


def remote_script(
    work_id: str, command: str, cache_id: str, *, keep_workspace: bool = False,
    gh_buffer_remote_port: int | None = None,
) -> tuple[str, str]:
    safe = safe_work_id(work_id)
    if not re.fullmatch(r"[0-9a-f]{24}", cache_id):
        raise ValueError("SWARM_EXEC_BAD_CACHE_ID")
    final = str(OMEN_WORK_ROOT / safe)
    cache = str(OMEN_CACHE_ROOT / cache_id)
    cache_incoming = cache + f".incoming-{safe}-$$"
    cache_previous = cache + f".previous-{safe}-$$"
    cache_lock = cache + ".lock"
    payload = cache + f".payload-{safe}-$$.tar"
    git_meta_dir = cache + f".git-meta-{safe}-$$"
    keep = 1 if keep_workspace else 0
    gh_buffer_env = (
        f"export GHBUF_ADDR={shlex.quote(f'127.0.0.1:{gh_buffer_remote_port}')}\n"
        if gh_buffer_remote_port is not None else ""
    )
    if gh_buffer_remote_port is not None:
        command_exec = (
            "if ! command -v ghbuf >/dev/null 2>&1; then "
            "printf '%s\n' 'SWARM_EXEC_GHBUF_REMOTE_CLIENT_MISSING' >&2; exit 69; fi\n"
            f"ghbuf exec-readonly -- bash -c {shlex.quote(command)}"
        )
    else:
        command_exec = f"bash -c {shlex.quote(command)}"
    script = f"""set -eu
final={shlex.quote(final)}
cache={shlex.quote(cache)}
cache_incoming={shlex.quote(cache_incoming)}
cache_previous={shlex.quote(cache_previous)}
cache_lock={shlex.quote(cache_lock)}
payload={shlex.quote(payload)}
git_meta_dir={shlex.quote(git_meta_dir)}
manifest_name={shlex.quote(CACHE_MANIFEST_NAME)}
control_name={shlex.quote(CACHE_CONTROL_NAME)}
keep_workspace={keep}
published=0
cleanup() {{
  rc=$?
  trap - EXIT
  rm -f -- \"$payload\"
  rm -rf -- \"$cache_incoming\" \"$cache_previous\" \"$git_meta_dir\"
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
python3 - \"$cache_incoming\" \"$control_name\" \"$manifest_name\" \"$git_meta_dir\" <<'PY'
import base64, json, shutil, sys
from pathlib import Path, PurePosixPath
root=Path(sys.argv[1]); control_name=sys.argv[2]; manifest_name=sys.argv[3]; git_meta_dir=Path(sys.argv[4])
control=root/control_name
meta=json.loads(control.read_text(encoding='utf-8'))
git_meta=meta.get('git')
if not isinstance(git_meta, dict) or git_meta.get('version') != 1 or not git_meta.get('head'):
    raise SystemExit('SWARM_EXEC_REMOTE_GIT_PROVENANCE_INVALID')
try:
    pack=base64.b64decode(git_meta.get('pack_b64',''), validate=True)
    index=base64.b64decode(git_meta.get('index_b64',''), validate=True)
except Exception:
    raise SystemExit('SWARM_EXEC_REMOTE_GIT_PROVENANCE_INVALID')
shutil.rmtree(git_meta_dir, ignore_errors=True); git_meta_dir.mkdir(parents=True)
(git_meta_dir/'meta.json').write_text(json.dumps({{'head':git_meta['head'],'branch':git_meta.get('branch'),'config':git_meta.get('config',{{}}),'shallow':git_meta.get('shallow',[])}},separators=(',',':')),encoding='utf-8')
(git_meta_dir/'objects.pack').write_bytes(pack)
(git_meta_dir/'index.bin').write_bytes(index)
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
. {shlex.quote(OMEN_TOOL_ENV)}
export PYTHONPATH={shlex.quote(OMEN_PYTHON_PACKAGES)}:${{PYTHONPATH:-}}
{gh_buffer_env}python3 - \"$final\" \"$git_meta_dir\" <<'PY'
import json, shutil, subprocess, sys
from pathlib import Path
root=Path(sys.argv[1]); meta_dir=Path(sys.argv[2])
meta=json.loads((meta_dir/'meta.json').read_text(encoding='utf-8'))
head=str(meta.get('head') or ''); branch=meta.get('branch'); config=meta.get('config',{{}}); shallow=meta.get('shallow',[])
if not head or not isinstance(config, dict) or not isinstance(shallow, list):
    raise SystemExit('SWARM_EXEC_REMOTE_GIT_PROVENANCE_INVALID')
subprocess.run(['git','-C',str(root),'init','-q'],check=True)
allowed_config={{'core.autocrlf','core.filemode','core.symlinks','core.ignorecase'}}
for key,value in config.items():
    if key not in allowed_config or not isinstance(value, str):
        raise SystemExit('SWARM_EXEC_REMOTE_GIT_PROVENANCE_INVALID')
    subprocess.run(['git','-C',str(root),'config',key,value],check=True)
if shallow:
    (root/'.git'/'shallow').write_text('\\n'.join(str(value) for value in shallow)+'\\n',encoding='ascii')
with (meta_dir/'objects.pack').open('rb') as fh:
    subprocess.run(['git','-C',str(root),'index-pack','--stdin','--fix-thin'],stdin=fh,stdout=subprocess.DEVNULL,check=True)
subprocess.run(['git','-C',str(root),'update-index','-z','--index-info'],input=(meta_dir/'index.bin').read_bytes(),check=True)
if branch:
    ref='refs/heads/'+str(branch)
    subprocess.run(['git','-C',str(root),'update-ref',ref,head],check=True)
    subprocess.run(['git','-C',str(root),'symbolic-ref','HEAD',ref],check=True)
else:
    subprocess.run(['git','-C',str(root),'update-ref','--no-deref','HEAD',head],check=True)
shutil.rmtree(meta_dir)
PY
published=1
flock -u 9
cd -- \"$final\"
set +e
{command_exec}
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


def execute_omen(
    repo_root: Path, work_id: str, command: str, max_sync_mb: int, *, keep_workspace: bool = False,
    gh_buffer_readonly: bool = False,
) -> int:
    paths = snapshot_paths(repo_root)
    current_manifest, size, hash_hits, hash_misses = cached_snapshot_manifest(repo_root, paths)
    git_provenance, git_provenance_bytes = git_provenance_payload(repo_root)
    limit = max_sync_mb * 1024 * 1024
    bounded_size = size + git_provenance_bytes
    if bounded_size > limit:
        raise ValueError(f"SWARM_EXEC_SNAPSHOT_TOO_LARGE bytes={bounded_size} limit={limit}")
    cache_id = repo_cache_id(repo_root)
    gh_buffer_local_host = "127.0.0.1"
    gh_buffer_local_port = 19427
    gh_buffer_remote_port: int | None = None
    if gh_buffer_readonly:
        gh_buffer_local_host, gh_buffer_local_port = gh_buffer_local_target()
        ensure_gh_buffer_sidecar(gh_buffer_local_host, gh_buffer_local_port)
        gh_buffer_remote_port = select_gh_buffer_remote_port(work_id)
    workspace, script = remote_script(
        work_id, command, cache_id, keep_workspace=keep_workspace,
        gh_buffer_remote_port=gh_buffer_remote_port,
    )
    proc = subprocess.Popen(
        ssh_args(
            gh_buffer_remote_port=gh_buffer_remote_port, gh_buffer_local_host=gh_buffer_local_host,
            gh_buffer_local_port=gh_buffer_local_port,
        ) + [script], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
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
            "deleted_files": len(deleted), "hash_cache_hits": hash_hits, "hash_cache_misses": hash_misses,
            "git_provenance_bytes": git_provenance_bytes,
            "gh_buffer_readonly": gh_buffer_readonly,
            **({"gh_buffer_remote_addr": f"127.0.0.1:{gh_buffer_remote_port}"} if gh_buffer_remote_port is not None else {}),
        }, separators=(",", ":")), file=sys.stderr, flush=True)
        with tarfile.open(fileobj=proc.stdin, mode="w|") as tf:
            _add_control_member(tf, current_manifest, changed, deleted, git_provenance)
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
    p.add_argument(
        "--gh-buffer-readonly", action="store_true",
        help="share the local Rust gh-buffer with this OMEN command through an authenticated loopback-only SSH reverse tunnel",
    )
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
            return execute_omen(
                root, args.work_id, command, args.max_sync_mb, keep_workspace=args.keep_workspace,
                gh_buffer_readonly=args.gh_buffer_readonly,
            )
        finally:
            if not args.keep_lease:
                swarm_route.release_work(args.state, args.work_id)
    except (ValueError, TimeoutError, OSError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
