param([switch]$StartNow)
$ErrorActionPreference = 'Stop'
$taskName = 'VaultBootstrapSnapshot'
$repoRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $PSScriptRoot 'bootstrap_read_loop.py'
$pythonPath = (& python.exe -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath)) { throw 'Python runtime unavailable' }
$windowless = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $windowless)) { throw 'Windowless Python runtime unavailable' }
$arguments = '"{0}" --once --quiet --repo-root "{1}"' -f $scriptPath, $repoRoot
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    if ($existing.Actions.Count -ne 1 -or $existing.Actions[0].Execute -ne $windowless -or $existing.Actions[0].Arguments -ne $arguments) {
        throw 'Existing bootstrap task uses a different action; preserved without changes'
    }
} else {
    $action = New-ScheduledTaskAction -Execute $windowless -Argument $arguments -WorkingDirectory $repoRoot
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 45) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Publishes one bounded bootstrap snapshot per minute; MCP readers only read the materialized file.' | Out-Null
}
if ($StartNow) { Start-ScheduledTask -TaskName $taskName }
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
