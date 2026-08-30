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
REL_AUTHORITY_REGISTRY = Path("memory") / "behavior-authority-registry.json"
REMOTE = "origin"
BRANCH = "main"
MAX_SYNC_ATTEMPTS = 3
LOCK_STALE_SECONDS = 180
IS_WINDOWS = os.name == "nt"


class MemorySyncError(RuntimeError):
    pass


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




def _parse_authority_registry_text(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MemorySyncError("authority registry is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise MemorySyncError("authority registry root must be an object")
    if payload.get("schema_version") != 1:
        raise MemorySyncError("authority registry schema_version must be 1")
    for key in ("user_explicit_ids", "canonical_policy_ids"):
        values = payload.get(key)
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            raise MemorySyncError(f"authority registry {key} must be an array of non-empty strings")
        if len(values) != len(set(values)):
            raise MemorySyncError(f"authority registry {key} contains duplicate ids")
    return payload


def _read_authority_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MemorySyncError(f"authority registry not found: {path}")
    return _parse_authority_registry_text(path.read_text(encoding="utf-8-sig"))


def merge_authority_registries(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    if primary.get("schema_version") != secondary.get("schema_version"):
        raise MemorySyncError("authority registry schema conflict")
    result = dict(primary)
    for key in ("user_explicit_ids", "canonical_policy_ids"):
        result[key] = sorted(set(primary.get(key, [])) | set(secondary.get(key, [])))
    if "purpose" not in result and secondary.get("purpose"):
        result["purpose"] = secondary["purpose"]
    return result


def _write_authority_registry(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8-sig") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".sync-tmp")
    temp_path.write_text(text, encoding="utf-8", newline="\n")
    try:
        os.replace(temp_path, path)
        return
    except PermissionError:
        if not IS_WINDOWS or not path.exists():
            raise
    payload_bytes = temp_path.read_bytes()
    with path.open("r+b") as handle:
        handle.seek(0)
        handle.write(payload_bytes)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
    if path.read_bytes() != payload_bytes:
        raise MemorySyncError(f"authority registry in-place rewrite verification failed: {path}")
    temp_path.unlink()


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


def _remote_state() -> tuple[str, list[dict[str, Any]]]:
    _git("fetch", REMOTE, BRANCH)
    head = _git("rev-parse", f"{REMOTE}/{BRANCH}").stdout.strip()
    shown = _git("show", f"{REMOTE}/{BRANCH}:{REL_BANK.as_posix()}")
    return head, _parse_bank_text(shown.stdout)


def _align_checkout(remote_head: str, bank_path: Path, *, repo_root: Path = REPO_ROOT) -> bool:
    canonical_bank = (repo_root / REL_BANK).resolve()
    if bank_path.resolve() != canonical_bank:
        return False
    upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", cwd=repo_root, check=False)
    if upstream.returncode != 0 or upstream.stdout.strip() != f"{REMOTE}/{BRANCH}":
        return False
    current_head = _git("rev-parse", "HEAD", cwd=repo_root).stdout.strip()
    if current_head == remote_head:
        return False
    ancestor = _git("merge-base", "--is-ancestor", current_head, remote_head, cwd=repo_root, check=False)
    if ancestor.returncode != 0:
        return False

    fast_forward = _git("merge", "--ff-only", remote_head, cwd=repo_root, check=False)
    if fast_forward.returncode == 0:
        return True

    changed = {
        line.strip().replace("\\", "/")
        for line in _git("diff", "--name-only", f"{current_head}..{remote_head}", cwd=repo_root).stdout.splitlines()
        if line.strip()
    }
    if changed - {REL_BANK.as_posix()}:
        return False
    bank_matches_remote = _git("diff", "--quiet", remote_head, "--", REL_BANK.as_posix(), cwd=repo_root, check=False)
    if bank_matches_remote.returncode != 0:
        return False
    ref = _git("symbolic-ref", "--quiet", "HEAD", cwd=repo_root, check=False).stdout.strip()
    if not ref:
        return False
    _git("update-ref", ref, remote_head, current_head, cwd=repo_root)
    _git("reset", "HEAD", "--", REL_BANK.as_posix(), cwd=repo_root)
    return True


def _publish_once(entries: list[dict[str, Any]]) -> subprocess.CompletedProcess[str]:
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
        _git("commit", "-m", "memory: synchronize canonical bank", cwd=worktree)
        return _git("push", REMOTE, f"HEAD:{BRANCH}", cwd=worktree, check=False)
    finally:
        if added:
            _git("worktree", "remove", "--force", str(worktree), check=False)
        shutil.rmtree(temp_root, ignore_errors=True)


def sync_bank(bank_path: Path, *, publish: bool) -> dict[str, Any]:
    bank_path = bank_path.resolve()
    for attempt in range(1, MAX_SYNC_ATTEMPTS + 1):
        remote_head, remote_entries = _remote_state()
        local_entries = _read_bank(bank_path)
        local_ids = {entry["id"] for entry in local_entries}
        remote_ids = {entry["id"] for entry in remote_entries}
        merged = merge_bank_entries(remote_entries, local_entries)
        pulled = len(remote_ids - local_ids)
        pending = len(local_ids - remote_ids)
        aligned = _align_checkout(remote_head, bank_path) if pending == 0 else False
        _write_bank(bank_path, merged)
        if not publish or pending == 0:
            if not aligned:
                aligned = _align_checkout(remote_head, bank_path)
            return {
                "status": "PROVEN",
                "remote_head": remote_head,
                "pulled": pulled,
                "pending_push": pending,
                "pushed": 0,
                "aligned_head": aligned,
            }
        pushed = _publish_once(merged)
        if pushed.returncode == 0:
            _git("fetch", REMOTE, BRANCH)
            new_head = _git("rev-parse", f"{REMOTE}/{BRANCH}").stdout.strip()
            aligned = _align_checkout(new_head, bank_path)
            return {
                "status": "PROVEN",
                "remote_head": new_head,
                "pulled": pulled,
                "pending_push": 0,
                "pushed": pending,
                "aligned_head": aligned,
            }
        message = (pushed.stderr or pushed.stdout).strip()
        race = "fetch first" in message.lower() or "non-fast-forward" in message.lower()
        if race and attempt < MAX_SYNC_ATTEMPTS:
            continue
        raise MemorySyncError(f"memory push failed: {message[-1600:]}")
    raise MemorySyncError("memory sync retries exhausted")

def _remote_behavior_bundle_state() -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    _git("fetch", REMOTE, BRANCH)
    head = _git("rev-parse", f"{REMOTE}/{BRANCH}").stdout.strip()
    bank = _git("show", f"{REMOTE}/{BRANCH}:{REL_BANK.as_posix()}")
    registry = _git("show", f"{REMOTE}/{BRANCH}:{REL_AUTHORITY_REGISTRY.as_posix()}")
    return head, _parse_bank_text(bank.stdout), _parse_authority_registry_text(registry.stdout)


def _align_behavior_bundle_checkout(
    remote_head: str, bank_path: Path, registry_path: Path, *, repo_root: Path = REPO_ROOT
) -> bool:
    if bank_path.resolve() != (repo_root / REL_BANK).resolve():
        return False
    if registry_path.resolve() != (repo_root / REL_AUTHORITY_REGISTRY).resolve():
        return False
    upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", cwd=repo_root, check=False)
    if upstream.returncode != 0 or upstream.stdout.strip() != f"{REMOTE}/{BRANCH}":
        return False
    current_head = _git("rev-parse", "HEAD", cwd=repo_root).stdout.strip()
    if current_head == remote_head:
        return False
    if _git("merge-base", "--is-ancestor", current_head, remote_head, cwd=repo_root, check=False).returncode != 0:
        return False
    fast_forward = _git("merge", "--ff-only", remote_head, cwd=repo_root, check=False)
    if fast_forward.returncode == 0:
        return True
    allowed = {REL_BANK.as_posix(), REL_AUTHORITY_REGISTRY.as_posix()}
    changed = {
        line.strip().replace("\\", "/")
        for line in _git("diff", "--name-only", f"{current_head}..{remote_head}", cwd=repo_root).stdout.splitlines()
        if line.strip()
    }
    if changed - allowed:
        return False
    for rel in allowed:
        if _git("diff", "--quiet", remote_head, "--", rel, cwd=repo_root, check=False).returncode != 0:
            return False
    ref = _git("symbolic-ref", "--quiet", "HEAD", cwd=repo_root, check=False).stdout.strip()
    if not ref:
        return False
    _git("update-ref", ref, remote_head, current_head, cwd=repo_root)
    _git("reset", "HEAD", "--", *sorted(allowed), cwd=repo_root)
    return True


def _publish_behavior_bundle_once(
    entries: list[dict[str, Any]], registry: dict[str, Any]
) -> subprocess.CompletedProcess[str]:
    temp_root = Path(tempfile.mkdtemp(prefix="vault-behavior-sync-"))
    worktree = temp_root / "worktree"
    added = False
    try:
        _git("worktree", "add", "--detach", str(worktree), f"{REMOTE}/{BRANCH}")
        added = True
        _write_bank(worktree / REL_BANK, entries)
        _write_authority_registry(worktree / REL_AUTHORITY_REGISTRY, registry)
        _git("add", "--", REL_BANK.as_posix(), REL_AUTHORITY_REGISTRY.as_posix(), cwd=worktree)
        diff = _git("diff", "--cached", "--quiet", cwd=worktree, check=False)
        if diff.returncode == 0:
            return subprocess.CompletedProcess([], 0, "", "")
        if diff.returncode != 1:
            raise MemorySyncError("could not inspect staged behavior-memory delta")
        _git("commit", "-m", "memory: synchronize behavior authority", cwd=worktree)
        return _git("push", REMOTE, f"HEAD:{BRANCH}", cwd=worktree, check=False)
    finally:
        if added:
            _git("worktree", "remove", "--force", str(worktree), check=False)
        shutil.rmtree(temp_root, ignore_errors=True)


def sync_behavior_bundle(
    bank_path: Path,
    registry_path: Path,
    *,
    add_user_ids: set[str] | None = None,
    add_policy_ids: set[str] | None = None,
    publish: bool,
) -> dict[str, Any]:
    bank_path = bank_path.resolve()
    registry_path = registry_path.resolve()
    add_user_ids = set(add_user_ids or ())
    add_policy_ids = set(add_policy_ids or ())
    for attempt in range(1, MAX_SYNC_ATTEMPTS + 1):
        remote_head, remote_entries, remote_registry = _remote_behavior_bundle_state()
        local_entries = _read_bank(bank_path)
        local_registry = _read_authority_registry(registry_path)
        merged_entries = merge_bank_entries(remote_entries, local_entries)
        merged_registry = merge_authority_registries(remote_registry, local_registry)
        merged_registry["user_explicit_ids"] = sorted(set(merged_registry["user_explicit_ids"]) | add_user_ids)
        merged_registry["canonical_policy_ids"] = sorted(set(merged_registry["canonical_policy_ids"]) | add_policy_ids)
        local_ids = {entry["id"] for entry in local_entries}
        remote_ids = {entry["id"] for entry in remote_entries}
        remote_user = set(remote_registry["user_explicit_ids"])
        remote_policy = set(remote_registry["canonical_policy_ids"])
        pending_bank = len(local_ids - remote_ids)
        pending_registry = len((set(merged_registry["user_explicit_ids"]) - remote_user) | (set(merged_registry["canonical_policy_ids"]) - remote_policy))
        _write_bank(bank_path, merged_entries)
        _write_authority_registry(registry_path, merged_registry)
        if not publish or (pending_bank == 0 and pending_registry == 0):
            aligned = _align_behavior_bundle_checkout(remote_head, bank_path, registry_path)
            return {
                "status": "PROVEN", "remote_head": remote_head,
                "pending_bank": pending_bank, "pending_registry": pending_registry,
                "pushed": 0, "aligned_head": aligned,
            }
        pushed = _publish_behavior_bundle_once(merged_entries, merged_registry)
        if pushed.returncode == 0:
            _git("fetch", REMOTE, BRANCH)
            new_head = _git("rev-parse", f"{REMOTE}/{BRANCH}").stdout.strip()
            aligned = _align_behavior_bundle_checkout(new_head, bank_path, registry_path)
            return {
                "status": "PROVEN", "remote_head": new_head,
                "pending_bank": 0, "pending_registry": 0,
                "pushed": pending_bank + pending_registry, "aligned_head": aligned,
            }
        message = (pushed.stderr or pushed.stdout).strip()
        race = "fetch first" in message.lower() or "non-fast-forward" in message.lower()
        if race and attempt < MAX_SYNC_ATTEMPTS:
            continue
        raise MemorySyncError(f"behavior-memory push failed: {message[-1600:]}")
    raise MemorySyncError("behavior-memory sync retries exhausted")
