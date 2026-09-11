import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / 'tools' / 'bootstrap_snapshot_task_runner.ps1'
INSTALLER = REPO_ROOT / 'tools' / 'install_bootstrap_snapshot_task.ps1'


def _pwsh() -> str:
    for name in ('pwsh.exe', 'powershell.exe'):
        cp = subprocess.run(['where.exe', name], capture_output=True, text=True)
        if cp.returncode == 0 and cp.stdout.strip():
            return cp.stdout.splitlines()[0].strip()
    raise RuntimeError('PowerShell unavailable')


def _write_snapshot(root: Path, when: datetime) -> Path:
    path = root / '.state' / 'bootstrap' / 'latest.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        'schema': 'bootstrap.v1',
        'generated_at': when.astimezone(timezone.utc).isoformat(),
        'bootstrap_end': {'status': 'COMPLETE', 'schema': 'bootstrap.v1'},
    }), encoding='utf-8')
    return path


def _write_producer(root: Path, source: str) -> Path:
    tools = root / 'tools'
    tools.mkdir(parents=True, exist_ok=True)
    producer = tools / 'bootstrap_read_loop.py'
    producer.write_text(source, encoding='utf-8')
    return producer


def _run(root: Path, mode: str, *, timeout_seconds: int = 3, stale_seconds: int = 55) -> subprocess.CompletedProcess[str]:
    return subprocess.run([
        _pwsh(), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', str(RUNNER), '-Mode', mode, '-RepoRoot', str(root), '-PythonPath', sys.executable,
        '-ProducerPath', str(root / 'tools' / 'bootstrap_read_loop.py'),
        '-TimeoutSeconds', str(timeout_seconds), '-StaleSeconds', str(stale_seconds),
    ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)


def test_watchdog_fresh_path_is_python_free(tmp_path: Path) -> None:
    marker = tmp_path / 'producer-ran.txt'
    _write_snapshot(tmp_path, datetime.now(timezone.utc))
    _write_producer(tmp_path, f"from pathlib import Path\nPath(r'{marker}').write_text('ran')\n")

    cp = _run(tmp_path, 'Watchdog', stale_seconds=55)

    assert cp.returncode == 0, cp.stderr
    assert not marker.exists()
    state = json.loads((tmp_path / '.state' / 'bootstrap' / 'guard-state.json').read_text(encoding='utf-8-sig'))
    assert state['schema'] == 'bootstrap-snapshot-guard.v2'
    assert state['action'] == 'NOOP_FRESH'
    assert state['ok'] is True


def test_watchdog_recovers_stale_snapshot_independently(tmp_path: Path) -> None:
    marker = tmp_path / 'producer-ran.txt'
    _write_snapshot(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=5))
    producer = f'''import json\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nroot=Path(r"{tmp_path}")\nPath(r"{marker}").write_text("ran")\np=root/".state"/"bootstrap"/"latest.json"\np.parent.mkdir(parents=True, exist_ok=True)\np.write_text(json.dumps({{"schema":"bootstrap.v1","generated_at":datetime.now(timezone.utc).isoformat(),"bootstrap_end":{{"status":"COMPLETE","schema":"bootstrap.v1"}}}}), encoding="utf-8")\n'''
    _write_producer(tmp_path, producer)

    cp = _run(tmp_path, 'Watchdog', timeout_seconds=3, stale_seconds=55)

    assert cp.returncode == 0, cp.stderr
    assert marker.read_text() == 'ran'
    state = json.loads((tmp_path / '.state' / 'bootstrap' / 'guard-state.json').read_text(encoding='utf-8-sig'))
    assert state['action'] == 'RECOVERED'
    assert state['refresh']['action'] == 'REFRESH_OK'
    assert state['snapshot_after']['status'] == 'OK'
    assert state['snapshot_after']['age_seconds'] < 5


def test_primary_timeout_kills_child_tree_without_waiting_for_scheduler(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, datetime.now(timezone.utc) - timedelta(minutes=5))
    child_marker = tmp_path / 'child-alive.txt'
    child_code = f"import time; from pathlib import Path; Path(r'{child_marker}').write_text('alive'); time.sleep(30)"
    producer = f'''import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', {child_code!r}])\ntime.sleep(30)\n'''
    _write_producer(tmp_path, producer)

    started = time.monotonic()
    cp = _run(tmp_path, 'Primary', timeout_seconds=1)
    elapsed = time.monotonic() - started

    assert cp.returncode == 1
    assert elapsed < 5
    state = json.loads((tmp_path / '.state' / 'bootstrap' / 'guard-state.json').read_text(encoding='utf-8-sig'))
    assert state['action'] == 'REFRESH_TIMEOUT'
    assert state['refresh']['action'] == 'REFRESH_TIMEOUT'
    time.sleep(0.4)
    # Process.Kill(true) must kill the producer and its spawned descendant, not just the direct child.
    ps = subprocess.run([
        'powershell.exe', '-NoProfile', '-Command',
        f"@(Get-CimInstance Win32_Process | Where-Object {{$_.Name -like 'python*.exe' -and $_.CommandLine -like '*{child_marker.name}*'}}).Count",
    ], capture_output=True, text=True, timeout=5)
    assert ps.stdout.strip().splitlines()[-1] == '0'


def test_installer_uses_pwsh_runner_not_pythonw_and_offsets_watchdog() -> None:
    text = INSTALLER.read_text(encoding='utf-8')
    assert 'bootstrap_snapshot_task_runner.ps1' in text
    assert "$producerRuntime = Join-Path $runtimeRoot 'bootstrap_read_loop.py'" in text
    assert "$producerSource = Join-Path $PSScriptRoot 'bootstrap_read_loop.py'" in text
    assert 'Copy-Item -LiteralPath $producerSource -Destination $producerRuntime -Force' in text
    assert '-Mode Primary' in text
    assert '-Mode Watchdog' in text
    assert '-TimeoutSeconds 15' in text
    assert '-TimeoutSeconds 12 -StaleSeconds 55' in text
    assert '$baseStart.AddSeconds(10)' in text
    assert 'CreateNoWindow' not in text  # owned by the runner, not embedded in task arguments
    assert "Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'" in text  # migration recognition only
    assert 'New-ScheduledTaskAction -Execute $shellPath' in text
    assert 'Existing $TaskName task uses an unknown action; preserved without changes' in text
