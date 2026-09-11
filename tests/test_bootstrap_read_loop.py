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


def _run_once(
    alternate: Path,
    overlay: Path,
    *,
    quiet: bool = True,
    skip_if_fresh_seconds: float | None = None,
    atlas_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env['VAULT_MEMORY_LOCAL_BANK'] = str(overlay)
    command = [sys.executable, str(SCRIPT), '--once', '--repo-root', str(alternate)]
    if atlas_path is not None:
        command.extend(['--atlas-path', str(atlas_path)])
    if quiet:
        command.append('--quiet')
    if skip_if_fresh_seconds is not None:
        command.extend(['--skip-if-fresh-seconds', str(skip_if_fresh_seconds)])
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


def test_once_can_run_deployed_atlas_outside_repo_root(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    atlas = runtime / 'stack_atlas.py'
    atlas.write_text(
        "import json, os\n"
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':'2026-09-11T11:00:00+00:00',"
        "'source_marker':'runtime-atlas','root_override':os.environ.get('STACK_ATLAS_ROOT_OVERRIDE'),"
        "'pythonpath':os.environ.get('PYTHONPATH',''),'memory_overview':{'recent':[]},"
        "'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    cp = _run_once(alternate, overlay, quiet=False, atlas_path=atlas)
    assert cp.returncode == 0, cp.stderr
    payload = json.loads(cp.stdout.lstrip('\ufeff'))
    assert payload['source_marker'] == 'runtime-atlas'
    assert Path(payload['root_override']) == alternate.resolve()
    assert str(alternate.resolve()) in payload['pythonpath'].split(os.pathsep)


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


def test_invalid_update_publishes_fresh_degraded_snapshot_and_watchdog_retries(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    _, overlay = _memory_files(alternate, tmp_path)
    good = _run_once(alternate, overlay)
    assert good.returncode == 0, good.stderr
    assert good.stdout == ''
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    previous = json.loads(destination.read_text(encoding='utf-8'))

    (alternate / 'tools' / 'stack_atlas.py').write_text("print('{}')", encoding='utf-8')
    degraded_run = _run_once(alternate, overlay)

    assert degraded_run.returncode == 0, degraded_run.stderr
    degraded = json.loads(destination.read_text(encoding='utf-8'))
    assert degraded['generated_at'] != previous['generated_at']
    assert degraded['bootstrap']['status'] == 'DEGRADED'
    assert degraded['bootstrap']['refresh_mode'] == 'DEGRADED_CARRY_FORWARD'
    assert degraded['bootstrap']['carried_forward_from'] == previous['generated_at']
    assert degraded['bootstrap']['agent_contract']['status'] == 'UNKNOWN'
    assert degraded['bootstrap_end'] == {'status': 'COMPLETE', 'schema': 'bootstrap.v1'}
    status = json.loads((destination.parent / 'producer-status.json').read_text(encoding='utf-8'))
    assert status['mode'] == 'DEGRADED'

    marker = tmp_path / 'watchdog-retried.txt'
    (alternate / 'tools' / 'stack_atlas.py').write_text(
        "import json\n"
        "from datetime import datetime, timezone\n"
        "from pathlib import Path\n"
        f"Path(r'{marker}').write_text('retried')\n"
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':datetime.now(timezone.utc).isoformat(),'bootstrap':{'status':'OK'},'memory_overview':{'recent':[]},'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))\n",
        encoding='utf-8',
    )
    retry = _run_once(alternate, overlay, skip_if_fresh_seconds=45)
    assert retry.returncode == 0, retry.stderr
    assert marker.read_text(encoding='utf-8') == 'retried'
    repaired = json.loads(destination.read_text(encoding='utf-8'))
    assert repaired['bootstrap']['status'] == 'OK'


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


def test_glance_capture_does_not_wait_for_inherited_stdout_handles(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    _, overlay = _memory_files(alternate, tmp_path)
    (tools / 'stack_atlas.py').write_text(
        "import json, subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':'2026-09-11T03:00:00+00:00','memory_overview':{'recent':[]},'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}), flush=True)\n",
        encoding='utf-8',
    )

    started = __import__('time').monotonic()
    cp = _run_once(alternate, overlay)
    elapsed = __import__('time').monotonic() - started

    assert cp.returncode == 0, cp.stderr
    assert elapsed < 2.5
    payload = json.loads((alternate / '.state' / 'bootstrap' / 'latest.json').read_text(encoding='utf-8'))
    assert payload['bootstrap_end']['status'] == 'COMPLETE'


def test_glance_timeout_is_bounded_without_pipe_eof_wait(tmp_path: Path) -> None:
    import importlib.util
    import time

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_timeout_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    atlas = tmp_path / 'stack_atlas.py'
    atlas.write_text('import time\ntime.sleep(30)\n', encoding='utf-8')

    started = time.monotonic()
    cp = module._run_bootstrap_glance(tmp_path, atlas, timeout_seconds=0.2)
    elapsed = time.monotonic() - started

    assert cp.returncode == 124
    assert 'timed out after 0.2s' in cp.stderr
    assert elapsed < 4.0


def test_skip_if_fresh_avoids_bootstrap_glance(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    original = {
        'schema': 'bootstrap.v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }
    destination.write_text(json.dumps(original), encoding='utf-8')

    cp = _run_once(alternate, overlay, skip_if_fresh_seconds=45)

    assert cp.returncode == 0, cp.stderr
    assert not marker.exists()
    assert json.loads(destination.read_text(encoding='utf-8')) == original


def test_skip_if_fresh_refreshes_stale_snapshot(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        "import json\n"
        "from datetime import datetime, timezone\n"
        "from pathlib import Path\n"
        f"Path(r'{marker}').write_text('ran')\n"
        "print(json.dumps({'schema':'bootstrap.v1','generated_at':datetime.now(timezone.utc).isoformat(),'memory_overview':{'recent':[]},'bootstrap_end':{'status':'COMPLETE','schema':'bootstrap.v1'}}))\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps({
        'schema': 'bootstrap.v1',
        'generated_at': (datetime.now(timezone.utc) - timedelta(seconds=70)).isoformat(),
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }), encoding='utf-8')

    cp = _run_once(alternate, overlay, skip_if_fresh_seconds=45)

    assert cp.returncode == 0, cp.stderr
    assert marker.read_text(encoding='utf-8') == 'ran'
    payload = json.loads(destination.read_text(encoding='utf-8'))
    assert payload['bootstrap_end']['status'] == 'COMPLETE'
    generated = datetime.fromisoformat(payload['generated_at'])
    assert (datetime.now(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds() < 5


def test_skip_if_fresh_refreshes_invalid_snapshot(tmp_path: Path) -> None:
    alternate = tmp_path / 'alternate'
    _write_fake_atlas(alternate)
    _, overlay = _memory_files(alternate, tmp_path)
    destination = alternate / '.state' / 'bootstrap' / 'latest.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text('{"schema":"bootstrap.v1"}', encoding='utf-8')

    cp = _run_once(alternate, overlay, skip_if_fresh_seconds=45)

    assert cp.returncode == 0, cp.stderr
    payload = json.loads(destination.read_text(encoding='utf-8'))
    assert payload['source_marker'] == 'alternate-root'
    assert payload['bootstrap_end']['status'] == 'COMPLETE'


def test_default_glance_timeout_allows_loaded_but_bounded_refresh() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_timeout_constant_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.BOOTSTRAP_GLANCE_TIMEOUT_SECONDS == 30.0


def test_singleflight_skips_second_producer_while_lock_is_held(tmp_path: Path) -> None:
    import importlib.util
    import time

    alternate = tmp_path / 'alternate'
    tools = alternate / 'tools'
    tools.mkdir(parents=True)
    marker = tmp_path / 'atlas-ran.txt'
    (tools / 'stack_atlas.py').write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n",
        encoding='utf-8',
    )
    _, overlay = _memory_files(alternate, tmp_path)
    spec = importlib.util.spec_from_file_location('bootstrap_read_loop_lock_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    lock = module._try_acquire_producer_lock(alternate)
    assert lock is not None
    try:
        started = time.monotonic()
        cp = _run_once(alternate, overlay)
        elapsed = time.monotonic() - started
    finally:
        module._release_producer_lock(lock)
    assert cp.returncode == 0, cp.stderr
    assert elapsed < 2.0
    assert not marker.exists()
    status = json.loads((alternate / '.state' / 'bootstrap' / 'producer-status.json').read_text(encoding='utf-8'))
    assert status['mode'] == 'SKIPPED_INFLIGHT'
