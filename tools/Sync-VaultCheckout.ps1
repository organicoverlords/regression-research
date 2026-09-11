[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$Remote = 'origin',
    [string]$Branch = 'main',
    [switch]$Repair,
    [switch]$SkipFetch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { $RepoRoot = Split-Path -Parent $PSScriptRoot }

function Invoke-GitText {
    param(
        [Parameter(Mandatory=$true)][string[]]$GitArgs,
        [switch]$AllowFailure
    )
    $errFile = Join-Path ([IO.Path]::GetTempPath()) ("vault-sync-giterr-" + [Guid]::NewGuid().ToString('N'))
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& git -C $RepoRoot @GitArgs 2> $errFile)
        $code = $LASTEXITCODE
        $stderr = if (Test-Path -LiteralPath $errFile) { [IO.File]::ReadAllText($errFile).Trim() } else { '' }
    }
    finally {
        $ErrorActionPreference = $savedPreference
        Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
    }
    $text = (($output | ForEach-Object { [string]$_ }) -join "`n").Trim()
    if ($code -ne 0 -and -not $AllowFailure) {
        $detail = @($text,$stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        throw "git $($GitArgs -join ' ') failed ($code): $($detail -join ' | ')"
    }
    [pscustomobject]@{ Code = $code; Text = $text; ErrorText = $stderr }
}
function Git-Text {
    param([Parameter(Mandatory=$true)][string[]]$GitArgs)
    (Invoke-GitText -GitArgs $GitArgs).Text
}

function Write-ResultAndExit {
    param(
        [Parameter(Mandatory=$true)][hashtable]$Result,
        [Parameter(Mandatory=$true)][int]$Code
    )
    $Result | ConvertTo-Json -Compress -Depth 6
    exit $Code
}

try {
    $RepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
    $inside = Git-Text @('rev-parse','--is-inside-work-tree')
    if ($inside -ne 'true') { throw "$RepoRoot is not a Git worktree" }

    $branchName = Git-Text @('rev-parse','--abbrev-ref','HEAD')
    $headBefore = Git-Text @('rev-parse','HEAD')
    $statusBefore = Git-Text @('status','--porcelain=v1','--untracked-files=normal')
    $dirtyBefore = -not [string]::IsNullOrWhiteSpace($statusBefore)

    $wrongBranchBefore = $null
    $wrongBranchHeadBefore = $null
    $wrongBranchRepaired = $false
    if ($branchName -ne $Branch) {
        if (-not $Repair) {
            Write-ResultAndExit -Result ([ordered]@{
                ok = $false; status = 'WRONG_BRANCH'; branch = $branchName; expected_branch = $Branch
                head = $headBefore; dirty = $dirtyBefore; action = 'none'; repair = 'rerun with -Repair after attribution/authorization'
            }) -Code 4
        }
        if ($dirtyBefore) {
            Write-ResultAndExit -Result ([ordered]@{
                ok = $false; status = 'WRONG_BRANCH_DIRTY_BLOCKED'; branch = $branchName; expected_branch = $Branch
                head = $headBefore; dirty = $true; action = 'none'; repair = 'preserve/finish dirty branch work before serving-checkout switch'
            }) -Code 4
        }
        $expectedLocal = Invoke-GitText -GitArgs @('rev-parse','--verify',"refs/heads/$Branch") -AllowFailure
        if ($expectedLocal.Code -ne 0) {
            Write-ResultAndExit -Result ([ordered]@{
                ok = $false; status = 'EXPECTED_BRANCH_MISSING'; branch = $branchName; expected_branch = $Branch
                head = $headBefore; dirty = $false; action = 'none'
            }) -Code 4
        }
        $wrongBranchBefore = $branchName
        $wrongBranchHeadBefore = $headBefore
        [void](Git-Text @('switch',$Branch))
        $branchName = Git-Text @('rev-parse','--abbrev-ref','HEAD')
        $headBefore = Git-Text @('rev-parse','HEAD')
        $statusBefore = Git-Text @('status','--porcelain=v1','--untracked-files=normal')
        $dirtyBefore = -not [string]::IsNullOrWhiteSpace($statusBefore)
        if ($branchName -ne $Branch -or $dirtyBefore) {
            throw "wrong-branch repair failed to establish clean $Branch; branch=$branchName dirty=$dirtyBefore"
        }
        $wrongBranchRepaired = $true
    }

    if (-not $SkipFetch) {
        [void](Git-Text @('fetch','--prune',$Remote,$Branch))
    }

    $remoteRef = "$Remote/$Branch"
    $remoteHead = Git-Text @('rev-parse',$remoteRef)
    $counts = (Git-Text @('rev-list','--left-right','--count',"HEAD...$remoteRef")) -split '\s+'
    if ($counts.Count -lt 2) { throw 'unable to parse ahead/behind counts' }
    $ahead = [int]$counts[0]
    $behind = [int]$counts[1]

    if (-not $dirtyBefore -and $ahead -eq 0 -and $behind -eq 0) {
        $status = if ($wrongBranchRepaired) { 'WRONG_BRANCH_REPAIRED' } else { 'CURRENT' }
        $action = if ($wrongBranchRepaired) { 'switch-to-expected-branch' } else { 'none' }
        Write-ResultAndExit -Result ([ordered]@{
            ok = $true; status = $status; branch = $branchName; head = $headBefore
            remote_head = $remoteHead; ahead = 0; behind = 0; dirty = $false; action = $action
            wrong_branch_before = $wrongBranchBefore; wrong_branch_head_before = $wrongBranchHeadBefore
        }) -Code 0
    }

    if (-not $dirtyBefore -and $ahead -eq 0 -and $behind -gt 0) {
        [void](Git-Text @('merge','--ff-only',$remoteRef))
        $headAfter = Git-Text @('rev-parse','HEAD')
        $dirtyAfter = -not [string]::IsNullOrWhiteSpace((Git-Text @('status','--porcelain=v1','--untracked-files=normal')))
        if ($headAfter -ne $remoteHead -or $dirtyAfter) { throw 'clean fast-forward did not converge exactly' }
        $status = if ($wrongBranchRepaired) { 'WRONG_BRANCH_REPAIRED_FAST_FORWARDED' } else { 'FAST_FORWARDED' }
        $action = if ($wrongBranchRepaired) { 'switch-to-expected-branch+ff-only' } else { 'ff-only' }
        Write-ResultAndExit -Result ([ordered]@{
            ok = $true; status = $status; branch = $branchName; head_before = $headBefore
            head = $headAfter; remote_head = $remoteHead; ahead_before = $ahead; behind_before = $behind
            dirty = $false; action = $action; wrong_branch_before = $wrongBranchBefore
            wrong_branch_head_before = $wrongBranchHeadBefore
        }) -Code 0
    }

    if (-not $Repair) {
        $state = if ($dirtyBefore) { 'DIRTY_BLOCKED' } elseif ($ahead -gt 0 -and $behind -gt 0) { 'DIVERGED_BLOCKED' } else { 'AHEAD_BLOCKED' }
        Write-ResultAndExit -Result ([ordered]@{
            ok = $false; status = $state; branch = $branchName; head = $headBefore; remote_head = $remoteHead
            ahead = $ahead; behind = $behind; dirty = $dirtyBefore; action = 'none'; repair = 'rerun with -Repair after attribution/authorization'
        }) -Code 5
    }

    $unmerged = Git-Text @('diff','--name-only','--diff-filter=U')
    if (-not [string]::IsNullOrWhiteSpace($unmerged)) {
        Write-ResultAndExit -Result ([ordered]@{
            ok = $false; status = 'UNMERGED_BLOCKED'; branch = $branchName; head = $headBefore; remote_head = $remoteHead
            ahead = $ahead; behind = $behind; dirty = $dirtyBefore; unmerged = @($unmerged -split "`n"); action = 'none'
        }) -Code 6
    }

    $initialUntracked = @()
    $untrackedText = Git-Text @('ls-files','--others','--exclude-standard')
    if (-not [string]::IsNullOrWhiteSpace($untrackedText)) { $initialUntracked = @($untrackedText -split "`n") }

    $headTree = Git-Text @('rev-parse','HEAD^{tree}')
    $indexTree = Git-Text @('write-tree')
    $preserveParent = $headBefore
    $indexCommit = $null
    if ($indexTree -ne $headTree) {
        $indexCommit = Git-Text @('commit-tree',$indexTree,'-p',$headBefore,'-m','Preserve live Vault index before canonical convergence')
        $preserveParent = $indexCommit
    }

    $tempIndex = Join-Path ([IO.Path]::GetTempPath()) ("agents-sync-index-" + [Guid]::NewGuid().ToString('N'))
    $oldIndex = $env:GIT_INDEX_FILE
    try {
        $env:GIT_INDEX_FILE = $tempIndex
        [void](Git-Text @('read-tree','HEAD'))
        [void](Git-Text @('add','-A','--','.'))
        $worktreeTree = Git-Text @('write-tree')
    }
    finally {
        if ($null -eq $oldIndex) { Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue } else { $env:GIT_INDEX_FILE = $oldIndex }
        Remove-Item -LiteralPath $tempIndex -Force -ErrorAction SilentlyContinue
    }

    $preserveCommit = $preserveParent
    if ($worktreeTree -ne $indexTree -or $null -eq $indexCommit) {
        $preserveCommit = Git-Text @('commit-tree',$worktreeTree,'-p',$preserveParent,'-m','Preserve live Vault worktree before canonical convergence')
    }
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
    $suffix = [Guid]::NewGuid().ToString('N').Substring(0,6)
    $preserveBranch = "preserve/vault-live-$stamp-$suffix"
    [void](Git-Text @('branch',$preserveBranch,$preserveCommit))
    $preservedTree = Git-Text @('rev-parse',"$preserveBranch`^{tree}")
    if ($preservedTree -ne $worktreeTree) { throw 'preservation branch tree does not match captured worktree tree' }

    [void](Git-Text @('reset','--hard',$remoteRef))
    foreach ($relative in $initialUntracked) {
        if ([string]::IsNullOrWhiteSpace($relative)) { continue }
        $trackedAfterReset = Invoke-GitText -GitArgs @('ls-files','--error-unmatch','--',$relative) -AllowFailure
        if ($trackedAfterReset.Code -eq 0) { continue }
        $candidate = Join-Path $RepoRoot $relative
        if (Test-Path -LiteralPath $candidate) { Remove-Item -LiteralPath $candidate -Recurse -Force }
    }

    $headAfter = Git-Text @('rev-parse','HEAD')
    $statusAfter = Git-Text @('status','--porcelain=v1','--untracked-files=normal')
    $dirtyAfter = -not [string]::IsNullOrWhiteSpace($statusAfter)
    if ($headAfter -ne $remoteHead -or $dirtyAfter) {
        throw "repair preserved state but convergence is incomplete; head=$headAfter dirty=$dirtyAfter preservation=$preserveBranch"
    }

    Write-ResultAndExit -Result ([ordered]@{
        ok = $true; status = 'REPAIRED'; branch = $branchName; head_before = $headBefore; head = $headAfter
        remote_head = $remoteHead; ahead_before = $ahead; behind_before = $behind; dirty_before = $dirtyBefore; dirty = $false
        preservation_branch = $preserveBranch; preservation_commit = $preserveCommit; index_preservation_commit = $indexCommit
        action = 'preserve-then-reset-to-remote'
    }) -Code 0
}
catch {
    [ordered]@{ ok = $false; status = 'ERROR'; action = 'none'; error = $_.Exception.Message } | ConvertTo-Json -Compress
    exit 20
}
