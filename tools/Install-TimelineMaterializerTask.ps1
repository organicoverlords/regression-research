param(
    [string]$TaskName = 'Vault Timeline Materializer',
    [int]$IntervalMinutes = 5,
    [string]$VaultRoot = 'C:\Users\Lauri\Desktop\vault'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($IntervalMinutes -lt 1) { throw 'IntervalMinutes must be at least 1' }

$repo = Split-Path -Parent $PSScriptRoot
$sourceCommit = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0 -or -not $sourceCommit) { throw 'Unable to resolve timeline source commit' }
& git -C $repo merge-base --is-ancestor $sourceCommit origin/main
if ($LASTEXITCODE -ne 0) { throw "Timeline runtime must be installed from a commit contained in cached origin/main: $sourceCommit" }

$pythonPath = (& python.exe -c 'import sys; print(sys.executable)').Trim()
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Python runtime unavailable' }
$pythonw = Join-Path (Split-Path -Parent $pythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) { throw "Windowless Python runtime unavailable: $pythonw" }

$runtimeRoot = Join-Path $env:LOCALAPPDATA 'VaultTimeline\runtime'
$runtime = Join-Path $runtimeRoot $sourceCommit
$runtimeScript = Join-Path $runtime 'tools\timeline_materializer.py'
$manifestPath = Join-Path $runtime 'manifest.json'

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$wasEnabled = $true
if ($existing) {
    $wasEnabled = [bool]$existing.Settings.Enabled
    if ([string]$existing.State -eq 'Running') { throw "Existing $TaskName task is running; retry after it returns Ready" }
    $actions = @($existing.Actions)
    if ($actions.Count -ne 1) { throw "Existing $TaskName task has unexpected action count; preserved without changes" }
    $existingArgument = [string]$actions[0].Arguments
    $legacyServing = 'C:\Users\Lauri\AppData\Local\VaultTimelineServing\tools\timeline_materializer.py'
    $legacyMutable = Join-Path $VaultRoot 'tools\timeline_materializer.py'
    $knownLegacyServing = $existingArgument.IndexOf($legacyServing, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $knownMutable = $existingArgument.IndexOf($legacyMutable, [StringComparison]::OrdinalIgnoreCase) -ge 0
    $knownRuntime = $existingArgument.IndexOf($runtimeRoot + '\', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $existingArgument.IndexOf('\tools\timeline_materializer.py', [StringComparison]::OrdinalIgnoreCase) -ge 0
    if (-not ($knownLegacyServing -or $knownMutable -or $knownRuntime)) { throw "Existing $TaskName task uses an unknown action; preserved without changes" }
}

if (Test-Path -LiteralPath $runtime) {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or -not (Test-Path -LiteralPath $runtimeScript -PathType Leaf)) {
        throw "Timeline runtime path already exists but is incomplete: $runtime"
    }
    $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    if ([string]$manifest.source_commit -ne $sourceCommit) { throw "Timeline runtime manifest does not match path commit: $runtime" }
} else {
    New-Item -ItemType Directory -Force -Path $runtime | Out-Null
    $archive = Join-Path $env:TEMP ("vault-timeline-{0}-{1}.zip" -f $sourceCommit, [Guid]::NewGuid().ToString('N'))
    try {
        & git -C $repo archive --format=zip --output=$archive $sourceCommit tools
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw 'Failed to create timeline runtime archive' }
        Expand-Archive -LiteralPath $archive -DestinationPath $runtime -Force
    } finally {
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath $runtimeScript -PathType Leaf)) { throw "Timeline runtime archive is missing materializer: $runtimeScript" }
    $manifest = [ordered]@{
        schema = 'vault-timeline-runtime.v1'
        source_commit = $sourceCommit
        installed_at = [DateTimeOffset]::UtcNow.ToString('o')
        source_repo = $repo
        vault_root = $VaultRoot
        archive_scope = 'tools/'
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
}

$installOutput = & $pythonPath $runtimeScript install-task --minutes $IntervalMinutes --root $VaultRoot
if ($LASTEXITCODE -ne 0) { throw "Timeline runtime task install failed: $installOutput" }
if (-not $wasEnabled) { Disable-ScheduledTask -TaskName $TaskName | Out-Null }
$task = Get-ScheduledTask -TaskName $TaskName
$action = @($task.Actions)[0]
[ordered]@{
    ok = $true
    task = $task.TaskName
    state = [string]$task.State
    enabled = [bool]$task.Settings.Enabled
    interval_minutes = $IntervalMinutes
    runtime_root = $runtime
    source_commit = $sourceCommit
    script = $runtimeScript
    execute = [string]$action.Execute
    arguments = [string]$action.Arguments
    preserved_enabled_state = $wasEnabled
    legacy_serving_preserved = 'C:\Users\Lauri\AppData\Local\VaultTimelineServing'
} | ConvertTo-Json -Compress
