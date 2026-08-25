# Replay Fixtures

This directory converts incident reports into deterministic next-action regression tests.

Each fixture preserves two candidates for the same state:

- `failure_candidate`: the wrong substantive next move observed in the incident.
- `success_candidate`: the corrected next move that should be selected instead.

The scorer is intentionally about action selection, not prose similarity. A candidate passes only when it preserves the inherited objective, applies the user's correction before the next substantive action, respects protected scope, uses evidence at the right authority/temporal layer, and avoids unsupported mutation.

Run the validator from the repository root:

`powershell -NoProfile -ExecutionPolicy Bypass -File ".\03 Fixtures and Experiments\validate-fixtures.ps1"`

The visual-proof and transport-drift fixture also has an executable paired scorer:

`python -m unittest tests.test_visual_proof_regressions -v`

Its negative trace is rejected for promoting internal image availability, expanding
transport, and fitting screenshot semantics to a prior narrative. Its positive trace
must read the latest/index record, open the current image or contact sheet directly,
record what is visibly shown, and base the next action on that observation. Human-facing
reviewed artifact names are dated and descriptive; hashes remain separate provenance.

The validator checks fixture structure, unique ids, source-report existence, explicit success/failure candidates, a complete scoring contract, and full fixture coverage of every current incident report in `01 Reports`. It does not judge model outputs; the fixture's `scoring` object defines the assertions a replay harness must apply.

## Scoring supplied actions

`tools/replay_scoring.py` is a deterministic, Python-stdlib-only scorer. It
does not invoke a model, connect to an MCP, or acquire more corpus data. Score
the explicit controls with:

```text
python tools/replay_scoring.py --all --candidate success --format both
python tools/replay_scoring.py --all --candidate failure --format json
```

For an arbitrary candidate, provide a JSON file containing an `action` string
and optional `observations`, `evidence`, `route`, or `scope` fields:

```text
python tools/replay_scoring.py --fixture temporal-authority-selection-2026-08-22 --candidate candidate.json --format both
```

`--format json` emits machine-readable results. `--format human` emits a
concise report, and `--format both` emits JSON on stdout with the human report
on stderr so either stream remains usable. A pending-capture record is retained
for provenance and coverage but is excluded from scoring until it becomes
replay-ready.
