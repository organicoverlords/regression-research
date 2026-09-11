from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / 'tools' / 'install_bootstrap_snapshot_task.ps1'
RUNNER = REPO_ROOT / 'tools' / 'bootstrap_snapshot_task_runner.ps1'


def test_installer_uses_direct_windowless_producer_actions() -> None:
    text = INSTALLER.read_text(encoding='utf-8')
    assert "$producerSource = Join-Path $PSScriptRoot 'bootstrap_read_loop.py'" in text
    assert "$helperSource = Join-Path $PSScriptRoot 'memory_recent_projection.py'" in text
    assert "$atlasSource = Join-Path $PSScriptRoot 'stack_atlas.py'" in text
    assert 'Copy-Item -LiteralPath $producerSource -Destination $producerRuntime -Force' in text
    assert 'Copy-Item -LiteralPath $helperSource -Destination $helperRuntime -Force' in text
    assert 'Copy-Item -LiteralPath $atlasSource -Destination $atlasRuntime -Force' in text
    assert "' --atlas-path '" in text
    assert '$directPrimaryArguments' in text
    assert '$directWatchdogArguments' in text
    assert "$pythonwPath = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'" in text
    assert text.count('New-ScheduledTaskAction -Execute $pythonwPath') == 2
    assert "' --skip-if-fresh-seconds 45'" in text
    assert '$baseStart.AddSeconds(35)' in text
    assert '-ExecutionTimeLimit (New-TimeSpan -Seconds 45)' in text
    assert 'Existing $TaskName task uses an unknown action; preserved without changes' in text


def test_installer_recognizes_v2_for_safe_migration_but_does_not_run_it() -> None:
    text = INSTALLER.read_text(encoding='utf-8')
    assert "$v2RunnerRuntime = Join-Path $runtimeRoot 'bootstrap_snapshot_task_runner.ps1'" in text
    assert '$v2PrimaryArguments' in text
    assert '$v2WatchdogArguments' in text
    assert 'New-ScheduledTaskAction -Execute $shellPath' not in text


def test_retired_pwsh_runner_is_removed_from_source_tree() -> None:
    assert not RUNNER.exists()
