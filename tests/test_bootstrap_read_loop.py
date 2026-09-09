import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "bootstrap_read_loop.py"


def _write_fake_atlas(root: Path, counter: Path | None = None) -> None:
    tools = root / "tools"
    tools.mkdir(parents=True)
    counter_code = ""
    if counter is not None:
        counter_code = (
            "from pathlib import Path\n"
            f"p=Path({str(counter)!r})\n"
            "n=int(p.read_text() or '0') if p.exists() else 0\n"
            "p.write_text(str(n+1))\n"
        )
    (tools / "stack_atlas.py").write_text(
        "import json\n" + counter_code +
        "print(json.dumps({"
        "'bootstrap_warning': {'status': 'READ_TO_END'}, "
        "'schema': 'bootstrap.v1', "
        "'generated_at': '2026-09-09T09:00:00+00:00', "
        "'source_marker': 'alternate-root', "
        "'bootstrap_end': {'status': 'COMPLETE'}"
        "}))\n",
        encoding="utf-8",
    )


def test_once_uses_explicit_repo_root(tmp_path: Path) -> None:
    alternate = tmp_path / "alternate"
    _write_fake_atlas(alternate)

    cp = subprocess.run(
        [sys.executable, str(SCRIPT), "--once", "--repo-root", str(alternate)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )

    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout.lstrip("\ufeff"))
    assert payload["schema"] == "bootstrap.v1"
    assert payload["source_marker"] == "alternate-root"
    assert payload["bootstrap_end"]["status"] == "COMPLETE"


def test_once_missing_repo_root_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    cp = subprocess.run(
        [sys.executable, str(SCRIPT), "--once", "--repo-root", str(missing)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )

    assert cp.returncode == 1
    payload = json.loads(cp.stdout.lstrip("\ufeff"))
    assert payload["stream_schema"] == "bootstrap-read-stream.v1"
    assert payload["repo_root"] == str(missing.resolve())


def test_repeated_mode_reuses_snapshot_until_refresh_due(tmp_path: Path) -> None:
    alternate = tmp_path / "alternate"
    counter = tmp_path / "atlas-count.txt"
    _write_fake_atlas(alternate, counter)

    proc = subprocess.Popen(
        [
            sys.executable, str(SCRIPT),
            "--repo-root", str(alternate),
            "--interval-seconds", "5",
            "--refresh-seconds", "60",
        ],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        assert proc.stdout is not None
        first = json.loads(proc.stdout.readline().lstrip("\ufeff"))
        second = json.loads(proc.stdout.readline().lstrip("\ufeff"))
    finally:
        proc.terminate()
        proc.wait(timeout=10)

    assert counter.read_text() == "1"
    assert first["stream_cache"]["used"] is False
    assert second["stream_cache"]["used"] is True
    assert second["source_marker"] == "alternate-root"
