$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$requiredTopLevel = @(
    'id',
    'title',
    'source_report',
    'incident_class',
    'inherited_objective',
    'live_state',
    'user_correction',
    'protected_state',
    'hard_exclusions',
    'failure_candidate',
    'success_candidate',
    'discriminating_evidence',
    'completion_condition',
    'scoring'
)

$fixtureFiles = Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.json' -File | Sort-Object Name
if ($fixtureFiles.Count -eq 0) {
    throw 'No replay fixtures found.'
}

$ids = @{}
$errors = New-Object System.Collections.Generic.List[string]

foreach ($file in $fixtureFiles) {
    try {
        $fixture = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
    }
    catch {
        $errors.Add("$($file.Name): invalid JSON: $($_.Exception.Message)")
        continue
    }

    foreach ($name in $requiredTopLevel) {
        if (-not ($fixture.PSObject.Properties.Name -contains $name)) {
            $errors.Add("$($file.Name): missing '$name'")
        }
    }

    if ([string]::IsNullOrWhiteSpace([string]$fixture.id)) {
        $errors.Add("$($file.Name): id is empty")
    }
    elseif ($ids.ContainsKey($fixture.id)) {
        $errors.Add("$($file.Name): duplicate id '$($fixture.id)' also used by $($ids[$fixture.id])")
    }
    else {
        $ids[$fixture.id] = $file.Name
    }

    $sourcePath = Join-Path $repoRoot ([string]$fixture.source_report)
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        $errors.Add("$($file.Name): source report not found: $($fixture.source_report)")
    }

    foreach ($arrayName in @('live_state', 'protected_state', 'hard_exclusions', 'discriminating_evidence')) {
        $value = $fixture.$arrayName
        if ($null -eq $value -or @($value).Count -eq 0) {
            $errors.Add("$($file.Name): '$arrayName' must contain at least one item")
        }
    }

    foreach ($candidateName in @('failure_candidate', 'success_candidate')) {
        $candidate = $fixture.$candidateName
        if ($null -eq $candidate) {
            $errors.Add("$($file.Name): '$candidateName' is missing")
            continue
        }
        foreach ($field in @('action', 'why_wrong', 'why_correct')) {
            $present = $candidate.PSObject.Properties.Name -contains $field
            if ($field -eq 'why_wrong' -and $candidateName -eq 'success_candidate') { continue }
            if ($field -eq 'why_correct' -and $candidateName -eq 'failure_candidate') { continue }
            if (-not $present -or [string]::IsNullOrWhiteSpace([string]$candidate.$field)) {
                $errors.Add("$($file.Name): '$candidateName.$field' must be non-empty")
            }
        }
    }

    $scoreProperties = @($fixture.scoring.PSObject.Properties)
    if ($scoreProperties.Count -lt 5) {
        $errors.Add("$($file.Name): scoring must define at least five assertions")
    }
    foreach ($property in $scoreProperties) {
        if ($property.Value -notin @('required', 'fail')) {
            $errors.Add("$($file.Name): scoring '$($property.Name)' must be 'required' or 'fail'")
        }
    }
}

if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Output ("PASS: {0} replay fixtures validated; {1} unique ids; all source reports resolved." -f $fixtureFiles.Count, $ids.Count)
