param(
    [Parameter(Mandatory=$true)][ValidateSet('Primary','Watchdog')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [string]$ProducerPath,
    [int]$TimeoutSeconds = 15,
    [int]$StaleSeconds = 55
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath $RepoRoot).Path
$producer = $(if ($ProducerPath) { (Resolve-Path -LiteralPath $ProducerPath).Path } else { Join-Path (Split-Path -Parent $PSCommandPath) 'bootstrap_read_loop.py' })
$snapshot = Join-Path $repo '.state\bootstrap\latest.json'
$statePath = Join-Path $repo '.state\bootstrap\guard-state.json'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python runtime missing: $PythonPath" }
if (-not (Test-Path -LiteralPath $producer -PathType Leaf)) { throw "Bootstrap producer missing: $producer" }

function Get-SnapshotState {
    $result = [ordered]@{ status = 'MISSING'; age_seconds = $null; generated_at = $null }
    if (-not (Test-Path -LiteralPath $snapshot -PathType Leaf)) { return $result }
    try {
        $payload = Get-Content -LiteralPath $snapshot -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        $result.status = 'UNREADABLE'
        return $result
    }
    if ($payload.schema -ne 'bootstrap.v1' -or $payload.bootstrap_end.status -ne 'COMPLETE' -or $payload.bootstrap_end.schema -ne 'bootstrap.v1') {
        $result.status = 'INVALID'
        return $result
    }
    try {
        $generated = [DateTimeOffset]::Parse([string]$payload.generated_at, [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::RoundtripKind)
    } catch {
        $result.status = 'INVALID_GENERATED_AT'
        return $result
    }
    $age = ([DateTimeOffset]::UtcNow - $generated.ToUniversalTime()).TotalSeconds
    if ($age -lt -5) {
        $result.status = 'FUTURE_GENERATED_AT'
        return $result
    }
    $result.status = 'OK'
    $result.age_seconds = [Math]::Max(0.0, $age)
    $result.generated_at = $generated.ToString('o')
    return $result
}

function Write-GuardState([hashtable]$State) {
    $dir = Split-Path -Parent $statePath
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $temp = Join-Path $dir ('.guard-state-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        ($State | ConvertTo-Json -Depth 8 -Compress) | Set-Content -LiteralPath $temp -Encoding UTF8
        $deadline = [DateTimeOffset]::UtcNow.AddMilliseconds(750)
        do {
            try {
                Move-Item -LiteralPath $temp -Destination $statePath -Force
                return
            } catch [System.IO.IOException] {
                if ([DateTimeOffset]::UtcNow -ge $deadline) { throw }
                Start-Sleep -Milliseconds 25
            } catch [System.UnauthorizedAccessException] {
                if ([DateTimeOffset]::UtcNow -ge $deadline) { throw }
                Start-Sleep -Milliseconds 25
            }
        } while ($true)
    } finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-BoundedRefresh {
    $start = [DateTimeOffset]::UtcNow
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $PythonPath
    $psi.WorkingDirectory = $repo
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $pathSeparator = [System.IO.Path]::PathSeparator
    $existingPythonPath = $psi.Environment['PYTHONPATH']
    $psi.Environment['PYTHONPATH'] = $(if ($existingPythonPath) { $repo + $pathSeparator + $existingPythonPath } else { $repo })
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    [void]$psi.ArgumentList.Add($producer)
    [void]$psi.ArgumentList.Add('--once')
    [void]$psi.ArgumentList.Add('--quiet')
    [void]$psi.ArgumentList.Add('--repo-root')
    [void]$psi.ArgumentList.Add($repo)
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $psi
    if (-not $process.Start()) {
        return [ordered]@{ ok = $false; action = 'REFRESH_START_FAILED'; started_at = $start.ToString('o') }
    }
    $childProcessId = $process.Id
    $finished = $process.WaitForExit([Math]::Max(1, $TimeoutSeconds) * 1000)
    if (-not $finished) {
        try { $process.Kill($true) } catch {}
        try { [void]$process.WaitForExit(2000) } catch {}
        return [ordered]@{ ok = $false; action = 'REFRESH_TIMEOUT'; pid = $childProcessId; timeout_seconds = $TimeoutSeconds; started_at = $start.ToString('o') }
    }
    $code = $process.ExitCode
    return [ordered]@{ ok = ($code -eq 0); action = $(if ($code -eq 0) { 'REFRESH_OK' } else { 'REFRESH_FAILED' }); pid = $childProcessId; exit_code = $code; started_at = $start.ToString('o') }
}

$before = Get-SnapshotState
$state = [ordered]@{
    schema = 'bootstrap-snapshot-guard.v2'
    mode = $Mode.ToUpperInvariant()
    checked_at = [DateTimeOffset]::UtcNow.ToString('o')
    threshold_seconds = $(if ($Mode -eq 'Watchdog') { $StaleSeconds } else { $null })
    snapshot_before = $before
}

if ($Mode -eq 'Watchdog' -and $before.status -eq 'OK' -and [double]$before.age_seconds -le $StaleSeconds) {
    $state.ok = $true
    $state.action = 'NOOP_FRESH'
    Write-GuardState $state
    exit 0
}

$refresh = Invoke-BoundedRefresh
$after = Get-SnapshotState
$state.refresh = $refresh
$state.snapshot_after = $after
$state.ok = [bool]$refresh.ok -and $after.status -eq 'OK'
$state.action = $(if ($state.ok) { $(if ($Mode -eq 'Watchdog') { 'RECOVERED' } else { 'REFRESH_OK' }) } else { $(if ($Mode -eq 'Watchdog') { 'RECOVERY_FAILED' } else { [string]$refresh.action }) })
Write-GuardState $state
if ($state.ok) { exit 0 }
exit 1



