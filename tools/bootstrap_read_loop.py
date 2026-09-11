import argparse
import json
import os
import subprocess
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from tools.memory_recent_projection import default_local_bank_path, read_current_projection
except ImportError:
    from memory_recent_projection import default_local_bank_path, read_current_projection

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parent
MEMORY_RECENT_LIMIT = 3

BOOTSTRAP_GLANCE_TIMEOUT_SECONDS = 12.0
PROCESS_TREE_KILL_TIMEOUT_SECONDS = 2.0


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


def _run_bootstrap_glance(repo_root: Path, atlas: Path, *, timeout_seconds: float = BOOTSTRAP_GLANCE_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[str]:
    stdout_path = None
    stderr_path = None
    stdout_stream = None
    stderr_stream = None
    command = [_child_python(), str(atlas), 'bootstrap-glance']
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
            creationflags=_creationflags(),
            close_fds=True,
        )
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


def _load_current_memory_projection(repo_root: Path) -> dict | None:
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


def snapshot_age_seconds(repo_root: Path) -> tuple[float, str]:
    path = repo_root.resolve() / '.state' / 'bootstrap' / 'latest.json'
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
    return max(0.0, age), 'OK'


def emit_snapshot(repo_root: Path = DEFAULT_REPO_ROOT, *, quiet: bool = False) -> bool:
    repo_root = repo_root.resolve()
    atlas = repo_root / 'tools' / 'stack_atlas.py'
    cp = _run_bootstrap_glance(repo_root, atlas)
    if cp.returncode != 0:
        print(json.dumps({
            'stream_schema': 'bootstrap-read-stream.v1',
            'error': 'bootstrap-glance failed',
            'exit_code': cp.returncode,
            'repo_root': str(repo_root),
            'stderr_tail': cp.stderr[-1000:],
        }, separators=(',', ':')), flush=True)
        return False
    payload = json.loads(cp.stdout.lstrip('\ufeff'))
    end = payload.get('bootstrap_end') or {}
    if (payload.get('schema') != 'bootstrap.v1' or not payload.get('generated_at')
            or end.get('status') != 'COMPLETE' or end.get('schema') != 'bootstrap.v1'):
        raise RuntimeError('bootstrap-glance returned invalid bootstrap.v1 payload')
    payload = _overlay_current_memory(payload, repo_root)
    encoded = json.dumps(payload, separators=(',', ':'), ensure_ascii=False)
    if len(encoded.encode('utf-8')) > 64 * 1024:
        raise RuntimeError('bootstrap snapshot exceeds 64 KiB producer limit')
    destination = repo_root / '.state' / 'bootstrap' / 'latest.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
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
        help='Repository root whose tools/stack_atlas.py supplies bootstrap snapshots.',
    )
    ap.add_argument('--once', action='store_true', help='Emit one snapshot and exit.')
    ap.add_argument('--quiet', action='store_true', help='Publish the snapshot file without repeating it on stdout.')
    ap.add_argument(
        '--skip-if-fresh-seconds',
        type=float,
        default=None,
        help='Skip bootstrap-glance when the current COMPLETE snapshot is no older than this threshold.',
    )
    args = ap.parse_args()
    interval = max(5.0, args.interval_seconds)
    repo_root = args.repo_root.resolve()
    skip_if_fresh = None if args.skip_if_fresh_seconds is None else max(0.0, args.skip_if_fresh_seconds)
    while True:
        started = time.monotonic()
        ok = False
        try:
            if skip_if_fresh is not None:
                age, status = snapshot_age_seconds(repo_root)
                if status == 'OK' and age <= skip_if_fresh:
                    ok = True
                else:
                    ok = emit_snapshot(repo_root, quiet=args.quiet)
            else:
                ok = emit_snapshot(repo_root, quiet=args.quiet)
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
