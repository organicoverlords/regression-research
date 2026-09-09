# #861 current-owner routing replay — remove assistant steering, keep freshness guards

Captured: 2026-09-09  
P3 current main: `48c38850eb320c6f89a3cd5fccb5548b07ef3592`  
Prerequisite: regression-research #820 is still **OPEN**, so this is bounded prework; no P3 control-plane mutation is proposed.

## Result

The 40-run historical convergence sequence supports a narrower YAGNI finding than “simplify the cohort safety system”:

- **10/40 runs were explicit `workflow_dispatch` launches**; 30 were normal `workflow_run` automation.
- **7/10 manual dispatches entered native cohort execution. All 7 produced no durable receipt**: 5 were invalidated by `BASE_MOVED`, 2 by `HEAD_MOVED`.
- **All 3 durable receipt successes came from automatic `workflow_run` executions.** Removing the 10 manual dispatches from the replay therefore removes no observed durable receipt success.
- The replay still retains automatic safety controls after removing manual dispatches: **9 automatic base-move invalidations**, **2 automatic head-move invalidations**, and the **1 real build/acceptance failure**.
- At the run-record level, dropping manual steering would reduce workflow launches **25.0% (40 → 30)** and native executions **31.8% (22 → 15)** while preserving all observed durable receipts and the real failure path.

## Why the base/head guards are not the YAGNI target

Of the **14 `BASE_MOVED` invalidations**, current-main attribution shows:

- **1/14** was a merge of a PR already inside that stale run's selected cohort (`#2810` in run `34291610571`), i.e. the class current receipt-chain reuse can plausibly absorb.
- **13/14** were unrelated main merges (`#2803`, `#2804`, `#2808`, `#2811`, `#2826`, `#2830`, `#2831`, `#2835`, `#2805`, `#2837`, `#2820`, `#2840`, `#2841`).

So weakening current-base identity to avoid rebuilds would be unsafe. The historical churn was mostly genuine base invalidation, not duplicated checking of an equivalent tree.

The **4 head-move invalidations** are likewise required exact-head safety. One was pre-build and three happened during module execution. The single native failure was not orchestration churn: focused acceptance failed because `P3Testing` could not load.

## Current owner trace

Current P3 main already has the intended owner shape:

- planner debounce/coalescing with `cancel-in-progress: true` only for the planning group;
- serialized cohort build group with running native builds preserved;
- `Test-P3CohortSelectionCurrent` checks before/between/during/after native modules;
- immutable hash-bound cohort receipts;
- merge guard candidate-tree/prefix-tree verification;
- `p3 PR auto merge` revalidates through the canonical guard, claims exact Busy scopes, continues receipt chains, refreshes main, and dispatches cohort refresh after merges.

Therefore the first accepted routing/execution finding should be **`reuse/shrink` at the assistant layer**, not another P3 scheduler/lock/receipt abstraction:

`repo-owned cohort + merge guard + auto-merge -> normal ready C++ PR chain -> duplicate layer: assistant workflow-dispatch/run-by-run convergence steering -> replacement: allow repo owner to progress normal states; inspect only terminal/anomalous states or product proof -> safety boundary: retain stale/head/prefix/Busy guards`

## Frozen replay metrics

| Metric | Baseline | Without manual dispatch steering |
|---|---:|---:|
| Workflow runs | 40 | 30 |
| Native executions | 22 | 15 |
| Durable receipts | 3 | 3 |
| Real build/acceptance failures retained | 1 | 1 |
| Automatic base-move safety controls retained | 9 | 9 |
| Automatic head-move safety controls retained | 2 | 2 |

This is an activity/run replay, not wall-clock or CPU accounting. It proves the manual-dispatch layer contributed no durable receipt in this episode; it does not claim every unrelated-main rebuild can be eliminated.

Structured evidence: `02 Evidence/2026-09-09_issue-861_current-owner-routing-replay.json`.
