[CmdletBinding()]
param(
    [string]$TaskName = 'VaultCheckoutSync',
    [int]$IntervalMinutes = 1,
    [string]$RepoRoot
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($IntervalMinutes -lt 1) { throw 'IntervalMinutes must be at least 1' }
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { $repo = Split-Path -Parent $PSScriptRoot } else { $repo = (Resolve-Path -LiteralPath $RepoRoot).Path }
$sync = Join-Path $repo 'tools\Sync-VaultCheckout.ps1'
if (-not (Test-Path -LiteralPath $sync)) { throw "Missing sync script: $sync" }
$powershell = (Get-Command powershell.exe -ErrorAction Stop).Source
$args = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -RepoRoot "{1}"' -f $sync, $repo
$action = New-ScheduledTaskAction -Execute $powershell -Argument $args -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName
[ordered]@{ ok=$true; task=$task.TaskName; state=[string]$task.State; interval_minutes=$IntervalMinutes; execute=$powershell; sync=$sync; repo_root=$repo; logon_type='Interactive'; run_level='Limited' } | ConvertTo-Json -Compress
