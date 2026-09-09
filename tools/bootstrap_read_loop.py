import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parent


def load_snapshot(repo_root: Path = DEFAULT_REPO_ROOT) -> dict:
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
    )
    if cp.returncode != 0:
        raise RuntimeError(json.dumps({
            'stream_schema': 'bootstrap-read-stream.v1',
            'error': 'bootstrap-glance failed',
            'exit_code': cp.returncode,
            'repo_root': str(repo_root),
            'stderr_tail': cp.stderr[-1000:],
        }, separators=(',', ':')))
    payload = json.loads(cp.stdout.lstrip('\ufeff'))
    if payload.get('schema') != 'bootstrap.v1' or not payload.get('generated_at'):
        raise RuntimeError('bootstrap-glance returned invalid bootstrap.v1 payload')
    return payload


def emit_payload(payload: dict, *, cache_used: bool, cache_age_seconds: float, refresh_seconds: float) -> None:
    view = dict(payload)
    view['stream_cache'] = {
        'used': cache_used,
        'age_seconds': round(max(0.0, cache_age_seconds), 3),
        'refresh_seconds': refresh_seconds,
    }
    print(json.dumps(view, separators=(',', ':'), ensure_ascii=False), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval-seconds', type=float, default=30.0)
    ap.add_argument('--refresh-seconds', type=float, default=60.0, help='Minimum seconds between full bootstrap recomputations in repeated mode.')
    ap.add_argument(
        '--repo-root',
        type=Path,
        default=DEFAULT_REPO_ROOT,
        help='Repository root whose tools/stack_atlas.py supplies bootstrap snapshots.',
    )
    ap.add_argument('--once', action='store_true', help='Emit one snapshot and exit.')
    args = ap.parse_args()
    interval = max(5.0, args.interval_seconds)
    refresh_seconds = max(interval, args.refresh_seconds)
    repo_root = args.repo_root.resolve()
    cached_payload: dict | None = None
    cached_at: float | None = None
    next_refresh_at = 0.0
    while True:
        started = time.monotonic()
        refreshed = False
        ok = cached_payload is not None
        if args.once or started >= next_refresh_at:
            next_refresh_at = started + refresh_seconds
            try:
                cached_payload = load_snapshot(repo_root)
                cached_at = time.monotonic()
                refreshed = True
                ok = True
            except Exception as exc:
                detail = str(exc)
                try:
                    parsed = json.loads(detail)
                except json.JSONDecodeError:
                    parsed = {
                        'stream_schema': 'bootstrap-read-stream.v1',
                        'error': type(exc).__name__,
                        'detail': detail[:1000],
                        'repo_root': str(repo_root),
                    }
                print(json.dumps(parsed, separators=(',', ':')), flush=True)
                ok = cached_payload is not None
        if cached_payload is not None and (refreshed or args.once):
            age = max(0.0, time.monotonic() - (cached_at or started))
            emit_payload(cached_payload, cache_used=False, cache_age_seconds=age, refresh_seconds=refresh_seconds)
        if args.once:
            return 0 if ok else 1
        elapsed = time.monotonic() - started
        time.sleep(max(0.5, interval - elapsed))


if __name__ == '__main__':
    raise SystemExit(main())
