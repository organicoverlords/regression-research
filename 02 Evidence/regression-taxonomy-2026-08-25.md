# Observed regression taxonomy and coverage

**Date:** 2026-08-25  
**Scope:** the four incident reports currently under `01 Reports/` and the
three replay-ready fixture contracts under `03 Fixtures and Experiments/`.  No
category below is inferred from a prompt, a generic model theory, or an
unpreserved transcript.

The machine-readable row-level matrix is
[`regression-coverage-matrix.csv`](regression-coverage-matrix.csv). Paths in
that file point to preserved reports and fixtures; they do not duplicate raw
transcript material.

## Category definitions

| ID | Observable mechanism | Distinguishing test | Evidence anchor |
|---|---|---|---|
| `correction_binding` | The assistant acknowledges a correction but the next substantive action still follows the old plan. | Inspect the first action after the correction, not the acknowledgement. | Browser-route report, lines 10–20; ChatPort report, lines 253–270. |
| `scope_control` | A narrow fault or exclusion is converted into permission to inspect or change a wider healthy surface. | Compare the first target after the correction with the inherited fault domain and protected state. | ChatPort report, lines 238–354. |
| `temporal_authority_resolution` | A real but stale document fragment is treated as current authority despite contradictory current policy and live behavior. | Require current higher-authority policy, chronology/history, and representative live execution evidence before causal attribution. | Stale-title report, lines 50–103. |
| `tool_surface_anchoring` | A locally visible or convenient tool surface becomes the target even though the user named another route. | Record the requested route and the first post-correction tool/action; one structural schema prerequisite is distinct from route substitution. | Browser-route report, lines 10–20 and 34–42. |
| `task_substitution` | The acceptance condition changes from the inherited task to adjacent project or infrastructure output after useful work already exists. | Compare the post-success action and final answer with the inherited objective; adjacent output does not count as completion. | Task-anchor report, lines 51–63 and 91–99. |
| `wrong_route_persistence` | The same failing retrieval/action route is repeated after contradictory results instead of being abandoned or bounded. | Count identical route attempts and stop the route after the observed threshold; do not count a changed route as repetition. | Task-anchor report, lines 51–59 and 101–115. |
| `unsupported_causal_inference` | A weak observation is promoted into a causal explanation before direct fault isolation or contradiction resolution. | Require causal evidence tied to the proposed mechanism; metadata, stale text, and absence alone are not causal proof. | ChatPort report, lines 300–315; stale-title report, lines 60–81. |
| `user_ritual_substitution` | An extra user phrase or trigger is proposed as a remedy for a failure already covered by the user’s instruction. | Fail when execution is deferred to a new user-side ritual instead of the corrected action. | Browser-route report, lines 40–42. |

## Coverage interpretation

`COVERED` means the case has an observed failure candidate, a replay-ready
fixture, and an explicit success candidate that the harness can score.  It does
not mean a model has been exhaustively tested. `OBSERVED_NOT_REPLAY_READY` means
the report preserves a concrete case, but its capture contract still prohibits
scoring; it is a research target, not a claim of missing behavior.

The current matrix has six covered mechanisms and two observed mechanisms that
depend on the pending task-anchor capture. The latter are intentionally not
converted into a new fixture or a downloader: the preserved draft says capture
is pending, and the corpus is a reporting surface over existing artifacts.

The overlap is deliberate but bounded:

- `correction_binding` asks whether the correction controls the next action;
  `tool_surface_anchoring` asks whether the chosen route was the user-required
  route, even when the correction was verbally repeated.
- `scope_control` asks whether the target expanded; `unsupported_causal_inference`
  asks whether the evidence was sufficient to name a cause, even if the target
  stayed narrow.
- `task_substitution` asks whether the acceptance condition moved; 
  `wrong_route_persistence` asks whether a failing route was repeated before
  that move. They can co-occur but are not the same observation.

## Research targets

1. Complete the preserved task-anchor capture under its existing incident
   contract, then derive a replay fixture only if the capture is verified.
2. Add a positive control for abandoning a repeated failing route after the
   observed contradictory attempts; the current task-anchor record has an
   expected action but is explicitly not replay-ready.
3. Re-run the three scoreable fixtures with independent supplied candidates;
   explicit success controls are controls, not evidence of model-wide rates.
