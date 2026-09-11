param(
    [switch]$StartNow,
    [string]$RepoRoot
)
$ErrorActionPreference = 'Stop'
$primaryTaskName = 'VaultBootstrapSnapshot'
$watchdogTaskName = 'VaultBootstrapSnapshotWatchdog'
$sourceRepoRoot = Split-Path -Parent $PSScriptRoot
if ($RepoRoot) { $repoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path } else { $repoRoot = $sourceRepoRoot }
$producerSource = Join-Path $PSScriptRoot 'bootstrap_read_loop.py'
if (-not (Test-Path -LiteralPath $producerSource)) { throw "Bootstrap producer source missing: $producerSource" }
$runnerSource = Join-Path $PSScriptRoot 'bootstrap_snapshot_task_runner.ps1'
if (-not (Test-Path -LiteralPath $runnerSource)) { throw "Bootstrap task runner missing: $runnerSource" }
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'VaultBootstrapSnapshot'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$runnerRuntime = Join-Path $runtimeRoot 'bootstrap_snapshot_task_runner.ps1'
$producerRuntime = Join-Path $runtimeRoot 'bootstrap_read_loop.py'
Copy-Item -LiteralPath $runnerSource -Destination $runnerRuntime -Force
Copy-Item -LiteralPath $producerSource -Destination $producerRuntime -Force

$pythonPath = (& python.exe -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath)) { throw 'Python runtime unavailable' }
$pwshCommand = Get-Command pwsh.exe -ErrorAction SilentlyContinue
if ($pwshCommand) { $shellPath = $pwshCommand.Source } else { $shellPath = (Get-Command powershell.exe -ErrorAction Stop).Source }

function Q([string]$Value) { return '"' + $Value.Replace('"','\"') + '"' }
$common = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File ' + (Q $runnerRuntime)
$primaryArguments = $common + ' -Mode Primary -RepoRoot ' + (Q $repoRoot) + ' -PythonPath ' + (Q $pythonPath) + ' -TimeoutSeconds 15'
$watchdogArguments = $common + ' -Mode Watchdog -RepoRoot ' + (Q $repoRoot) + ' -PythonPath ' + (Q $pythonPath) + ' -TimeoutSeconds 12 -StaleSeconds 55'

$legacyPythonw = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
$legacyScript = Join-Path $repoRoot 'tools\bootstrap_read_loop.py'
$legacyArguments = '"{0}" --once --quiet --repo-root "{1}"' -f $legacyScript, $repoRoot
$v1Guard = Join-Path $runtimeRoot 'bootstrap_snapshot_guard.py'
$v1PrimaryArguments = '"{0}" --refresh --timeout-seconds 15 --repo-root "{1}"' -f $v1Guard, $repoRoot
$v1WatchdogArguments = '"{0}" --watchdog --stale-seconds 55 --timeout-seconds 15 --primary-task-name "{1}" --repo-root "{2}"' -f $v1Guard, $primaryTaskName, $repoRoot

function Assert-KnownTaskAction([string]$TaskName, [string[]]$KnownExecutables, [string[]]$KnownArguments) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) { return $null }
    if ($existing.Actions.Count -ne 1 -or $KnownExecutables -notcontains $existing.Actions[0].Execute -or $KnownArguments -notcontains $existing.Actions[0].Arguments) {
        throw "Existing $TaskName task uses an unknown action; preserved without changes"
    }
    return $existing
}

$knownExecutables = @($legacyPythonw, $shellPath)
$existingPrimary = Assert-KnownTaskAction $primaryTaskName $knownExecutables @($legacyArguments, $v1PrimaryArguments, $primaryArguments)
$existingWatchdog = Assert-KnownTaskAction $watchdogTaskName $knownExecutables @($v1WatchdogArguments, $watchdogArguments)
if ($existingPrimary) { Unregister-ScheduledTask -TaskName $primaryTaskName -Confirm:$false }
if ($existingWatchdog) { Unregister-ScheduledTask -TaskName $watchdogTaskName -Confirm:$false }

$baseStart = (Get-Date).AddMinutes(1)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 22) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$primaryAction = New-ScheduledTaskAction -Execute $shellPath -Argument $primaryArguments -WorkingDirectory $repoRoot
$primaryTrigger = New-ScheduledTaskTrigger -Once -At $baseStart -RepetitionInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $primaryTaskName -Action $primaryAction -Trigger $primaryTrigger -Settings $settings -Principal $principal -Description 'Publishes one bounded bootstrap snapshot per minute through a no-window PowerShell/.NET process runner.' | Out-Null

$watchdogAction = New-ScheduledTaskAction -Execute $shellPath -Argument $watchdogArguments -WorkingDirectory $repoRoot
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At $baseStart.AddSeconds(10) -RepetitionInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $watchdogTaskName -Action $watchdogAction -Trigger $watchdogTrigger -Settings $settings -Principal $principal -Description 'Checks bootstrap freshness independently and performs a bounded recovery refresh before the 90-second MCP freshness contract.' | Out-Null

if ($StartNow) { Start-ScheduledTask -TaskName $primaryTaskName }
Get-ScheduledTask -TaskName $primaryTaskName, $watchdogTaskName | Select-Object TaskName, State
