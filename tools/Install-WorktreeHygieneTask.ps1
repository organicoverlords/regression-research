param(
    [string]$TaskName = 'VaultWorktreeHygiene',
    [int]$IntervalMinutes = 15
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($IntervalMinutes -lt 5) { throw 'IntervalMinutes must be at least 5' }
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'tools\worktree_hygiene_task.py'
if (-not (Test-Path -LiteralPath $script)) { throw "Missing hygiene task: $script" }
$pythonw = (Get-Command pythonw.exe -ErrorAction Stop).Source
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}"' -f $script) -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName
[ordered]@{
    ok = $true
    task = $task.TaskName
    state = [string]$task.State
    interval_minutes = $IntervalMinutes
    execute = $pythonw
    script = $script
    logon_type = 'Interactive'
    run_level = 'Limited'
} | ConvertTo-Json -Compress
