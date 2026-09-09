import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "bootstrap_read_loop.py"


def _write_fake_atlas(root: Path) -> None:
    tools = root / "tools"
    tools.mkdir(parents=True)
    (tools / "stack_atlas.py").write_text(
        "import json\n"
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
