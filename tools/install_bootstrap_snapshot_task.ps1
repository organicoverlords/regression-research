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
$helperSource = Join-Path $PSScriptRoot 'memory_recent_projection.py'
if (-not (Test-Path -LiteralPath $producerSource -PathType Leaf)) { throw "Bootstrap producer source missing: $producerSource" }
if (-not (Test-Path -LiteralPath $helperSource -PathType Leaf)) { throw "Bootstrap helper source missing: $helperSource" }

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'VaultBootstrapSnapshot'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$producerRuntime = Join-Path $runtimeRoot 'bootstrap_read_loop.py'
$helperRuntime = Join-Path $runtimeRoot 'memory_recent_projection.py'
Copy-Item -LiteralPath $producerSource -Destination $producerRuntime -Force
Copy-Item -LiteralPath $helperSource -Destination $helperRuntime -Force

$pythonPath = (& python.exe -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Python runtime unavailable' }
$pythonwPath = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonwPath -PathType Leaf)) { throw "Windowless Python runtime unavailable: $pythonwPath" }
$pwshCommand = Get-Command pwsh.exe -ErrorAction SilentlyContinue
if ($pwshCommand) { $shellPath = $pwshCommand.Source } else { $shellPath = (Get-Command powershell.exe -ErrorAction Stop).Source }

function Q([string]$Value) { return '"' + $Value.Replace('"','\"') + '"' }
$primaryArguments = (Q $producerRuntime) + ' --once --quiet --repo-root ' + (Q $repoRoot)
$watchdogArguments = $primaryArguments + ' --skip-if-fresh-seconds 45'

# Recognize every task action shipped by the prior generations so migration stays fail-closed.
$legacyScript = Join-Path $repoRoot 'tools\bootstrap_read_loop.py'
$legacyArguments = (Q $legacyScript) + ' --once --quiet --repo-root ' + (Q $repoRoot)
$v1Guard = Join-Path $runtimeRoot 'bootstrap_snapshot_guard.py'
$v1PrimaryArguments = (Q $v1Guard) + ' --refresh --timeout-seconds 15 --repo-root ' + (Q $repoRoot)
$v1WatchdogArguments = (Q $v1Guard) + ' --watchdog --stale-seconds 55 --timeout-seconds 15 --primary-task-name ' + (Q $primaryTaskName) + ' --repo-root ' + (Q $repoRoot)
$v2RunnerRuntime = Join-Path $runtimeRoot 'bootstrap_snapshot_task_runner.ps1'
$v2Common = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File ' + (Q $v2RunnerRuntime)
$v2PrimaryArguments = $v2Common + ' -Mode Primary -RepoRoot ' + (Q $repoRoot) + ' -PythonPath ' + (Q $pythonPath) + ' -TimeoutSeconds 15'
$v2WatchdogArguments = $v2Common + ' -Mode Watchdog -RepoRoot ' + (Q $repoRoot) + ' -PythonPath ' + (Q $pythonPath) + ' -TimeoutSeconds 12 -StaleSeconds 55'

function Assert-KnownTaskAction([string]$TaskName, [string[]]$KnownExecutables, [string[]]$KnownArguments) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) { return $null }
    if ($existing.Actions.Count -ne 1 -or $KnownExecutables -notcontains $existing.Actions[0].Execute -or $KnownArguments -notcontains $existing.Actions[0].Arguments) {
        throw "Existing $TaskName task uses an unknown action; preserved without changes"
    }
    return $existing
}

$knownExecutables = @($pythonwPath, $shellPath)
$existingPrimary = Assert-KnownTaskAction $primaryTaskName $knownExecutables @($legacyArguments, $v1PrimaryArguments, $v2PrimaryArguments, $primaryArguments)
$existingWatchdog = Assert-KnownTaskAction $watchdogTaskName $knownExecutables @($v1WatchdogArguments, $v2WatchdogArguments, $watchdogArguments)
if ($existingPrimary) { Unregister-ScheduledTask -TaskName $primaryTaskName -Confirm:$false }
if ($existingWatchdog) { Unregister-ScheduledTask -TaskName $watchdogTaskName -Confirm:$false }

$baseStart = (Get-Date).AddMinutes(1)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 20) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$primaryAction = New-ScheduledTaskAction -Execute $pythonwPath -Argument $primaryArguments -WorkingDirectory $repoRoot
$primaryTrigger = New-ScheduledTaskTrigger -Once -At $baseStart -RepetitionInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $primaryTaskName -Action $primaryAction -Trigger $primaryTrigger -Settings $settings -Principal $principal -Description 'Publishes one bounded bootstrap snapshot per minute directly through the runtime producer.' | Out-Null

$watchdogAction = New-ScheduledTaskAction -Execute $pythonwPath -Argument $watchdogArguments -WorkingDirectory $repoRoot
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At $baseStart.AddSeconds(20) -RepetitionInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $watchdogTaskName -Action $watchdogAction -Trigger $watchdogTrigger -Settings $settings -Principal $principal -Description 'Runs the same bounded producer independently and skips work while a COMPLETE bootstrap snapshot is 45 seconds old or newer.' | Out-Null

# guard-state.json belonged to the retired PowerShell wrapper and must not masquerade as live authority.
Remove-Item -LiteralPath (Join-Path $repoRoot '.state\bootstrap\guard-state.json') -Force -ErrorAction SilentlyContinue
if ($StartNow) { Start-ScheduledTask -TaskName $primaryTaskName }
Get-ScheduledTask -TaskName $primaryTaskName, $watchdogTaskName | Select-Object TaskName, State
