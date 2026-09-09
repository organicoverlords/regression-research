import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = HERE.parent


def emit_snapshot(repo_root: Path = DEFAULT_REPO_ROOT) -> bool:
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
        print(json.dumps({
            'stream_schema': 'bootstrap-read-stream.v1',
            'error': 'bootstrap-glance failed',
            'exit_code': cp.returncode,
            'repo_root': str(repo_root),
            'stderr_tail': cp.stderr[-1000:],
        }, separators=(',', ':')), flush=True)
        return False
    payload = json.loads(cp.stdout.lstrip('\ufeff'))
    if payload.get('schema') != 'bootstrap.v1' or not payload.get('generated_at'):
        raise RuntimeError('bootstrap-glance returned invalid bootstrap.v1 payload')
    print(json.dumps(payload, separators=(',', ':'), ensure_ascii=False), flush=True)
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
    args = ap.parse_args()
    interval = max(5.0, args.interval_seconds)
    repo_root = args.repo_root.resolve()
    while True:
        started = time.monotonic()
        ok = False
        try:
            ok = emit_snapshot(repo_root)
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
