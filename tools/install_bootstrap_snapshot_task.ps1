param(
    [switch]$StartNow,
    [string]$RepoRoot
)
$ErrorActionPreference = 'Stop'
$primaryTaskName = 'VaultBootstrapSnapshot'
$watchdogTaskName = 'VaultBootstrapSnapshotWatchdog'
$sourceRepoRoot = Split-Path -Parent $PSScriptRoot
if ($RepoRoot) {
    $repoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
} else {
    $repoRoot = $sourceRepoRoot
}
$producerPath = Join-Path $repoRoot 'tools\bootstrap_read_loop.py'
if (-not (Test-Path -LiteralPath $producerPath)) { throw "Bootstrap producer missing: $producerPath" }
$guardSource = Join-Path $PSScriptRoot 'bootstrap_snapshot_guard.py'
if (-not (Test-Path -LiteralPath $guardSource)) { throw "Bootstrap guard missing: $guardSource" }
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'VaultBootstrapSnapshot'
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$guardRuntime = Join-Path $runtimeRoot 'bootstrap_snapshot_guard.py'
Copy-Item -LiteralPath $guardSource -Destination $guardRuntime -Force

$pythonPath = (& python.exe -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath)) { throw 'Python runtime unavailable' }
$windowless = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $windowless)) { throw 'Windowless Python runtime unavailable' }

$primaryArguments = '"{0}" --refresh --timeout-seconds 15 --repo-root "{1}"' -f $guardRuntime, $repoRoot
$watchdogArguments = '"{0}" --watchdog --stale-seconds 55 --timeout-seconds 15 --primary-task-name "{1}" --repo-root "{2}"' -f $guardRuntime, $primaryTaskName, $repoRoot
$legacyScript = Join-Path $repoRoot 'tools\bootstrap_read_loop.py'
$legacyArguments = '"{0}" --once --quiet --repo-root "{1}"' -f $legacyScript, $repoRoot

function Assert-KnownTaskAction([string]$TaskName, [string[]]$KnownArguments) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $existing) { return $null }
    if ($existing.Actions.Count -ne 1 -or $existing.Actions[0].Execute -ne $windowless -or $KnownArguments -notcontains $existing.Actions[0].Arguments) {
        throw "Existing $TaskName task uses an unknown action; preserved without changes"
    }
    return $existing
}

$existingPrimary = Assert-KnownTaskAction $primaryTaskName @($legacyArguments, $primaryArguments)
$existingWatchdog = Assert-KnownTaskAction $watchdogTaskName @($watchdogArguments)
if ($existingPrimary) { Unregister-ScheduledTask -TaskName $primaryTaskName -Confirm:$false }
if ($existingWatchdog) { Unregister-ScheduledTask -TaskName $watchdogTaskName -Confirm:$false }

$baseStart = (Get-Date).AddMinutes(1)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited

$primaryAction = New-ScheduledTaskAction -Execute $windowless -Argument $primaryArguments -WorkingDirectory $repoRoot
$primaryTrigger = New-ScheduledTaskTrigger -Once -At $baseStart -RepetitionInterval (New-TimeSpan -Minutes 1)
$primarySettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 25) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $primaryTaskName -Action $primaryAction -Trigger $primaryTrigger -Settings $primarySettings -Principal $principal -Description 'Publishes one hard-bounded bootstrap snapshot per minute.' | Out-Null

$watchdogAction = New-ScheduledTaskAction -Execute $windowless -Argument $watchdogArguments -WorkingDirectory $repoRoot
$watchdogTrigger = New-ScheduledTaskTrigger -Once -At $baseStart.AddSeconds(15) -RepetitionInterval (New-TimeSpan -Minutes 1)
$watchdogSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 25) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $watchdogTaskName -Action $watchdogAction -Trigger $watchdogTrigger -Settings $watchdogSettings -Principal $principal -Description 'Checks bootstrap freshness cheaply and repairs a stale or invalid snapshot before the 90-second MCP freshness contract.' | Out-Null

if ($StartNow) { Start-ScheduledTask -TaskName $primaryTaskName }
Get-ScheduledTask -TaskName $primaryTaskName, $watchdogTaskName | Select-Object TaskName, State
