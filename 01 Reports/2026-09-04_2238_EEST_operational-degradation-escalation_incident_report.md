# Operational degradation was allowed to escalate until user intervention

Timestamp: 2026-09-04 22:38 EEST
Status: verified behavioral incident from current user correction; exact mechanics vary by owning subsystem.

## User report (verbatim)

> this has to apply to the very slow CI churns and stalled editors and orphaned processess etc etc it can't be that one thing you are not told to ID blocks the whole stack and every time it happens again you just let it happen. these things should be documented in vault and improved upon not just let them escalate until I come and tell you what to do

## Failure pattern

The stack can observe an abnormal condition?very slow or repeating CI, an editor/process that is alive but making no useful progress, an orphan left by agent work, or another unidentified dependency?and incorrectly normalize that state as ordinary waiting. The result is global serialization or repeated churn until the user notices and diagnoses the hidden blocker.

The defect is not that every slow operation is a failure. The defect is failure to distinguish **progressing contention** from **no-progress degradation**, failure to identify the smallest owner, and failure to close recurring causes after they become visible.

## Correct behavior

1. Establish a discriminating progress signal and compare against the recent working behavior/expected phase.
2. If progress is absent or pathological, identify the smallest blocking owner using live process/job/runtime evidence rather than waiting on a label or timeout alone.
3. Keep unrelated work moving; one degraded dependency does not serialize the stack.
4. Follow processes/runtimes created or relied on by the task through terminal state, explicit handoff, or owned cleanup. A process being alive is not proof it is healthy; disappearance is not proof it completed.
5. Once causal evidence exists, fix/remove/fail-close the broken owner path and add the narrowest guard/replay so recurrence is harder.
6. Record material recurring incidents in Vault with symptom, working baseline/boundary when known, owner, cause or unresolved evidence gap, fix, and recurrence prevention.

## Recurrence closure

Shared policy must require proactive degradation ownership. Owning repos remain responsible for the concrete process/CI/editor checks and cleanup mechanisms. Vault stores chronology and replay evidence; it is not runtime authority.

## Closure found while adding the regression fixture

The global replay loader failed before it could reach the new cases because `03 Fixtures and Experiments/2026-09-01_plugin2-funnel-root-route-recovery.json` contained a `scoring` object but did not implement the current replay-ready schema. Git history showed the file entered in `9d5dc9f` as recovered local evidence. The file is now explicitly `capture_state: pending` and `replay_ready: false`; its evidence is preserved, but it no longer masquerades as an executable fixture. The supported path is to complete the current success/failure replay contract before reenabling it.
