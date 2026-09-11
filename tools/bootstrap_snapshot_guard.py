from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parent
DEFAULT_STALE_SECONDS = 65.0
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_PRIMARY_TASK_NAME = 'VaultBootstrapSnapshot'


def _creationflags() -> int:
    if os.name != 'nt':
        return 0
    return int(getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def _worker_python() -> str:
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.name.casefold() == 'pythonw.exe':
        console = executable.with_name('python.exe')
        if console.exists():
            return str(console)
    return str(executable)


def _snapshot_path(repo_root: Path) -> Path:
    return repo_root.resolve() / '.state' / 'bootstrap' / 'latest.json'


def _parse_generated_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def snapshot_age_seconds(repo_root: Path, *, now: datetime | None = None) -> tuple[float, str]:
    path = _snapshot_path(repo_root)
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        return float('inf'), 'MISSING'
    except (OSError, json.JSONDecodeError):
        return float('inf'), 'UNREADABLE'
    end = payload.get('bootstrap_end') or {}
    if payload.get('schema') != 'bootstrap.v1' or end.get('status') != 'COMPLETE' or end.get('schema') != 'bootstrap.v1':
        return float('inf'), 'INVALID'
    generated = _parse_generated_at(payload.get('generated_at'))
    if generated is None:
        return float('inf'), 'INVALID_GENERATED_AT'
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    delta = (current - generated).total_seconds()
    if delta < -5:
        return float('inf'), 'FUTURE_GENERATED_AT'
    return max(0.0, delta), 'OK'


def _terminate_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(
                ['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=_creationflags(),
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _run_refresh(repo_root: Path, *, timeout_seconds: float) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    producer = repo_root / 'tools' / 'bootstrap_read_loop.py'
    command = [
        _worker_python(), str(producer), '--once', '--quiet', '--repo-root', str(repo_root),
    ]
    started = datetime.now(timezone.utc)
    process = subprocess.Popen(
        command,
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        creationflags=_creationflags(),
    )
    try:
        stdout, stderr = process.communicate(timeout=max(0.1, timeout_seconds))
    except subprocess.TimeoutExpired:
        _terminate_tree(process)
        return {
            'ok': False,
            'action': 'REFRESH_TIMEOUT',
            'pid': process.pid,
            'timeout_seconds': timeout_seconds,
            'started_at': started.isoformat(),
        }
    return {
        'ok': process.returncode == 0,
        'action': 'REFRESH_OK' if process.returncode == 0 else 'REFRESH_FAILED',
        'pid': process.pid,
        'exit_code': process.returncode,
        'stderr_tail': stderr[-1000:],
        'stdout_tail': stdout[-1000:],
        'started_at': started.isoformat(),
    }


def _end_primary_task(task_name: str) -> dict[str, Any]:
    if os.name != 'nt':
        return {'ok': True, 'action': 'END_PRIMARY_SKIPPED_NON_WINDOWS'}
    try:
        cp = subprocess.run(
            ['schtasks.exe', '/End', '/TN', task_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=5,
            creationflags=_creationflags(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'ok': False, 'action': 'END_PRIMARY_FAILED', 'detail': type(exc).__name__}
    return {
        'ok': cp.returncode == 0,
        'action': 'END_PRIMARY_OK' if cp.returncode == 0 else 'END_PRIMARY_NOT_RUNNING',
        'exit_code': cp.returncode,
    }


def _write_guard_state(repo_root: Path, state: dict[str, Any]) -> None:
    destination = repo_root.resolve() / '.state' / 'bootstrap' / 'guard-state.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(state, separators=(',', ':'), ensure_ascii=False)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=destination.parent, suffix='.tmp', delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def refresh_once(repo_root: Path, *, timeout_seconds: float) -> dict[str, Any]:
    result = _run_refresh(repo_root, timeout_seconds=timeout_seconds)
    age, status = snapshot_age_seconds(repo_root)
    state = {
        'schema': 'bootstrap-snapshot-guard.v1',
        'mode': 'PRIMARY',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'result': result,
        'snapshot_age_seconds': age if age != float('inf') else None,
        'snapshot_status': status,
        'ok': bool(result.get('ok')) and status == 'OK',
    }
    _write_guard_state(repo_root, state)
    return state


def watchdog_once(
    repo_root: Path,
    *,
    stale_seconds: float,
    timeout_seconds: float,
    primary_task_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    age, status = snapshot_age_seconds(repo_root, now=now)
    checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    state: dict[str, Any] = {
        'schema': 'bootstrap-snapshot-guard.v1',
        'mode': 'WATCHDOG',
        'checked_at': checked_at.isoformat(),
        'threshold_seconds': stale_seconds,
        'snapshot_age_seconds_before': age if age != float('inf') else None,
        'snapshot_status_before': status,
    }
    if status == 'OK' and age <= stale_seconds:
        state.update({'ok': True, 'action': 'NOOP_FRESH'})
        _write_guard_state(repo_root, state)
        return state

    state['primary_end'] = _end_primary_task(primary_task_name)
    state['recovery'] = _run_refresh(repo_root, timeout_seconds=timeout_seconds)
    after_age, after_status = snapshot_age_seconds(repo_root)
    state['snapshot_age_seconds_after'] = after_age if after_age != float('inf') else None
    state['snapshot_status_after'] = after_status
    state['action'] = 'RECOVERED' if state['recovery'].get('ok') and after_status == 'OK' else 'RECOVERY_FAILED'
    state['ok'] = state['action'] == 'RECOVERED'
    _write_guard_state(repo_root, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--refresh', action='store_true', help='Run one hard-bounded snapshot producer invocation.')
    mode.add_argument('--watchdog', action='store_true', help='Repair only when the current snapshot exceeds the stale threshold.')
    parser.add_argument('--repo-root', type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument('--timeout-seconds', type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument('--stale-seconds', type=float, default=DEFAULT_STALE_SECONDS)
    parser.add_argument('--primary-task-name', default=DEFAULT_PRIMARY_TASK_NAME)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    if args.refresh:
        result = refresh_once(repo_root, timeout_seconds=max(0.1, args.timeout_seconds))
    else:
        result = watchdog_once(
            repo_root,
            stale_seconds=max(1.0, args.stale_seconds),
            timeout_seconds=max(0.1, args.timeout_seconds),
            primary_task_name=args.primary_task_name,
        )
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
