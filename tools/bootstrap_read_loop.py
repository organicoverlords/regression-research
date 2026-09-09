import argparse
import json
import os
import subprocess
import sys
import time
import tempfile
from pathlib import Path

try:
    from tools.memory_recent_projection import default_local_bank_path, read_current_projection
except ImportError:
    from memory_recent_projection import default_local_bank_path, read_current_projection

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parent
MEMORY_RECENT_LIMIT = 3


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


def emit_snapshot(repo_root: Path = DEFAULT_REPO_ROOT, *, quiet: bool = False) -> bool:
    repo_root = repo_root.resolve()
    atlas = repo_root / 'tools' / 'stack_atlas.py'
    cp = subprocess.run(
        [sys.executable, str(atlas), 'bootstrap-glance'],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=20,
    )
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
    args = ap.parse_args()
    interval = max(5.0, args.interval_seconds)
    repo_root = args.repo_root.resolve()
    while True:
        started = time.monotonic()
        ok = False
        try:
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
