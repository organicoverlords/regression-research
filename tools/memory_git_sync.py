from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
REL_BANK = Path("memory") / "memory-bank.jsonl"
REMOTE = "origin"
BRANCH = "memory/live"
SEED_BRANCH = "main"
PROTECTED_REMOTE_BRANCHES = frozenset({"main", "master", "dev", "develop"})
MAX_SYNC_ATTEMPTS = 3
LOCK_STALE_SECONDS = 180
IS_WINDOWS = os.name == "nt"


class MemorySyncError(RuntimeError):
    pass


def _validate_sync_branch() -> None:
    branch = BRANCH.strip()
    if not branch:
        raise MemorySyncError("memory sync branch is empty")
    if branch.casefold() in PROTECTED_REMOTE_BRANCHES:
        raise MemorySyncError(f"memory sync refuses protected branch: {branch}")


def _git(*args: str, cwd: Path = REPO_ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", *args], cwd=cwd, text=True, encoding="utf-8", capture_output=True)
    if check and proc.returncode:
        detail = (proc.stderr or proc.stdout).strip()[-1600:]
        raise MemorySyncError(f"git {' '.join(args)} failed: {detail}")
    return proc


def _parse_bank_text(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_no, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MemorySyncError(f"bank line {line_no} is invalid JSON") from exc
        ident = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(ident, str) or not ident:
            raise MemorySyncError(f"bank line {line_no} has no id")
        if ident in seen:
            raise MemorySyncError(f"bank contains duplicate id {ident}")
        seen.add(ident)
        entries.append(entry)
    return entries


def _read_bank(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return _parse_bank_text(path.read_text(encoding="utf-8-sig"))


def _serialize(entries: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n" for entry in entries)


def merge_bank_entries(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = list(primary)
    by_id = {entry["id"]: entry for entry in primary}
    for entry in secondary:
        ident = entry["id"]
        if ident in by_id:
            if by_id[ident] != entry:
                raise MemorySyncError(f"memory id conflict: {ident}")
            continue
        merged.append(entry)
        by_id[ident] = entry
    return merged


def local_memory_replica_entries(*, repo_root: Path = REPO_ROOT) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read the locally fetched memory/live replica without network or checkout mutation."""
    ref = f"refs/remotes/{REMOTE}/{BRANCH}"
    head = _git("rev-parse", ref, cwd=repo_root, check=False)
    if head.returncode != 0:
        return [], {
            "status": "UNAVAILABLE",
            "authority": "LOCAL_GIT_MEMORY_REPLICA",
            "ref": ref,
            "network_fanout": False,
            "checkout_mutated": False,
        }
    shown = _git("show", f"{ref}:{REL_BANK.as_posix()}", cwd=repo_root, check=False)
    if shown.returncode != 0:
        return [], {
            "status": "UNAVAILABLE",
            "authority": "LOCAL_GIT_MEMORY_REPLICA",
            "ref": ref,
            "head": head.stdout.strip(),
            "network_fanout": False,
            "checkout_mutated": False,
        }
    entries = _parse_bank_text(shown.stdout)
    return entries, {
        "status": "OK",
        "authority": "LOCAL_GIT_MEMORY_REPLICA",
        "ref": ref,
        "head": head.stdout.strip(),
        "entries": len(entries),
        "network_fanout": False,
        "checkout_mutated": False,
    }




def _write_bank(path: Path, entries: list[dict[str, Any]]) -> None:
    text = _serialize(entries)
    if path.exists() and path.read_text(encoding="utf-8-sig") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".sync-tmp")
    temp_path.write_text(text, encoding="utf-8", newline="\n")
    try:
        os.replace(temp_path, path)
        return
    except PermissionError:
        # Windows readers can open the bank without FILE_SHARE_DELETE. In that
        # state replacing the pathname fails even though the file itself remains
        # writable. sync_lock serializes memory writers, so preserve the temp
        # recovery copy and rewrite the existing file identity in place.
        if not IS_WINDOWS or not path.exists():
            raise

    payload = temp_path.read_bytes()
    with path.open("r+b") as handle:
        handle.seek(0)
        handle.write(payload)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != payload:
        raise MemorySyncError(f"memory bank in-place rewrite verification failed: {path}")
    temp_path.unlink()


@contextmanager
def sync_lock(bank_path: Path, timeout_seconds: float = 15.0) -> Iterator[None]:
    lock_path = bank_path.with_name(bank_path.name + ".sync.lock")
    deadline = time.monotonic() + timeout_seconds
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()}\n".encode("ascii"))
        except FileExistsError:
            try:
                stale = time.time() - lock_path.stat().st_mtime > LOCK_STALE_SECONDS
            except FileNotFoundError:
                continue
            if stale:
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    pass
                continue
            if time.monotonic() >= deadline:
                raise MemorySyncError(f"memory sync lock remained busy: {lock_path}")
            time.sleep(0.1)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _ghbuf_bin() -> str | None:
    configured = os.environ.get("GHBUF_BIN", "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    found = shutil.which("ghbuf")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / ("ghbuf.exe" if IS_WINDOWS else "ghbuf")
    return str(local) if local.is_file() else None


def _ghbuf_remote_branch_probe() -> subprocess.CompletedProcess[str] | None:
    ghbuf = _ghbuf_bin()
    if not ghbuf:
        return None
    try:
        proc = subprocess.run(
            [
                ghbuf,
                "exec-git",
                "--",
                "git",
                "ls-remote",
                "--exit-code",
                "--heads",
                REMOTE,
                f"refs/heads/{BRANCH}",
            ],
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
    except OSError:
        return None
    # 0 and 2 are authoritative Git ls-remote outcomes (match / no match).
    # Any wrapper/proxy operational failure falls back to real Git instead of
    # being mistaken for a missing branch.
    return proc if proc.returncode in (0, 2) else None


def _remote_branch_exists(*, authoritative: bool = False) -> bool:
    proc = None if authoritative else _ghbuf_remote_branch_probe()
    if proc is None:
        proc = _git(
            "ls-remote", "--exit-code", "--heads", REMOTE, f"refs/heads/{BRANCH}",
            check=False,
        )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _ensure_remote_branch() -> bool:
    """Recreate a deleted dedicated memory mirror without touching protected refs."""
    _validate_sync_branch()
    if _remote_branch_exists():
        return False
    if SEED_BRANCH.casefold() not in PROTECTED_REMOTE_BRANCHES:
        raise MemorySyncError(f"memory sync seed must be an integration branch: {SEED_BRANCH}")
    _git("fetch", REMOTE, SEED_BRANCH)
    seed = _git("rev-parse", f"{REMOTE}/{SEED_BRANCH}").stdout.strip()
    if not seed:
        raise MemorySyncError(f"memory sync could not resolve seed branch: {REMOTE}/{SEED_BRANCH}")
    pushed = _git("push", REMOTE, f"{seed}:refs/heads/{BRANCH}", check=False)
    if pushed.returncode != 0 and not _remote_branch_exists(authoritative=True):
        detail = (pushed.stderr or pushed.stdout).strip()[-1600:]
        raise MemorySyncError(f"memory sync could not recreate {REMOTE}/{BRANCH}: {detail}")
    return True


def _remote_state() -> tuple[str, list[dict[str, Any]]]:
    _ensure_remote_branch()
    _git("fetch", REMOTE, BRANCH)
    head = _git("rev-parse", f"{REMOTE}/{BRANCH}").stdout.strip()
    shown = _git("show", f"{REMOTE}/{BRANCH}:{REL_BANK.as_posix()}")
    return head, _parse_bank_text(shown.stdout)


def _commit_entry_lines(entries: list[dict[str, Any]], ids: set[str]) -> list[str]:
    by_id = {entry.get("id"): entry for entry in entries}
    lines: list[str] = []
    for ident in sorted(ids):
        entry = by_id.get(ident) or {}
        title = str(entry.get("title") or entry.get("scope") or entry.get("kind") or "memory entry").replace("\n", " ").strip()
        lines.append(f"- {ident}: {title}")
    return lines

def _memory_commit_message(entries: list[dict[str, Any]], entry_ids: set[str]) -> tuple[str, str]:
    if len(entry_ids) == 1:
        subject = f"memory: add {next(iter(entry_ids))}"
    else:
        subject = f"memory: add {len(entry_ids)} canonical entries"
    body = "Memory change log:\n" + "\n".join(_commit_entry_lines(entries, entry_ids))
    return subject, body


def _publish_once(entries: list[dict[str, Any]], new_ids: set[str]) -> subprocess.CompletedProcess[str]:
    _validate_sync_branch()
    temp_root = Path(tempfile.mkdtemp(prefix="vault-memory-sync-"))
    worktree = temp_root / "worktree"
    added = False
    try:
        _git("worktree", "add", "--detach", str(worktree), f"{REMOTE}/{BRANCH}")
        added = True
        _write_bank(worktree / REL_BANK, entries)
        _git("add", "--", REL_BANK.as_posix(), cwd=worktree)
        diff = _git("diff", "--cached", "--quiet", cwd=worktree, check=False)
        if diff.returncode == 0:
            return subprocess.CompletedProcess([], 0, "", "")
        if diff.returncode != 1:
            raise MemorySyncError("could not inspect staged memory-bank delta")
        subject, body = _memory_commit_message(entries, new_ids)
        _git("commit", "-m", subject, "-m", body, cwd=worktree)
        return _git("push", REMOTE, f"HEAD:{BRANCH}", cwd=worktree, check=False)
    finally:
        if added:
            _git("worktree", "remove", "--force", str(worktree), check=False)
        shutil.rmtree(temp_root, ignore_errors=True)

def sync_bank(bank_path: Path, *, publish: bool) -> dict[str, Any]:
    """Merge/publish the bank without mutating any serving or user checkout."""
    bank_path = bank_path.resolve()
    for attempt in range(1, MAX_SYNC_ATTEMPTS + 1):
        remote_head, remote_entries = _remote_state()
        local_entries = _read_bank(bank_path)
        local_ids = {entry["id"] for entry in local_entries}
        remote_ids = {entry["id"] for entry in remote_entries}
        merged = merge_bank_entries(remote_entries, local_entries)
        pulled = len(remote_ids - local_ids)
        pending = len(local_ids - remote_ids)
        _write_bank(bank_path, merged)
        if not publish or pending == 0:
            return {
                "status": "PROVEN",
                "remote_head": remote_head,
                "pulled": pulled,
                "pending_push": pending,
                "pushed": 0,
                "aligned_head": False,
                "checkout_mutated": False,
            }
        pushed = _publish_once(merged, local_ids - remote_ids)
        if pushed.returncode == 0:
            _git("fetch", REMOTE, BRANCH)
            new_head = _git("rev-parse", f"{REMOTE}/{BRANCH}").stdout.strip()
            return {
                "status": "PROVEN",
                "remote_head": new_head,
                "pulled": pulled,
                "pending_push": 0,
                "pushed": pending,
                "aligned_head": False,
                "checkout_mutated": False,
            }
        message = (pushed.stderr or pushed.stdout).strip()
        race = "fetch first" in message.lower() or "non-fast-forward" in message.lower()
        if race and attempt < MAX_SYNC_ATTEMPTS:
            continue
        raise MemorySyncError(f"memory push failed: {message[-1600:]}")
    raise MemorySyncError("memory sync retries exhausted")
