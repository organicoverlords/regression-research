import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ATLAS = HERE / 'stack_atlas.py'


def load_snapshot() -> str | None:
    cp = subprocess.run(
        [sys.executable, str(ATLAS), 'bootstrap-glance'],
        cwd=str(HERE.parent),
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
            'stderr_tail': cp.stderr[-1000:],
        }, separators=(',', ':')), flush=True)
        return None
    payload = json.loads(cp.stdout.lstrip('\ufeff'))
    if payload.get('schema') != 'bootstrap.v1' or not payload.get('generated_at'):
        raise RuntimeError('bootstrap-glance returned invalid bootstrap.v1 payload')
    return json.dumps(payload, separators=(',', ':'), ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval-seconds', type=float, default=30.0)
    args = ap.parse_args()
    interval = max(5.0, args.interval_seconds)
    cached_snapshot: str | None = None
    while True:
        started = time.monotonic()
        try:
            if cached_snapshot is None:
                cached_snapshot = load_snapshot()
            if cached_snapshot is not None:
                print(cached_snapshot, flush=True)
        except Exception as exc:
            print(json.dumps({
                'stream_schema': 'bootstrap-read-stream.v1',
                'error': type(exc).__name__,
                'detail': str(exc)[:1000],
            }, separators=(',', ':')), flush=True)
        elapsed = time.monotonic() - started
        time.sleep(max(0.5, interval - elapsed))


if __name__ == '__main__':
    raise SystemExit(main())
