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

$runtimeFiles = @('worktree_hygiene_task.py','worktree_hygiene_guard.py','cleanup_converger.py','live_swarm.py')
foreach ($name in $runtimeFiles) {
    $source = Join-Path $PSScriptRoot $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing hygiene runtime source: $source" }
    $relative = 'tools/' + $name
    $dirty = & git -C $repo status --porcelain=v1 -- $relative
    if ($LASTEXITCODE -ne 0 -or $dirty) { throw "Hygiene runtime source differs from committed snapshot: $relative" }
}

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'VaultWorktreeHygiene\runtime'
$runtime = Join-Path $runtimeRoot $sourceCommit
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

$script = Join-Path $runtime 'worktree_hygiene_task.py'
$pythonPath = (& python.exe -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Python runtime unavailable' }
$pythonw = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) { throw "Windowless Python runtime unavailable: $pythonw" }
$argument = ('"{0}"' -f $script)

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    $knownMutable = Join-Path $repo 'tools\worktree_hygiene_task.py'
    $knownMutableArgument = ('"{0}"' -f $knownMutable)
    $existingArgument = [string]$existing.Actions[0].Arguments
    $knownRuntime = $existing.Actions.Count -eq 1 -and $existing.Actions[0].Execute -eq $pythonw -and $existingArgument.StartsWith(('"{0}\' -f $runtimeRoot), [StringComparison]::OrdinalIgnoreCase) -and $existingArgument.EndsWith('\worktree_hygiene_task.py"', [StringComparison]::OrdinalIgnoreCase)
    $knownMutableAction = $existing.Actions.Count -eq 1 -and $existing.Actions[0].Execute -eq $pythonw -and $existingArgument -eq $knownMutableArgument
    if (-not ($knownRuntime -or $knownMutableAction)) { throw "Existing $TaskName task uses an unknown action; preserved without changes" }
}

$action = New-ScheduledTaskAction -Execute $pythonw -Argument $argument -WorkingDirectory $runtime
$trigger = New-ScheduledTaskTrigger -Once -At ((Get-Date).AddMinutes(1)) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 50) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
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
    runtime_root = $runtime
    source_commit = $sourceCommit
    restart_count = [int]$task.Settings.RestartCount
    logon_type = 'Interactive'
    run_level = 'Limited'
} | ConvertTo-Json -Compress
