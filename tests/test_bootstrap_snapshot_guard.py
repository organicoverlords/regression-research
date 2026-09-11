import importlib.util
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / 'tools' / 'bootstrap_snapshot_guard.py'
INSTALLER = REPO_ROOT / 'tools' / 'install_bootstrap_snapshot_task.ps1'


def _load_guard():
    spec = importlib.util.spec_from_file_location('bootstrap_snapshot_guard_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_snapshot(root: Path, generated_at: datetime) -> None:
    path = root / '.state' / 'bootstrap' / 'latest.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'schema': 'bootstrap.v1',
        'generated_at': generated_at.astimezone(timezone.utc).isoformat(),
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }), encoding='utf-8')


def test_watchdog_is_cheap_noop_for_fresh_snapshot(monkeypatch, tmp_path: Path) -> None:
    guard = _load_guard()
    now = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)
    _write_snapshot(tmp_path, now - timedelta(seconds=20))
    monkeypatch.setattr(guard, '_run_refresh', lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('refresh must not run')))
    monkeypatch.setattr(guard, '_end_primary_task', lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError('primary must not be ended')))

    state = guard.watchdog_once(
        tmp_path,
        stale_seconds=65,
        timeout_seconds=15,
        primary_task_name='VaultBootstrapSnapshot',
        now=now,
    )

    assert state['ok'] is True
    assert state['action'] == 'NOOP_FRESH'
    assert state['snapshot_age_seconds_before'] == 20


def test_watchdog_repairs_stale_snapshot_and_clears_primary(monkeypatch, tmp_path: Path) -> None:
    guard = _load_guard()
    now = datetime(2026, 9, 11, 2, 0, tzinfo=timezone.utc)
    _write_snapshot(tmp_path, now - timedelta(seconds=75))
    calls = []

    def end_primary(name: str):
        calls.append(('end', name))
        return {'ok': True, 'action': 'END_PRIMARY_OK'}

    def refresh(root: Path, *, timeout_seconds: float):
        calls.append(('refresh', timeout_seconds))
        _write_snapshot(root, datetime.now(timezone.utc))
        return {'ok': True, 'action': 'REFRESH_OK'}

    monkeypatch.setattr(guard, '_end_primary_task', end_primary)
    monkeypatch.setattr(guard, '_run_refresh', refresh)

    state = guard.watchdog_once(
        tmp_path,
        stale_seconds=65,
        timeout_seconds=15,
        primary_task_name='VaultBootstrapSnapshot',
        now=now,
    )

    assert calls == [('end', 'VaultBootstrapSnapshot'), ('refresh', 15)]
    assert state['ok'] is True
    assert state['action'] == 'RECOVERED'
    assert state['snapshot_status_after'] == 'OK'


def test_invalid_snapshot_is_recovery_condition(monkeypatch, tmp_path: Path) -> None:
    guard = _load_guard()
    path = tmp_path / '.state' / 'bootstrap' / 'latest.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema":"bootstrap.v1"}', encoding='utf-8')
    monkeypatch.setattr(guard, '_end_primary_task', lambda _name: {'ok': True, 'action': 'END_PRIMARY_OK'})

    def refresh(root: Path, *, timeout_seconds: float):
        _write_snapshot(root, datetime.now(timezone.utc))
        return {'ok': True, 'action': 'REFRESH_OK', 'timeout_seconds': timeout_seconds}

    monkeypatch.setattr(guard, '_run_refresh', refresh)
    state = guard.watchdog_once(tmp_path, stale_seconds=65, timeout_seconds=15, primary_task_name='VaultBootstrapSnapshot')
    assert state['snapshot_status_before'] == 'INVALID'
    assert state['action'] == 'RECOVERED'


def test_refresh_timeout_is_hard_bounded(tmp_path: Path) -> None:
    guard = _load_guard()
    tools = tmp_path / 'tools'
    tools.mkdir(parents=True)
    (tools / 'bootstrap_read_loop.py').write_text('import time\ntime.sleep(5)\n', encoding='utf-8')

    started = time.monotonic()
    result = guard._run_refresh(tmp_path, timeout_seconds=0.2)
    elapsed = time.monotonic() - started

    assert result['ok'] is False
    assert result['action'] == 'REFRESH_TIMEOUT'
    assert elapsed < 2.5


def test_installer_registers_bounded_primary_and_independent_watchdog() -> None:
    text = INSTALLER.read_text(encoding='utf-8')
    assert "VaultBootstrapSnapshotWatchdog" in text
    assert "bootstrap_snapshot_guard.py" in text
    assert "--refresh --timeout-seconds 15" in text
    assert "--watchdog --stale-seconds 55 --timeout-seconds 15" in text
    assert text.count("-MultipleInstances IgnoreNew") >= 2
    assert "$baseStart.AddSeconds(15)" in text
    assert "Existing $TaskName task uses an unknown action; preserved without changes" in text
