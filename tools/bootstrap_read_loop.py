import argparse
import json
import os
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parent
MEMORY_RECENT_LIMIT = 3
PRODUCER_STATUS_NAME = 'producer-status.json'
BOOTSTRAP_DEPLOYMENT_SOURCE_REF = 'refs/remotes/origin/main'


BOOTSTRAP_GLANCE_TIMEOUT_SECONDS = 30.0
PROCESS_TREE_KILL_TIMEOUT_SECONDS = 2.0
WINDOWS_JOB_OBJECT_ASSIGN_FAILURE_EXIT_CODE = 125
SEVERE_FREE_PHYSICAL_BYTES = 768 * 1024 * 1024
SEVERE_COMMIT_USED_PCT = 85.0


def _resource_pressure_from_memory_values(*, available_physical: int, commit_limit: int, commit_available: int) -> dict | None:
    commit_used = max(0, int(commit_limit) - int(commit_available))
    commit_used_pct = 0.0 if commit_limit <= 0 else 100.0 * commit_used / int(commit_limit)
    low_physical = int(available_physical) < SEVERE_FREE_PHYSICAL_BYTES
    high_commit = commit_used_pct >= SEVERE_COMMIT_USED_PCT
    # Windows can run with very little free physical RAM while commit headroom is
    # still healthy. Shed the full refresh only when both pressure signals agree;
    # physical-free alone must not turn a healthy-commit machine DEGRADED.
    if not (low_physical and high_commit):
        return None
    reasons = ['low_free_physical_memory', 'high_commit_pressure']
    return {
        'status': 'SEVERE',
        'reasons': reasons,
        'available_physical_bytes': int(available_physical),
        'available_physical_mb': round(int(available_physical) / (1024 * 1024), 1),
        'commit_used_bytes': commit_used,
        'commit_limit_bytes': int(commit_limit),
        'commit_used_pct': round(commit_used_pct, 1),
    }


def _windows_resource_pressure() -> dict | None:
    if os.name != 'nt':
        return None
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ('dwLength', ctypes.c_ulong),
            ('dwMemoryLoad', ctypes.c_ulong),
            ('ullTotalPhys', ctypes.c_ulonglong),
            ('ullAvailPhys', ctypes.c_ulonglong),
            ('ullTotalPageFile', ctypes.c_ulonglong),
            ('ullAvailPageFile', ctypes.c_ulonglong),
            ('ullTotalVirtual', ctypes.c_ulonglong),
            ('ullAvailVirtual', ctypes.c_ulonglong),
            ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MEMORYSTATUSEX)]
    kernel32.GlobalMemoryStatusEx.restype = ctypes.c_int
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return _resource_pressure_from_memory_values(
        available_physical=status.ullAvailPhys,
        commit_limit=status.ullTotalPageFile,
        commit_available=status.ullAvailPageFile,
    )


def _close_windows_handle(handle) -> None:
    if os.name != 'nt' or not handle:
        return
    import ctypes
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(handle)


def _assign_windows_kill_on_close_job(process: subprocess.Popen[bytes]):
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes

    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ('PerProcessUserTimeLimit', ctypes.c_longlong),
            ('PerJobUserTimeLimit', ctypes.c_longlong),
            ('LimitFlags', wintypes.DWORD),
            ('MinimumWorkingSetSize', ctypes.c_size_t),
            ('MaximumWorkingSetSize', ctypes.c_size_t),
            ('ActiveProcessLimit', wintypes.DWORD),
            ('Affinity', ctypes.c_size_t),
            ('PriorityClass', wintypes.DWORD),
            ('SchedulingClass', wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ('ReadOperationCount', ctypes.c_ulonglong),
            ('WriteOperationCount', ctypes.c_ulonglong),
            ('OtherOperationCount', ctypes.c_ulonglong),
            ('ReadTransferCount', ctypes.c_ulonglong),
            ('WriteTransferCount', ctypes.c_ulonglong),
            ('OtherTransferCount', ctypes.c_ulonglong),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ('IoInfo', IO_COUNTERS),
            ('ProcessMemoryLimit', ctypes.c_size_t),
            ('JobMemoryLimit', ctypes.c_size_t),
            ('PeakProcessMemoryUsed', ctypes.c_size_t),
            ('PeakJobMemoryUsed', ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), 'CreateJobObjectW failed')
    try:
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            raise OSError(ctypes.get_last_error(), 'SetInformationJobObject failed')
        process_handle = wintypes.HANDLE(process._handle)
        if not kernel32.AssignProcessToJobObject(job, process_handle):
            raise OSError(ctypes.get_last_error(), 'AssignProcessToJobObject failed')
        return job
    except Exception:
        _close_windows_handle(job)
        raise


def _creationflags() -> int:
    if os.name != 'nt':
        return 0
    return int(getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def _child_python() -> str:
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.name.casefold() == 'pythonw.exe':
        console = executable.with_name('python.exe')
        if console.exists():
            return str(console)
    return str(executable)


def _terminate_process_tree(process: subprocess.Popen[bytes], *, timeout_seconds: float = PROCESS_TREE_KILL_TIMEOUT_SECONDS) -> None:
    if process.poll() is not None:
        return
    if os.name == 'nt':
        killer = None
        try:
            killer = subprocess.Popen(
                ['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_creationflags(),
                close_fds=True,
            )
            try:
                killer.wait(timeout=max(0.1, timeout_seconds))
            except subprocess.TimeoutExpired:
                killer.kill()
        except OSError:
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass


def _read_capture(stream) -> str:
    stream.flush()
    stream.seek(0)
    return stream.read().decode('utf-8', errors='replace')


def _git_ref_file_bytes(repo_root: Path, source_ref: str, relative_path: str) -> bytes | None:
    repo_root = repo_root.resolve()
    probe = subprocess.run(
        ['git', '-C', str(repo_root), 'rev-parse', '--is-inside-work-tree'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
    )
    if probe.returncode != 0 or probe.stdout.strip() != 'true':
        return None
    source = subprocess.run(
        ['git', '-C', str(repo_root), 'show', f'{source_ref}:{relative_path}'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if source.returncode != 0 or not source.stdout:
        detail = source.stderr.decode('utf-8', errors='replace')[-500:]
        raise RuntimeError(f'unable to read bootstrap deployment source {source_ref}:{relative_path}: {detail}')
    return source.stdout


def _replace_deployed_file_bytes(destination: Path, desired: bytes) -> bool:
    destination = destination.resolve()
    try:
        if destination.read_bytes() == desired:
            return False
    except FileNotFoundError:
        pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w+b', dir=destination.parent, suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(desired)
            stream.flush()
            os.fsync(stream.fileno())
        _replace_snapshot(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def _sync_deployed_file_from_source_ref(
    repo_root: Path, destination: Path, relative_path: str, *, source_ref: str = BOOTSTRAP_DEPLOYMENT_SOURCE_REF
) -> bool:
    repo_root = repo_root.resolve()
    destination = destination.resolve()
    canonical = (repo_root / Path(relative_path)).resolve()
    if destination == canonical:
        return False
    desired = _git_ref_file_bytes(repo_root, source_ref, relative_path)
    if desired is None:
        return False
    return _replace_deployed_file_bytes(destination, desired)


def _sync_deployed_atlas_from_source_ref(repo_root: Path, atlas: Path) -> bool:
    """Refresh deployed Stack Atlas from cached origin/main, never live branch/worktree bytes."""
    return _sync_deployed_file_from_source_ref(repo_root, atlas, 'tools/stack_atlas.py')


def _sync_deployed_runtime_bundle_from_source_ref(repo_root: Path, atlas: Path | None) -> dict[str, bool]:
    """Self-heal the scheduled AppData producer bundle from cached origin/main.

    The installer deploys producer/helper/Atlas into one runtime directory. Once this
    generation is installed, every primary run repairs all three committed bytes from
    the cached remote-main ref before doing useful work. VaultCheckoutSync owns refreshing
    that ref without mutating a dirty/wrong-branch serving checkout. The current process may continue on its already-loaded producer
    code for this one run; the next scheduled run necessarily starts from the repaired
    producer. Dirty worktree bytes are never used by this repair path.
    """
    if atlas is None:
        return {}
    producer = Path(__file__).resolve()
    atlas = atlas.resolve()
    runtime_dir = producer.parent
    canonical_producer = (repo_root.resolve() / 'tools' / 'bootstrap_read_loop.py').resolve()
    if producer == canonical_producer or atlas.parent != runtime_dir:
        return {}
    targets = (
        ('producer', producer, 'tools/bootstrap_read_loop.py'),
        ('memory_helper', runtime_dir / 'memory_recent_projection.py', 'tools/memory_recent_projection.py'),
        ('atlas', atlas, 'tools/stack_atlas.py'),
    )
    return {
        name: _sync_deployed_file_from_source_ref(repo_root, destination, relative_path)
        for name, destination, relative_path in targets
    }


def _run_bootstrap_glance(repo_root: Path, atlas: Path, *, timeout_seconds: float = BOOTSTRAP_GLANCE_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    stdout_path = None
    stderr_path = None
    stdout_stream = None
    stderr_stream = None
    command = [_child_python(), str(atlas), 'bootstrap-glance']
    env = os.environ.copy()
    env['STACK_ATLAS_ROOT_OVERRIDE'] = str(repo_root)
    existing_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(repo_root) if not existing_pythonpath else os.pathsep.join((str(repo_root), existing_pythonpath))
    try:
        stdout_stream = tempfile.NamedTemporaryFile(mode='w+b', prefix='bootstrap-glance-stdout-', suffix='.tmp', delete=False)
        stderr_stream = tempfile.NamedTemporaryFile(mode='w+b', prefix='bootstrap-glance-stderr-', suffix='.tmp', delete=False)
        stdout_path = Path(stdout_stream.name)
        stderr_path = Path(stderr_stream.name)
        process = subprocess.Popen(
            command,
            cwd=str(repo_root),
            stdout=stdout_stream,
            stderr=stderr_stream,
            env=env,
            creationflags=_creationflags(),
            close_fds=True,
        )
        job_handle = None
        if os.name == 'nt':
            try:
                job_handle = _assign_windows_kill_on_close_job(process)
            except OSError as exc:
                _terminate_process_tree(process)
                return subprocess.CompletedProcess(
                    command,
                    WINDOWS_JOB_OBJECT_ASSIGN_FAILURE_EXIT_CODE,
                    '',
                    f'bootstrap-glance child job assignment failed: {exc}',
                )
        try:
            timed_out = False
            try:
                returncode = process.wait(timeout=max(0.1, timeout_seconds))
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                returncode = 124
            stdout = _read_capture(stdout_stream)
            stderr = _read_capture(stderr_stream)
            if timed_out:
                suffix = f'bootstrap-glance timed out after {timeout_seconds:.1f}s'
                stderr = f'{stderr.rstrip()}\n{suffix}'.lstrip()
            return subprocess.CompletedProcess(command, returncode, stdout, stderr)
        finally:
            _close_windows_handle(job_handle)
    finally:
        for stream in (stdout_stream, stderr_stream):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        for path in (stdout_path, stderr_path):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    # A timed-out descendant can briefly retain an inherited file handle.
                    # The producer must stay bounded even if that best-effort cleanup cannot run yet.
                    pass


def _memory_projection_api():
    # Keep this import after deployed-bundle self-heal so a stale AppData helper is
    # replaced before Python loads it into the scheduled producer process.
    try:
        from tools.memory_recent_projection import default_local_bank_path, read_current_projection
    except ImportError:
        from memory_recent_projection import default_local_bank_path, read_current_projection
    return default_local_bank_path, read_current_projection


def _load_current_memory_projection(repo_root: Path) -> dict | None:
    default_local_bank_path, read_current_projection = _memory_projection_api()
    seed_path = repo_root / 'memory' / 'memory-bank.jsonl'
    overlay_path = default_local_bank_path()
    return read_current_projection(seed_path=seed_path, overlay_path=overlay_path)


def _overlay_current_memory(payload: dict, repo_root: Path) -> dict:
    projection = _load_current_memory_projection(repo_root)
    if projection is None:
        return payload
    recent = projection.get('recent')
    if not isinstance(recent, list):
        return payload
    view = dict(payload)
    overview = dict(view.get('memory_overview') or {})
    overview['recent'] = recent[:MEMORY_RECENT_LIMIT]
    overview['recent_source'] = {
        'authority': 'DIRECT_LOCAL_EFFECTIVE_MEMORY_PROJECTION',
        'read_mode': 'fingerprint_validated_recent_titles_projection',
        'status': 'CURRENT_FOR_EFFECTIVE_MEMORY_FILES',
        'generated_at': projection.get('generated_at'),
    }
    view['memory_overview'] = overview
    return view


def _replace_snapshot(temporary: Path, destination: Path, *, retry_seconds: float = 0.5) -> None:
    deadline = time.monotonic() + max(0.0, retry_seconds)
    delay = 0.005
    while True:
        try:
            os.replace(temporary, destination)
            return
        except PermissionError:
            if os.name != 'nt' or time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.05)


def _snapshot_dir(repo_root: Path) -> Path:
    return repo_root.resolve() / '.state' / 'bootstrap'


def _write_json_atomic(destination: Path, payload: dict) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        _replace_snapshot(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_producer_status(repo_root: Path, *, mode: str, detail: str = '', exit_code: int = 0) -> None:
    try:
        _write_json_atomic(_snapshot_dir(repo_root) / PRODUCER_STATUS_NAME, {
            'schema': 'bootstrap-producer-status.v1',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'mode': mode,
            'exit_code': int(exit_code),
            'detail': detail[-1000:],
        })
    except OSError:
        pass


def _load_previous_snapshot(repo_root: Path) -> dict | None:
    path = _snapshot_dir(repo_root) / 'latest.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    end = payload.get('bootstrap_end') or {}
    if payload.get('schema') != 'bootstrap.v1' or end.get('status') != 'COMPLETE' or end.get('schema') != 'bootstrap.v1':
        return None
    return payload


def _build_degraded_snapshot(
    previous: dict,
    *,
    reason: str,
    exit_code: int,
    refresh_mode: str,
    reason_code: str,
    warning: str,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    payload = dict(previous)
    previous_generated_at = payload.get('generated_at')
    payload['generated_at'] = now
    payload['bootstrap_warning'] = warning
    bootstrap = dict(payload.get('bootstrap') or {})
    bootstrap.update({
        'status': 'DEGRADED',
        'self_check': 'DEGRADED',
        'refresh_mode': refresh_mode,
        'refresh_failure': reason[-1000:],
        'refresh_exit_code': int(exit_code),
        'carried_forward_from': previous_generated_at,
        'agent_contract': {
            'status': 'UNKNOWN',
            'reason': reason_code,
            'carried_forward_from': previous_generated_at,
        },
    })
    payload['bootstrap'] = bootstrap
    for section in ('swarm_topology', 'live_swarm', 'mcp', 'vault', 'github', 'source_freshness', 'pc', 'workers',
                    'mcp_current_topology', 'mcp_recovery_state', 'memory_overview'):
        if section in payload:
            payload[section] = {
                'available': False,
                'status': 'UNKNOWN',
                'reason': reason_code,
                'carried_forward_from': previous_generated_at,
            }
    payload['bootstrap_end'] = {'status': 'COMPLETE', 'schema': 'bootstrap.v1'}
    return payload


def _publish_degraded_snapshot(repo_root: Path, *, reason: str, exit_code: int) -> bool:
    lock = _acquire_snapshot_write_lock(repo_root)
    try:
        previous = _load_previous_snapshot(repo_root)
        if previous is None:
            return False
        payload = _build_degraded_snapshot(
            previous,
            reason=reason,
            exit_code=exit_code,
            refresh_mode='DEGRADED_CARRY_FORWARD',
            reason_code='full_bootstrap_refresh_failed',
            warning=(
                'BOOTSTRAP REFRESH DEGRADED: the full bootstrap-glance refresh failed. '
                'Live/current sections are UNKNOWN until a full refresh succeeds.'
            ),
        )
        _write_json_atomic(_snapshot_dir(repo_root) / 'latest.json', payload)
    finally:
        _release_producer_lock(lock)
    _write_producer_status(repo_root, mode='DEGRADED', detail=reason, exit_code=exit_code)
    return True

def _publish_resource_pressure_snapshot(repo_root: Path, *, pressure: dict, quiet: bool) -> bool:
    lock = _acquire_snapshot_write_lock(repo_root)
    try:
        previous = _load_previous_snapshot(repo_root)
        if previous is None:
            return False
        reason = (
            'full bootstrap refresh load-shed under severe local resource pressure: '
            + ','.join(str(item) for item in pressure.get('reasons') or ['unknown'])
        )
        payload = _build_degraded_snapshot(
            previous,
            reason=reason,
            exit_code=0,
            refresh_mode='RESOURCE_PRESSURE_SHED',
            reason_code='severe_local_resource_pressure',
            warning=(
                'BOOTSTRAP RESOURCE-PRESSURE SHED: the heavy full refresh was intentionally skipped '
                'to avoid worsening a severely memory-constrained machine. This envelope is fresh, '
                'but live/current sections are UNKNOWN until a later full refresh succeeds.'
            ),
        )
        bootstrap = dict(payload.get('bootstrap') or {})
        bootstrap['resource_pressure'] = pressure
        payload['bootstrap'] = bootstrap
        _write_json_atomic(_snapshot_dir(repo_root) / 'latest.json', payload)
    finally:
        _release_producer_lock(lock)
    _write_producer_status(repo_root, mode='RESOURCE_PRESSURE_SHED', detail=reason, exit_code=0)
    if not quiet:
        print(json.dumps(payload, separators=(',', ':'), ensure_ascii=False), flush=True)
    return True


def snapshot_age_seconds(repo_root: Path) -> tuple[float, str]:
    path = _snapshot_dir(repo_root) / 'latest.json'
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return float('inf'), 'MISSING'
    except (OSError, json.JSONDecodeError):
        return float('inf'), 'UNREADABLE'
    end = payload.get('bootstrap_end') or {}
    if payload.get('schema') != 'bootstrap.v1' or end.get('status') != 'COMPLETE' or end.get('schema') != 'bootstrap.v1':
        return float('inf'), 'INVALID'
    generated_raw = payload.get('generated_at')
    if not isinstance(generated_raw, str) or not generated_raw.strip():
        return float('inf'), 'INVALID_GENERATED_AT'
    try:
        generated = datetime.fromisoformat(generated_raw.strip().replace('Z', '+00:00'))
    except ValueError:
        return float('inf'), 'INVALID_GENERATED_AT'
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds()
    if age < -5:
        return float('inf'), 'FUTURE_GENERATED_AT'
    bootstrap = payload.get('bootstrap') or {}
    status = 'OK' if bootstrap.get('status', 'OK') == 'OK' else 'DEGRADED'
    return max(0.0, age), status


def publish_watchdog_heartbeat(
    repo_root: Path,
    *,
    older_than_seconds: float,
    quiet: bool = False,
) -> bool:
    repo_root = repo_root.resolve()
    threshold = max(0.0, older_than_seconds)
    lock = _acquire_snapshot_write_lock(repo_root)
    try:
        previous = _load_previous_snapshot(repo_root)
        if previous is None:
            _write_producer_status(
                repo_root,
                mode='WATCHDOG_HEARTBEAT_UNAVAILABLE',
                detail='no previous COMPLETE bootstrap snapshot available',
                exit_code=1,
            )
            return False
        age, _status = snapshot_age_seconds(repo_root)
        if age <= threshold:
            _write_producer_status(repo_root, mode='WATCHDOG_SKIPPED_FRESH', exit_code=0)
            return True
        age_label = 'unknown' if age == float('inf') else f'{age:.1f}s'
        reason = (
            f'watchdog heartbeat published because the last COMPLETE snapshot age {age_label} '
            f'exceeded {threshold:.1f}s while the primary refresh may be delayed or resource-starved'
        )
        payload = _build_degraded_snapshot(
            previous,
            reason=reason,
            exit_code=0,
            refresh_mode='WATCHDOG_HEARTBEAT',
            reason_code='primary_refresh_overdue_or_resource_pressure',
            warning=(
                'BOOTSTRAP WATCHDOG HEARTBEAT: the full refresh is overdue or still in progress. '
                'This envelope is fresh, but live/current sections are UNKNOWN until the primary full refresh succeeds.'
            ),
        )
        _write_json_atomic(_snapshot_dir(repo_root) / 'latest.json', payload)
    finally:
        _release_producer_lock(lock)
    _write_producer_status(repo_root, mode='WATCHDOG_HEARTBEAT', detail=reason, exit_code=0)
    if not quiet:
        print(json.dumps(payload, separators=(',', ':'), ensure_ascii=False), flush=True)
    return True


def _try_acquire_lock_path(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open('a+b')
    try:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                stream.close()
                return None
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                stream.close()
                return None
        return stream
    except Exception:
        stream.close()
        raise


def _try_acquire_producer_lock(repo_root: Path):
    return _try_acquire_lock_path(_snapshot_dir(repo_root) / 'producer.lock')


def _try_acquire_snapshot_write_lock(repo_root: Path):
    return _try_acquire_lock_path(_snapshot_dir(repo_root) / 'snapshot-write.lock')


def _acquire_snapshot_write_lock(repo_root: Path, *, timeout_seconds: float = 0.5):
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        lock = _try_acquire_snapshot_write_lock(repo_root)
        if lock is not None:
            return lock
        if time.monotonic() >= deadline:
            raise TimeoutError('timed out acquiring bootstrap snapshot write lock')
        time.sleep(0.005)


def _release_producer_lock(stream) -> None:
    try:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def _emit_singleflight(repo_root: Path, *, quiet: bool, atlas_path: Path | None = None) -> bool:
    lock = _try_acquire_producer_lock(repo_root)
    if lock is None:
        _write_producer_status(repo_root, mode='SKIPPED_INFLIGHT', exit_code=0)
        return True
    try:
        pressure = _windows_resource_pressure()
        if pressure is not None and _publish_resource_pressure_snapshot(repo_root, pressure=pressure, quiet=quiet):
            return True
        return emit_snapshot(repo_root, quiet=quiet, atlas_path=atlas_path)
    finally:
        _release_producer_lock(lock)

def emit_snapshot(repo_root: Path = DEFAULT_REPO_ROOT, *, quiet: bool = False, atlas_path: Path | None = None) -> bool:
    repo_root = repo_root.resolve()
    atlas = (atlas_path or (repo_root / 'tools' / 'stack_atlas.py')).resolve()
    if atlas_path is not None:
        _sync_deployed_atlas_from_source_ref(repo_root, atlas)
    cp = _run_bootstrap_glance(repo_root, atlas)
    if cp.returncode != 0:
        detail = (cp.stderr or f'bootstrap-glance exited {cp.returncode}')[-1000:]
        if _publish_degraded_snapshot(repo_root, reason=detail, exit_code=cp.returncode):
            if not quiet:
                print((_snapshot_dir(repo_root) / 'latest.json').read_text(encoding='utf-8'), flush=True)
            return True
        print(json.dumps({
            'stream_schema': 'bootstrap-read-stream.v1',
            'error': 'bootstrap-glance failed and no previous COMPLETE snapshot was available',
            'exit_code': cp.returncode,
            'repo_root': str(repo_root),
            'stderr_tail': detail,
        }, separators=(',', ':')), flush=True)
        _write_producer_status(repo_root, mode='FAILED', detail=detail, exit_code=cp.returncode)
        return False
    try:
        payload = json.loads(cp.stdout.lstrip('\ufeff'))
    except json.JSONDecodeError as exc:
        detail = f'invalid bootstrap-glance JSON: {exc}'
        if _publish_degraded_snapshot(repo_root, reason=detail, exit_code=2):
            if not quiet:
                print((_snapshot_dir(repo_root) / 'latest.json').read_text(encoding='utf-8'), flush=True)
            return True
        raise
    end = payload.get('bootstrap_end') or {}
    if (payload.get('schema') != 'bootstrap.v1' or not payload.get('generated_at')
            or end.get('status') != 'COMPLETE' or end.get('schema') != 'bootstrap.v1'):
        detail = 'bootstrap-glance returned invalid bootstrap.v1 payload'
        if _publish_degraded_snapshot(repo_root, reason=detail, exit_code=2):
            if not quiet:
                print((_snapshot_dir(repo_root) / 'latest.json').read_text(encoding='utf-8'), flush=True)
            return True
        raise RuntimeError(detail)
    payload = _overlay_current_memory(payload, repo_root)
    encoded = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
    if len(encoded.encode('utf-8')) > 64 * 1024:
        raise RuntimeError('bootstrap snapshot exceeds 64 KiB producer limit')
    snapshot_lock = _acquire_snapshot_write_lock(repo_root)
    try:
        _write_json_atomic(_snapshot_dir(repo_root) / 'latest.json', payload)
    finally:
        _release_producer_lock(snapshot_lock)
    _write_producer_status(repo_root, mode='FULL', exit_code=0)
    if not quiet:
        print(encoded, flush=True)
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval-seconds', type=float, default=30.0)
    ap.add_argument(
        '--repo-root',
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help='Repository root that owns snapshot state and live/root authority.',
    )
    ap.add_argument(
        '--atlas-path',
        type=Path,
        default=None,
        help='Optional deployed Stack Atlas script; live/root authority remains --repo-root.',
    )
    ap.add_argument('--once', action='store_true', help='Emit one snapshot and exit.')
    ap.add_argument('--quiet', action='store_true', help='Publish the snapshot file without repeating it on stdout.')
    ap.add_argument(
        '--skip-if-fresh-seconds',
        type=float,
        default=None,
        help='Skip bootstrap-glance when the current COMPLETE snapshot is no older than this threshold.',
    )
    ap.add_argument(
        '--heartbeat-if-older-than-seconds',
        type=float,
        default=None,
        help='Watchdog-only mode: publish a lightweight fresh DEGRADED envelope when the COMPLETE snapshot is older than this threshold; never run bootstrap-glance.',
    )
    args = ap.parse_args()
    interval = max(5.0, args.interval_seconds)
    repo_root = args.repo_root.resolve()
    atlas_path = None if args.atlas_path is None else args.atlas_path.resolve()
    skip_if_fresh = None if args.skip_if_fresh_seconds is None else max(0.0, args.skip_if_fresh_seconds)
    heartbeat_if_older = None if args.heartbeat_if_older_than_seconds is None else max(0.0, args.heartbeat_if_older_than_seconds)
    if skip_if_fresh is not None and heartbeat_if_older is not None:
        ap.error('--skip-if-fresh-seconds and --heartbeat-if-older-than-seconds are mutually exclusive')
    while True:
        started = time.monotonic()
        ok = False
        try:
            _sync_deployed_runtime_bundle_from_source_ref(repo_root, atlas_path)
            if heartbeat_if_older is not None:
                ok = publish_watchdog_heartbeat(
                    repo_root, older_than_seconds=heartbeat_if_older, quiet=args.quiet
                )
            elif skip_if_fresh is not None:
                age, status = snapshot_age_seconds(repo_root)
                if status == 'OK' and age <= skip_if_fresh:
                    _write_producer_status(repo_root, mode='SKIPPED_FRESH', exit_code=0)
                    ok = True
                else:
                    ok = _emit_singleflight(repo_root, quiet=args.quiet, atlas_path=atlas_path)
            else:
                ok = _emit_singleflight(repo_root, quiet=args.quiet, atlas_path=atlas_path)
        except Exception as exc:
            print(json.dumps({
                'stream_schema': 'bootstrap-read-stream.v1',
                'error': type(exc).__name__,
                'detail': str(exc)[:1000],
                'repo_root': str(repo_root),
            }, separators=(',', ':')), flush=True)
        if args.once:
            return 0 if ok else 1
        elapsed = time.monotonic() - started
        time.sleep(max(0.5, interval - elapsed))


if __name__ == '__main__':
    raise SystemExit(main())
