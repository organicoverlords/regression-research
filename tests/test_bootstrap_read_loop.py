import json
import subprocess
import sys

import pytest
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
        "'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'}"
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
    assert json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8')) == payload
    assert not list((alternate / '.state' / 'bootstrap').glob('*.tmp'))


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


def test_invalid_update_preserves_previous_snapshot(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    command = [sys.executable, str(SCRIPT), '--once', '--quiet', '--repo-root', str(alternate)]
    good = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert good.returncode == 0, good.stderr
    assert good.stdout == ''
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    previous = destination.read_bytes()
    (alternate / 'tools' / 'stack_atlas.py').write_text("print('{}')", encoding='utf-8')
    failed = subprocess.run(command, capture_output=True, text=True, timeout=20)
    assert failed.returncode == 1
    assert destination.read_bytes() == previous


def test_replace_snapshot_retries_transient_windows_permission_error(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_retry_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    source = tmp_path / 'source.tmp'
    destination = tmp_path / 'latest.json'
    source.write_text('new', encoding='utf-8')
    destination.write_text('old', encoding='utf-8')
    real_replace = module.os.replace
    attempts = {'count': 0}

    def transient_replace(src, dst):
        attempts['count'] += 1
        if attempts['count'] <= 3:
            raise PermissionError('destination temporarily held open')
        return real_replace(src, dst)

    monkeypatch.setattr(module.os, 'name', 'nt')
    monkeypatch.setattr(module.os, 'replace', transient_replace)
    monkeypatch.setattr(module.time, 'sleep', lambda _seconds: None)
    module._replace_snapshot(source, destination, retry_seconds=0.5)

    assert attempts['count'] == 4
    assert destination.read_text(encoding='utf-8') == 'new'


def test_replace_snapshot_fails_closed_after_retry_deadline(monkeypatch, tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_retry_deadline_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    source = tmp_path / 'source.tmp'
    destination = tmp_path / 'latest.json'
    source.write_text('new', encoding='utf-8')
    destination.write_text('old', encoding='utf-8')
    monkeypatch.setattr(module.os, 'name', 'nt')
    monkeypatch.setattr(module.os, 'replace', lambda *_args: (_ for _ in ()).throw(PermissionError('locked')))

    with pytest.raises(PermissionError):
        module._replace_snapshot(source, destination, retry_seconds=0)
    assert source.exists()
    assert destination.read_text(encoding='utf-8') == 'old'
