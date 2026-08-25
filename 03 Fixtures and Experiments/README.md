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
