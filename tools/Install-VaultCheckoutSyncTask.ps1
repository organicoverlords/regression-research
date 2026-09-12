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
$pythonw = (Get-Command pythonw.exe -ErrorAction Stop).Source
$childCommand = @($powershell, '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', $sync, '-RepoRoot', $repo) | ConvertTo-Json -Compress
$payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($childCommand))
$pythonCode = "import base64,json,subprocess,sys; c=json.loads(base64.b64decode('$payload')); si=subprocess.STARTUPINFO(); si.dwFlags|=subprocess.STARTF_USESHOWWINDOW; si.wShowWindow=subprocess.SW_HIDE; r=subprocess.run(c, startupinfo=si, creationflags=subprocess.CREATE_NEW_CONSOLE); sys.exit(r.returncode)"
$args = '-c "{0}"' -f $pythonCode
$action = New-ScheduledTaskAction -Execute $pythonw -Argument $args -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
$task = Get-ScheduledTask -TaskName $TaskName
[ordered]@{ ok=$true; task=$task.TaskName; state=[string]$task.State; interval_minutes=$IntervalMinutes; execute=$pythonw; child_execute=$powershell; launcher='pythonw_hidden_inherited_console'; sync=$sync; repo_root=$repo; logon_type='Interactive'; run_level='Limited' } | ConvertTo-Json -Compress
