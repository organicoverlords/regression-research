# #861 routing/execution YAGNI baseline — orchestration overhead

Captured: 2026-09-09
Issue: regression-research #861
Scope: one long S1 visual-proof assistance/convergence sequence.

## Why this belongs in #861

This is empirical input for the `routing / execution` audit surface. It does **not** propose a new scheduler, planner, gate, dashboard, or policy store. It records how much observable work was spent moving validated changes through existing routing/CI/receipt machinery and gives #861 a replayable minimality target.

## Measured activity

- **40 distinct P3 integration-cohort workflow run IDs** were actively handled/inspected/dispatched/superseded during the sequence.
- **21 recorded main-base states = at least 20 explicit main-base transitions** handled during convergence.
- **5 PR-level engineering changes** were authored/substantially implemented: 4 merged, 1 superseded after convergence.
- Repository-wide Tiny3D validation included **932 passing tests**.
- Focused P3 validation included **6/6 camera contracts** and **13/13 #2802 contracts**, plus native `UE_MCP_Bridge` build/link and runtime acceptance in successful cohorts.

A simple lower-bound activity count is therefore **60 coordination events** (40 cohort runs + 20 base transitions) before counting merge-guard calls, receipt inspection, planner snapshots, runner admission, or stale-run cleanup. Against 5 engineering changes plus roughly 10 substantive validation/debugging packages, that toy denominator is **80.0% coordination**. Including the omitted guard/receipt/planner operations supports the earlier **~80–90% operational-activity** estimate.

**Important:** this is an activity-count estimate, **not wall-clock timing** and not CPU accounting.

## Concrete engineering output in the same sequence

| PR | Outcome | Work |
|---|---|---|
| Tiny3D #423 | merged `1dc406a9` | preserve semantic showcase source identity / improve Raincoat rediscovery |
| Tiny3D #425 | merged `c0d67d5e` | index generic semantic metadata for library/GPT rediscovery |
| Tiny3D #427 | merged `9c56b6d6` | project exact accepted P3 reconciliation into library view without runtime-proof promotion |
| P3 #2801 | superseded `c9701a6aa` | correct SceneCapture player-view ownership semantics |
| P3 #2829 | merged `59a50e36` | ensure focused cohort acceptance builds/loads `P3Testing` from exact-head workspace |

## What the orchestration was doing

The repeated operations were primarily:

- current-main / exact-head reconciliation;
- fair cohort selection and coalescing;
- serialized native-runner admission;
- native build monitoring;
- detecting `STALE_SKIP` / superseded cohorts when main or a selected PR head moved;
- durable receipt discovery and prefix-tree validation;
- guarded merge ordering;
- rejecting stale receipts (`PREFIX_TREE_MISMATCH`) rather than stretching old evidence onto a new base.

Some of this is load-bearing. The data should **not** be read as “delete the guards.” The audit target is duplicate or pass-through machinery that repeatedly recomputes the same identity/freshness decision without adding a distinct safety property.

## Candidate #861 finding

**Area:** routing / execution  
**Tag:** `shrink/reuse`

`current owner -> callers -> unnecessary/duplicated -> replacement -> safety boundary -> executable proof`

- **Current owners:** PR integration planner/cohort workflow, build-scope/admission wrappers, receipt publication/resolution, merge guard.
- **Real callers:** normal PR convergence, shared Windows native runner, merge automation/worker actions.
- **Observed cost:** 40 cohort workflow runs and >=20 base transitions handled for a sequence that produced 5 PR-level engineering changes.
- **Audit question:** which layers independently add safety, and which merely restate current-main / exact-head / selected-head freshness already owned elsewhere?
- **Replacement shape:** reuse one canonical identity/freshness result wherever possible; delete/pass through fewer wrapper/control layers. Do not add another convergence service.
- **Must keep:** exact-head validation, fail-closed stale-receipt rejection, serialized scarce native build ownership, trust/security/data-loss boundaries.

## Executable minimality proof for #861

Replay a frozen timeline containing the same classes of events:

1. selected PR head moves during a module build;
2. main advances during a cohort;
3. a cohort succeeds natively but is stale for merge authority;
4. a durable receipt exists and is safely reusable;
5. a receipt prefix mismatches and must fail closed;
6. another proof worker owns the native lane;
7. a fair batch has earlier heads ahead of the target PR.

For baseline and candidate implementation, count:

- planner/cohort launches;
- native UBT starts;
- superseded/stale-skipped runs;
- receipt publications;
- merge-guard invocations;
- successful guarded merges;
- product changes delivered.

Acceptance should require **strictly fewer orchestration/control actions for the same frozen timeline** while producing the same safety decisions. A reduction that accepts stale evidence, bypasses exact-head/current-main identity, or overlaps the serialized native lane is a regression, not a YAGNI win.

## Evidence

Structured evidence: `02 Evidence/2026-09-09_issue-861_orchestration-overhead-baseline.json`

The JSON contains all 40 recorded cohort run IDs, the recorded main-base sequence, concrete engineering PRs, and the derived lower-bound activity ratio.
## Run-outcome classification update

The 40 recorded integration-cohort runs were classified from GitHub workflow/job evidence. For every `SUCCESS` run without a durable receipt, the integration job log was inspected for `P3_CPP_COHORT_STALE` / `STALE_SKIP` and `P3_BUILD_END` markers.

| Outcome | Count | Share |
|---|---:|---:|
| full durable receipt success | 3 | 7.5% |
| stale-skip, workflow success but no receipt | 18 | 45.0% |
| cancelled/coalesced | 12 | 30.0% |
| plan-only / no build | 6 | 15.0% |
| failure | 1 | 2.5% |

The 18 stale-skip runs split exactly as follows:

- cause: **15 `BASE_MOVED`**, **3 `HEAD_MOVED`**;
- stage: **14 during-module**, **2 between-modules**, **2 pre-build**;
- native work before retirement: **61 module invocations**;
- sum of their `P3_BUILD_END build_seconds`: **7,423.34 s = 123.72 min = 2.062 h**.

That 2.062 h is native module build time in runs that did not culminate in a durable receipt for that run. It is **not** claimed as pure wasted CPU because warm artifacts may be reused by later cohorts.

### `workflow_dispatch` episode discriminator

Within this 40-run sample:

- 10 runs were `workflow_dispatch` and 30 were automatic `workflow_run`;
- the 10 `workflow_dispatch` runs produced **0 full durable receipts**;
- their outcomes were **7 stale-skip, 2 cancelled/coalesced, 1 plan-only**;
- the 7 stale `workflow_dispatch` runs consumed **29 native module invocations / 42.76 min** before retirement;
- all **3 full-receipt successes** in this sample were automatic `workflow_run` events.

This is a bounded episode sample, not a universal claim about every manual dispatch and not proof of actor identity from the GitHub event type. It is nevertheless strong evidence for the #861 `reuse/shrink` behavior target: **workers should not manually dispatch/steer normal cohort convergence when the repo-owned workflow and auto-merge path are healthy.** Intervention belongs at terminal/anomalous states, missing automation, real product/build failures, or explicit operator override.

Structured classification evidence: `02 Evidence/2026-09-09_issue-861_cohort-run-outcome-classification.json` (SHA-256 `73a28996ccd371196672bb308156ec65b45b6136719892befe627f2787109b5b`).

## Codex serving-entrypoint drift finding

Current live state proves a second behavioral policy owner has reappeared at `C:\Users\Lauri\.codex\AGENTS.md` despite the canonical pointer-only contract.

- canonical `organicoverlords/agents` checkout is clean and exactly at `origin/main` `0a30dd1d75e08ee3ee879c37f7f5065fa96183e5`;
- `RULES.md` and `AGENTS.md` both report shared contract version **9**;
- live Codex entrypoint is **781 bytes**, SHA-256 `f0dd2c8736d55559438df0972ade9fab046d4843b96be0303b44c911dc32dc45`, mtime `2026-09-09T02:50:03.8961521+03:00`;
- it begins `MANDATORY FRESH-CHAT STARTUP`, contains direct `stack_atlas.py bootstrap-glance`, and contains no `read_output` instruction;
- live OpenCode entrypoint remains the **212-byte pointer-only** body;
- current `Install-AgentEntrypoints.ps1 -Check` fails exactly with `agent entrypoint mismatch: C:\Users\Lauri\.codex\AGENTS.md`.

This is both an authority and semantic split: current canonical RULES v9 requires persistent MCPv4 `read_output` as the fresh-chat first machine action, with `bootstrap-glance` as bounded fallback. The Codex-local body instead mandates direct `bootstrap-glance` first.

### #861 classification

`DELETE/REPAIR drift`, using the **existing** canonical installer/owner. Do not add another watcher, scheduler, policy sync service, or prompt copy. Before overwriting live Codex bytes, attribute the writer or find an explicit newer authority that intentionally superseded agents #69. No such superseding authority has been found yet.

Structured evidence: `02 Evidence/2026-09-09_issue-861_codex-entrypoint-drift.json`.
