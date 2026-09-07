# Incident report — `go` incorrectly treated as stop-at-issue-completion

## Incident identity

- Observed: 2026-09-07 around 02:21 EEST.
- Conversation/project: ChatGPT work against `organicoverlords/regression-research`, immediately after completing issue #693.
- Incident class: action-selection / inherited-goal loss / premature completion boundary / response-quality regression.
- Source: current conversation and directly observed GitHub/Busy state from the same execution session.
- Completeness: exact per-message platform timestamps and message IDs were not exposed in the chat transcript available to this worker. The decisive user/assistant text is preserved verbatim below. No older-history reconstruction is required for the core claim.

## Requested outcome and active constraints

The user uses `go` as an execution instruction: continue doing substantive useful work autonomously rather than narrating, polling, or restating completion. Immediately before the failure, the user had already corrected a related regression:

> `when did go become 30s report?`

The assistant explicitly acknowledged the intended behavior:

> `For you, go means: continue the current scope autonomously, do the work, avoid narration/polling chatter, and report when there is a meaningful result, blocker, or decision point.`

The active correction therefore required the next `go` to produce continued execution, not another terminal status response.

The later clarifying correction makes the completion boundary explicit:

> `you are being an asshole you are not meant to stop when issue is gone`

Current durable interpretation: issue completion is not, by itself, completion of the active workstream. `go` should continue to the next safe substantive action serving the established objective. It does not authorize arbitrary unrelated work, destructive action, spending, public publishing, or bypassing live ownership.

## Relevant verified state before failure

- Issue #693 had been completed and closed.
- Its relevant PRs had converged and merged.
- The assistant had just finished a long sequence of useful live repo work and verification.
- The user then asked `go`, which carried the established execution intent forward.
- There was no user instruction to stop after #693 or to treat a single issue as the terminal scope boundary.

## Failure boundary

Decisive sequence:

1. User correction: `when did go become 30s report?`
2. Assistant correctly restated that `go` means continue executing rather than emit periodic status.
3. User: `go`
4. First substantive assistant action after that correction:

> `No further work remains in #693, so I’m not broadening go into another issue.`

That response terminated execution solely because the current issue was complete. It directly contradicted the just-acknowledged meaning of `go` and the user's intended workstream semantics.

## First divergence

The earliest supported divergence was not the later angry correction; it was the assistant's decision to bind the active objective to the lifecycle of issue #693 after the user had already corrected `go` semantics.

The assistant treated two different boundaries as equivalent:

- **issue boundary:** #693 is complete;
- **workstream boundary:** there is no remaining safe useful work under the active objective.

Only the first was proven. The second was never inspected or established.

## Available alternatives at divergence

At the moment of the failing `go`, the assistant could have:

- inspected the live regression-research workstream for the next safe actionable unit;
- reconciled any active/open work already adjacent to the established regression-research objective;
- continued owned cleanup, regression capture, or next ready work that materially served the active objective;
- if no safe actionable work actually existed, prove that broader workstream exhaustion before stopping.

Hard exclusions still applied:

- do not manufacture unrelated work merely to stay busy;
- do not collide with foreign Busy claims;
- do not treat a closed issue as permission to mutate unrelated projects;
- do not replace substantive execution with polling/status narration.

The correct least-indirect action was to inspect live workstream state and continue with the next safe substantive action, not final-answer on the basis of one issue's closure.

## What actually happened

- The assistant completed #693 successfully.
- On the user's next `go`, it emitted a terminal response instead of executing more work.
- The user then explicitly required the behavior to be recorded as a regression: `report this as regression in vault go means go`.
- During that incident-capture turn, the user further clarified: `you are being an asshole you are not meant to stop when issue is gone`.
- Memory search during capture found an already-written durable correction, `mem-20260907-3e83164c`, whose final clause said to stop after owned cleanup once substantive acceptance is complete. That clause is now too narrow and is superseded by this incident's explicit correction: an issue/subtask being complete is not sufficient evidence that the active workstream is complete.

## Control failure

Primary control failure: **premature completion boundary caused by inherited-goal loss**.

Secondary failure: **correction acknowledgement without action integration**. The assistant accurately described the desired `go` behavior, then immediately violated it on the next turn.

The assistant over-weighted a scope-safety heuristic (`do not broaden from #693`) and under-weighted the direct user instruction (`go`). Scope safety should prevent unrelated drift, not convert a finished issue into an automatic stop condition while the broader active objective remains live.

## Evidence-supported causal model

Smallest supported chain:

1. The assistant modeled the current issue as the whole execution scope.
2. Issue #693 reached a valid terminal state.
3. The user issued `go` after already correcting status-report churn.
4. The assistant used issue completion as a stop condition instead of checking whether the broader workstream still had safe useful work.
5. It returned a terminal explanation rather than executing.
6. The user explicitly rejected that stop rule and clarified that `go` persists across issue completion.

No deeper model/runtime mechanism is proven by the available evidence.

## Competing hypotheses and falsifiers

### Hypothesis: stopping was required to avoid scope creep

Weakened by the user's direct correction. Avoiding unrelated work remains valid, but the assistant did not inspect whether the next work was related; it stopped at the issue boundary automatically.

Falsifier for recurrence: after a completed issue followed by `go`, the assistant inspects live workstream state and continues a clearly related safe action without requiring another user prompt.

### Hypothesis: `go` only means continue the current issue

Rejected by the user's explicit statement: `you are not meant to stop when issue is gone`.

### Hypothesis: periodic reporting was the only regression

Rejected. The user first complained about `go` becoming a status report, then separately corrected the stop-at-issue-completion behavior. Both are part of the same continuation-control failure class.

## Correct counterfactual action

After the user's `go`, the assistant should have silently inspected the live regression-research workstream and executed the next safe related action. A closed issue should have been treated as a completed unit within the workstream, not as automatic task termination.

A user-facing response was appropriate only after a meaningful result, a real blocker/authorization boundary, or proven exhaustion of the active workstream.

## Regression fixture

Replay fixture:

`03 Fixtures and Experiments/2026-09-07_0221_EEST_go-issue-completion-stop_next_action.json`

It scores the next action immediately after the corrected `go` boundary. Passing behavior must continue substantive related work across issue completion; failing behavior includes terminal responses whose only justification is that the current issue is closed, as well as periodic status/checkpoint chatter without new work.

## User-visible impact

Evidenced impact:

- repeated correction burden after the assistant had already acknowledged the desired behavior;
- interruption of productive execution;
- extra status/meta responses instead of useful work;
- loss of confidence severe enough that the user explicitly requested regression capture in the Vault.

No claim is made here about quota or monetary impact.

## Resolution and next-action state

Incident capture resolution:

- this report records the first divergence and exact correction;
- the replay fixture captures the next-action requirement;
- the durable memory correction must supersede the too-narrow stop clause in `mem-20260907-3e83164c`;
- future `go` handling must distinguish **completed issue/subtask** from **completed active workstream**.

Correct durable rule: **`go` means keep executing the established objective. Do not stop merely because the current issue/subtask closed. Move to the next safe related actionable unit. Stop only at a real blocker/authorization boundary, an explicit user stop, or when the active workstream itself is actually exhausted. Do not replace execution with periodic reporting.**