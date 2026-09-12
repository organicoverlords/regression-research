param(
    [string]$TaskName = 'VaultWorktreeHygiene',
    [int]$IntervalMinutes = 1
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($IntervalMinutes -lt 1) { throw 'IntervalMinutes must be at least 1' }

$repo = Split-Path -Parent $PSScriptRoot
$sourceCommit = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $sourceCommit) { throw 'Unable to resolve hygiene source commit' }
& git -C $repo merge-base --is-ancestor $sourceCommit origin/main
if ($LASTEXITCODE -ne 0) { throw "Hygiene runtime must be installed from a commit contained in cached origin/main: $sourceCommit" }

$runtimeFiles = @(
    'worktree_hygiene_task.py',
    'worktree_hygiene_guard.py',
    'cleanup_converger.py',
    'live_swarm.py'
)
foreach ($name in $runtimeFiles) {
    $source = Join-Path $PSScriptRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing hygiene runtime source: $source" }
    $relative = 'tools/' + $name
    $dirty = & git -C $repo status --porcelain=v1 -- $relative
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw "Hygiene runtime source differs from committed snapshot: $relative" }
}

$pythonPath = (& python.exe -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Python runtime unavailable' }
$pythonw = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) { throw "Windowless Python runtime unavailable: $pythonw" }

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'VaultWorktreeHygiene\runtime'
$runtime = Join-Path $runtimeRoot $sourceCommit
$script = Join-Path $runtime 'worktree_hygiene_task.py'
$argument = ('"{0}"' -f $script)

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$wasEnabled = $true
if ($existing) {
    $wasEnabled = [bool]$existing.Settings.Enabled
    $actions = @($existing.Actions)
    $legacyMutableRoot = 'C:\Users\Lauri\Desktop\vault'
    $knownMutable = Join-Path $legacyMutableRoot 'tools\worktree_hygiene_task.py'
    $knownMutableArgument = ('"{0}"' -f $knownMutable)
    $existingArgument = if ($actions.Count -eq 1) { [string]$actions[0].Arguments } else { '' }
    $runtimePrefix = '"' + $runtimeRoot + '\'
    $knownRuntime = $actions.Count -eq 1 -and [string]$actions[0].Execute -eq $pythonw -and $existingArgument.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase) -and $existingArgument.EndsWith('\worktree_hygiene_task.py"', [StringComparison]::OrdinalIgnoreCase)
    $knownMutableAction = $actions.Count -eq 1 -and [string]$actions[0].Execute -eq $pythonw -and $existingArgument -eq $knownMutableArgument
    if (-not ($knownRuntime -or $knownMutableAction)) { throw "Existing $TaskName task uses an unknown action; preserved without changes" }
}

New-Item -ItemType Directory -Force -Path $runtime | Out-Null
foreach ($name in $runtimeFiles) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $runtime $name) -Force
}
$manifest = [ordered]@{
    schema = 'vault-worktree-hygiene-runtime.v1'
    source_commit = $sourceCommit
    installed_at = [DateTimeOffset]::UtcNow.ToString('o')
    source_repo = $repo
    files = $runtimeFiles
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $runtime 'manifest.json') -Encoding UTF8

$action = New-ScheduledTaskAction -Execute $pythonw -Argument $argument -WorkingDirectory $runtime
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
if (-not $wasEnabled) { Disable-ScheduledTask -TaskName $TaskName | Out-Null }
$task = Get-ScheduledTask -TaskName $TaskName
[ordered]@{
    ok = $true
    task = $task.TaskName
    state = [string]$task.State
    enabled = [bool]$task.Settings.Enabled
    interval_minutes = $IntervalMinutes
    execute = $pythonw
    script = $script
    runtime_root = $runtime
    source_commit = $sourceCommit
    preserved_enabled_state = $wasEnabled
    logon_type = 'Interactive'
    run_level = 'Limited'
} | ConvertTo-Json -Compress
