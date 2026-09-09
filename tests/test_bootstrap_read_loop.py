import json
import os
import subprocess
import sys

import pytest
from pathlib import Path

from tools.memory_recent_projection import write_recent_projection


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
        "'memory_overview': {"
        "'recent': [{'id':'materialized-old','timestamp':'2026-09-09T09:00:00+00:00','title':'materialized old'}], "
        "'timeline_materialized': {'as_of':'2026-09-09T09:00:00+00:00','read_mode':'MATERIALIZED_ONLY'}"
        "}, "
        "'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'}"
        "}))\n",
        encoding="utf-8",
    )


def _memory_files(root: Path, tmp_path: Path) -> tuple[Path, Path]:
    seed = root / 'memory' / 'memory-bank.jsonl'
    overlay = tmp_path / 'local-memory' / 'memory-bank.local.jsonl'
    seed.parent.mkdir(parents=True, exist_ok=True)
    overlay.parent.mkdir(parents=True, exist_ok=True)
    seed.write_text('', encoding='utf-8')
    overlay.write_text('', encoding='utf-8')
    return seed, overlay


def _run_once(alternate: Path, overlay: Path, *, quiet: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['VAULT_MEMORY_LOCAL_BANK'] = str(overlay)
    command = [sys.executable, str(SCRIPT), '--once', '--repo-root', str(alternate)]
    if quiet:
        command.append('--quiet')
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=20,
        env=env,
    )


def test_once_uses_explicit_repo_root(tmp_path: Path) -> None:
    alternate = tmp_path / "alternate"
    _write_fake_atlas(alternate)
    _, overlay = _memory_files(alternate, tmp_path)

    cp = _run_once(alternate, overlay, quiet=False)

    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout.lstrip("\ufeff"))
    assert payload["schema"] == "bootstrap.v1"
    assert payload["source_marker"] == "alternate-root"
    assert payload["bootstrap_end"]["status"] == "COMPLETE"
    assert json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8')) == payload
    assert not list((alternate / '.state' / 'bootstrap').glob('*.tmp'))


def test_once_overlays_fingerprint_current_recent_memory_projection(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    seed, overlay = _memory_files(alternate, tmp_path)
    recent = [
        {'id': f'mem-fresh-{index}', 'timestamp': f'2026-09-09T20:3{index}:00+03:00', 'title': f'fresh {index}', 'kind': 'lesson', 'scope': 'vault'}
        for index in range(5)
    ]
    write_recent_projection(seed_path=seed, overlay_path=overlay, recent=recent)

    cp = _run_once(alternate, overlay)

    assert cp.returncode == 0, cp.stderr
    assert cp.stdout == ''
    payload = json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8'))
    assert payload['memory_overview']['recent'] == recent[:3]
    source = payload['memory_overview']['recent_source']
    assert source['authority'] == 'DIRECT_LOCAL_EFFECTIVE_MEMORY_PROJECTION'
    assert source['read_mode'] == 'fingerprint_validated_recent_titles_projection'
    assert source['status'] == 'CURRENT_FOR_EFFECTIVE_MEMORY_FILES'
    assert source['generated_at']
    assert payload['memory_overview']['timeline_materialized'] == {
        'as_of': '2026-09-09T09:00:00+00:00',
        'read_mode': 'MATERIALIZED_ONLY',
    }


def test_once_rejects_projection_after_memory_source_changes(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    seed, overlay = _memory_files(alternate, tmp_path)
    write_recent_projection(
        seed_path=seed,
        overlay_path=overlay,
        recent=[{'id':'mem-fresh','timestamp':'2026-09-09T20:35:00+03:00','title':'fresh','kind':'lesson','scope':'vault'}],
    )
    overlay.write_text('{"changed":true}\n', encoding='utf-8')

    cp = _run_once(alternate, overlay)

    assert cp.returncode == 0, cp.stderr
    payload = json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8'))
    assert payload['memory_overview']['recent'] == [
        {'id':'materialized-old','timestamp':'2026-09-09T09:00:00+00:00','title':'materialized old'}
    ]
    assert 'recent_source' not in payload['memory_overview']


def test_once_missing_repo_root_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    overlay = tmp_path / 'local-memory' / 'memory-bank.local.jsonl'

    cp = _run_once(missing, overlay, quiet=False)

    assert cp.returncode == 1
    payload = json.loads(cp.stdout.lstrip("\ufeff"))
    assert payload["stream_schema"] == "bootstrap-read-stream.v1"
    assert payload["repo_root"] == str(missing.resolve())


def test_invalid_update_preserves_previous_snapshot(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    _, overlay = _memory_files(alternate, tmp_path)
    good = _run_once(alternate, overlay)
    assert good.returncode == 0, good.stderr
    assert good.stdout == ''
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    previous = destination.read_bytes()
    (alternate / 'tools' / 'stack_atlas.py').write_text("print('{}')", encoding='utf-8')
    failed = _run_once(alternate, overlay)
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
