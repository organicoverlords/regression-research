# P3, Tiny3D, MCP and coordinator operating audit

Audit boundary: 2026-09-02 EEST. This is a live operating correction, not product proof and not authorization for broad deletion.

## Executive verdict

The same failure pattern exists across the stack: control artifacts and resource labels are being promoted into blockers beyond what they actually prove. P3 expresses it as proof/changelog/build churn and artificial resource pressure; Tiny3D as branch/PR inventory; MCP as telemetry/deployment residue. BusyCoordinator itself is collision state; its ready-job inventory is bookkeeping and must not be treated as workload pressure or a product queue.

The stack has enough mechanisms. It lacks enforced completion economics: bounded WIP, one integration owner, branch/worktree retirement, truthful capacity advertisement, bounded logs and cleanup that can actually see every cache class.

## Live findings

## Commit, work-surface and automation distribution

This section measures what the work actually centered on. A "commit touch" means a commit changed at least one file in that category; categories can overlap and are not estimates of labor hours. Commit-file touches count repeated file appearances across commits. The P3 range is the #599 baseline through `origin/main@5d6de8cee48023a67593dd21ccaf177954f97068`; Tiny3D and MCP use 2026-08-27 through the current remote default head.

| Repository | Commits | Merge commits | Merged PRs in six-day window | Commit concentration | Dominant surfaces |
| --- | ---: | ---: | ---: | --- | --- |
| P3 | 480 | 176 (36.7%) | 102 | 171 commits on Aug 28; 97 on Aug 31; 84 on Sep 1 | docs/governance 166 commit touches; CI/tooling 126; product source 98; tests/proof 90 |
| Tiny3D | 219 | 81 (37.0%) | 110 | 100 commits on Aug 31; 67 on Sep 1 | docs/governance 124 commit touches; tests/proof 107; product source 81; CI/tooling 49 |
| MCP | 18 | 9 (50.0%) | 9 | 12 commits on Aug 27 | docs/governance 9 commit touches; product source 8; CI/tooling 8 |

P3 had 1,071 commit-file touches across 397 unique files. Its leading surfaces were `Plugins/P3` 266, `CHANGELOG.md` 132, `scripts/v2` 125, `scripts/ci` 114, `Content/__ExternalActors__` 106, `README.md` 93 and `.github/workflows` 53. `CHANGELOG.md` and `README.md` alone were touched 225 times. P3's 102 merged PRs had a median of four files/72 changed lines and p90 of 15 files/610 lines; #622 remained the largest by changed lines at 62 files and 3,592 lines.

Tiny3D had 679 commit-file touches across 256 unique files. `CHANGELOG.md` was touched 111 times and `README.md` 76, versus 102 touches across `src/tiny3d`; `tests/test_animation_quality.py` alone was touched 21 times. Its 110 merged PRs had a median of four files/105 lines and p90 of 11 files/881 lines; nine exceeded 1,000 changed lines. The work centered heavily on animation-quality contracts, tests, evidence lineage, changelog/readme maintenance and rapid PR fan-out--not simply reusable product code.

MCP was materially smaller: 42 commit-file touches across 19 unique files, with 15 on `CHANGELOG.md`/`README.md`, four on `src/server.ts`, and the remainder spread across clone, process and front-door scripts. Its nine PRs were small (median four files/42 lines), but eight linked worktrees and 13 remote branches for zero open PRs still indicate unreconciled task state.

Authorship telemetry is not fit for swarm accountability. P3's 480 commits resolve to four Git author strings, including 54 commits under `Your Name <you@example.com>` and two email variants of the shared `organicoverlords` identity. Tiny3D resolves to only two author strings, one of them the same placeholder; all 110 PRs are authored by the shared account. MCP resolves to two identities while all nine PRs are authored by the shared account. We can measure repository motion, but not reliably assign useful work, retries or rework to individual workers. Required correction: every lane must emit stable harness/worker identity in the claim, branch, PR and machine-readable completion receipt; Git author identity alone is not accepted provenance.

P3 Actions were overwhelmingly control-plane work. An uncapped page traversal found 4,646 runs from 2026-08-27 through 2026-09-01 UTC. The top eight workflow families consumed 3,331 runs (71.7%): changelog landing 628, PR queue admission 558, V2 architecture ratchet 514, unnamed workflow runs 428, PR contract gate 418, direct real-agent canary #51 320, C++ integration cohort 274 and PR C++ build gate 191. PR, PR-target, workflow-chain and issue-comment events accounted for 3,992 runs (85.9%); only ten were manual dispatches. Outcomes were 51.9% success, 21.1% skipped, 9.2% startup failure, 8.8% cancelled, 5.6% failure and 3.5% action required. This is the numerical center of the swarm's work: admission, ratchets, changelog, canaries, chained workflows and retries--not continuous default-product integration.

Correction: publish this distribution daily while the recovery is active, with product-source/content change, default-path acceptance movement, CI/control activity, rework/revert, branch/worktree retirement and stable worker provenance shown separately. Set an automation budget: a workflow family that does not protect a named release gate is removed, consolidated or made non-blocking. Throughput is counted as accepted default-product capability, not commits, PRs or runs.

### Tiny3D

- 42 linked worktrees, 39 remote branches, one open PR and 13 open issues at the later distribution snapshot.
- 41 worktrees were clean; only the primary checkout had three untracked paths.
- The clean worktree estate was about 2.15 GiB. Disk cost is modest; coordination cost is severe.
- Many worktrees had no corresponding open PR or active BUSY claim.
- Product risk: workers can keep producing isolated contract/proof slices while newest-150/P3 campaign integration remains the bottleneck.

Correction: one campaign integration owner, bound new work by the downstream campaign-integration/P3-acceptance bottleneck rather than a global lane count, enforce the two-working-day branch-age stop, and retire worktrees/branches after merge or closure. Useful independent work may continue when it does not add unabsorbed downstream inventory.

### MCP

- `shell-mcp` was healthy on loopback port 3000.
- Canonical BUSY JSON contained both `claims` and `coordinator`; prior metadata erasure was not reproduced.
- Live checkout was dirty and on a checkpoint branch while `origin/master` had advanced.
- `transport.jsonl` was about 168 MiB and had no source-side rotation.
- 45 orphan atomic-write temp files consumed about 3.8 MiB.

Correction: treat the live install as an immutable deployment target, bound/rotate telemetry, sweep only stale unowned temp files, and prevent normal product tasks from turning into MCP repair.

### BusyCoordinator

- 0 active jobs, 297 ready, 4 blocked, 145 completed and no live claims at the final snapshot.
- State/operation bounds exist and the canonical contract is intact.
- Exact-scope ownership works; product prioritization, global WIP and queue aging are outside the coordinator's current enforcement.

Correction: keep the coordinator narrow. Ready/blocked/completed jobs are optional resumability metadata, not admission, backpressure, priority, capacity or liveness. Orchestrators choose work from the live product/repo state and consult BUSY only for exact mutation collisions. Do not make queue cardinality, job age, or old handoff entries a reason to stop, wait, clean, allocate, or select work.

### P3 disk and builds

- C: had about 47.6 GiB free at the stable snapshot; no Unreal/UBT/compiler process was active.
- P3 primary checkout occupied about 17.6 GiB: Content 12.6 GiB, Intermediate 2.67 GiB, Plugins 1.2 GiB, Git 0.9 GiB, Binaries 0.15 GiB.
- Five P3 local runner roots occupied about 3.9 GiB. Hot workspaces held only about 0.09 GiB and no build cache.
- The guarded sweep found no eligible candidate and reclaimed zero, because it excludes primary and runner caches. Its explanation that all remaining caches were warm/running was factually wrong.
- Build admission is 25 GiB floor plus 8 GiB growth reserve. The 75/100 GiB sweep trigger/target is proactive policy, not a prerequisite.
- The nominal two-slot hot-source pool is serialized by one global mutex held across synchronization, inner queue waiting and the entire build. Its effective source-build capacity is one.
- Canonical build slot two disables UBA; UBA exclusive-storage contention is a resource collision, not a compile failure.

The supplied historical screenshot adds two failures:

- after reporting roughly 660 MiB free physical RAM, the worker said builds should remain paused. That is not a valid machine-wide gate. Free physical RAM is only one pressure signal; the required capacity decision uses commit limit, charge/remaining, operation peak and progress. At the live audit boundary, Windows reported roughly 27 GiB free virtual/commit headroom despite low physical memory, so "work will never start because of RAM" was unsupported;
- after one guarded scanner found no eligible lane/hot cache, the worker claimed the remaining 47.6 GiB was tracked/project data. The scanner did not inspect primary generated output or runner-root caches, so it could not support that conclusion. "No eligible candidate in this scanner" was inflated into "nothing reclaimable exists."

Correction: complete cache inventory with explicit dispositions, truthful effective concurrency, cleanup before scarce locks, no lock-while-waiting chains, and retry only after measured capacity change.

## Cross-stack operating rules

1. One integrated product/campaign owner per product.
2. Bound new downstream inventory by the actual scarce integration/build/editor/review/runtime-acceptance capacity; this is not a global cap on useful independent work.
3. When a bottleneck is full, workers finish or unblock the oldest item feeding it instead of creating more unabsorbed downstream slices.
4. Branches, worktrees, logs, receipts and queues are costs with owners and retirement rules.
5. A clean worktree without an open PR/claim is a cleanup candidate, not latent capacity.
6. Health and proof remain narrow facts; neither implies product completion.
7. Cleanup inventories all owned cache classes and reports why each is kept or reclaimable.
8. Advertised capacity must equal effective concurrency after mutex/UBA/editor constraints.
9. No identical build/proof retry without a named source/content/environment/route/capacity change.
10. MCP transports work; BusyCoordinator owns exact scopes; product orchestration owns priority and WIP.

## What remains unperformed

- No user-owned or ambiguous worktree, branch, P3 cache, runner workspace, MCP log or temp file was deleted.
- No live MCP deployment was restarted or changed.
- No P3 build/runtime claim was made.
- Actual cleanup requires ownership/restore receipts for the primary and runner caches; actual two-slot hot-source concurrency requires a code change and contention test.

## Default-path acceptance correlation follow-up

The interrupted Codex correlation was continued after correcting two overpromoted recovery diagnostics. Per-lane distribution reporting is not a durable worker obligation, and one integration plus two feature lanes is not a global swarm cap. Distribution is a centrally computed recovery diagnostic; new inventory is bounded at the actual scarce downstream integration/build/editor/review/runtime-acceptance bottleneck.

Retrospective result: **0 of the 13 #611 required rows can currently be promoted to `DEFAULT_PATH_PROVEN` on one compatible post-cutover head.** This does not erase useful subsystem gains. #601 has strong moduleless V2/dedicated/two-client proof; #603/#622 has two-client combat plus inspected rendered proof; Construction has bounded runtime/two-client/rendered proof. The promotion failure is fan-in.

The decisive compatibility boundary is merged PR #739: it changed production defaults to `Lvl_V2ProductionWorld` and `AP3V2ProductionGameMode`, explicitly composed Lane War, and explicitly did **not** rerun runtime/visual acceptance afterward. Therefore pre-cutover or bounded subsystem evidence is not automatically default-path evidence.

Standalone table: `C:\Users\Lauri\Documents\Codex\2026-09-02\expl\outputs\DEFAULT_PATH_ACCEPTANCE_CORRELATION.md`.

## 12:27 EEST live worker/policy follow-up

The current five-worker generation is no longer an enabled-but-idle fleet. Fresh local worker reports and exact GitHub artifacts show substantive work: Juniper merged regression-research PR #361 at `37662419`; Alder published LowVRAM PR #109 at `d8afd259` with 23/23 focused tests and its hosted checks are now green; Cedar repaired P3 PR #745 at `1f5a99f8`, which was subsequently merged; Ember published Tiny3D PR #262 at `1535f9a8` with 22 focused tests; Harbor then moved from selection into Tiny3D #20 and opened PR #263. This is real execution evidence, not scheduler/claim evidence.

The reporting fix is nevertheless split-brain. Current worker prompts say `/Worker Reports/<name>.md` in ChatGPT Library is mandatory and local `C:\Users\Lauri\Desktop\vault\worker-reports\<name>.md` is fallback. The live Stack Atlas instead names the local Vault directory as the worker-report canonical source. At this follow-up boundary the local reports for all five workers were current, while Library contained only stale Juniper/Alder copies from September 1 and no current Cedar/Ember/Harbor report. The reason Library publication failed is not proven from the available run outputs. Correction: choose one report owner/source and make the other a projection; do not encode two competing "mandatory/canonical" surfaces in prompts and Atlas.

The shared-policy deployment path is currently broken. `C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md` was modified at 03:20 EEST but still identifies itself as version 1.27 / 2026-08-31. The only local diff adds immediate exact-claim recovery after proven owner termination. `node sync-agent-policy.mjs --check-remotes` aborts with `POLICY_BLOCK_TOO_LARGE_BYTES=8233 max=8000`, so the change cannot propagate. P3, Tiny3D and Regression Research AGENTS blocks therefore still contain the previous generated text. This is a migration failure: local canonical prose changed, version did not, and generated consumers cannot receive it.

Policy enforcement is also incomplete. The shared rule requires coordinator actors to include harness plus task/session suffix, but BusyCoordinator accepted live owner `Harbor` for `tiny3d#20-locomotion-action-proof-binding`; the prior Ember claim was likewise worker-name-only. Current worker PR branches carry some worker identity, but three of the four sampled worker heads (P3 #745, LowVRAM #109, Tiny3D #262) were still committed as `Your Name <you@example.com>` while PR authorship remains the shared `organicoverlords` account. The earlier audit finding that Git/PR telemetry cannot attribute worker value therefore remains unresolved.
Coordinator cardinality is large but that is not, by itself, a health or throughput defect. The 12:24-12:27 snapshot had 318 ready jobs, many old/duplicate/superseded. Those records become a fault only where consumers treat them as executable inventory, priority, liveness or backpressure. This distinction matters: BUSY/job history may preserve resumability, but it must remain inert unless an orchestrator explicitly selects a specific record. The correct invariant is not "drain the coordinator backlog"; it is "never let backlog size or age block unrelated work."

Current P3 #611 work is real, not claim-only: the `chatgpt/issue611-default-path-20260902` worktree had six current verifier/client/test edits with file/test-cache activity through 12:21 EEST. The issue now contains the required default-path readiness ledger, so stabilizing the single verifier can be legitimate unblock work. It must still be charged against the first unmet default-path gate; verifier improvement is not itself a product-row promotion.

Tiny3D shows mixed recovery. Linked worktrees fell from the audit's 42 to 21 and remote branches from 39 to 33, so retirement is happening. At the same time open PRs rose from one at the audit snapshot to six, including #258-#263, four of them Ember/Harbor lanes. That is the same inventory-risk pattern in smaller form: cleanup improved, but new downstream review/integration inventory is entering faster than one campaign owner has demonstrated absorption.

Machine pressure also worsened during the follow-up: BusyCoordinator's runtime snapshot reported 39.03 GiB free on C:, down from roughly 47.6 GiB in the earlier operating audit, with no Unreal/UBT/compiler process reported in that snapshot. This does not identify the consumer, but it strengthens the earlier finding that cache/output inventory and retirement remain unresolved.

Additional process hygiene finding: three Desktop Commander child PowerShell processes from September 1 were still alive more than 22 hours later, including a Harbor Tiny3D inspection command and an Ember report-write command. Their CPU totals were under one second each and they were not evidence of current worker progress. No cleanup was performed because ownership/termination safety was not established. Long-lived completed-looking transport children must not be counted as liveness and should be reconciled by their owning transport/session.
Final reconciliation strengthened the WIP finding. Juniper's next hourly run started at 12:24 EEST and published regression-research PR #362 at `d80ab619`; hosted `verify` then failed because the substantive PR omitted `CHANGELOG.md` (`CHANGELOG_LANDING_FAIL`). The worker report had recorded 64/64 focused tests and `git diff --check` before publication. This is a current example of the audit's control-churn mechanism: a short recurring run can create another PR before running the repository's actual landing verifier, immediately generating avoidable CI/rework.

Tiny3D's six open PRs #258-#263 were all still queued for `unit` and `verify` at the final check. Four are Ember lanes and two are Harbor lanes. The workers are therefore producing new review/CI inventory across successive runs before prior inventory has been absorbed. The correction is not to stop useful workers; it is to make an owning worker consume its own oldest open/failed/green PR before opening another downstream lane unless a current blocker makes that impossible.


## Verified control-plane resolution - 2026-09-02

The control-plane defects found in this audit were carried through to merged fixes rather than left as recommendations. P3 PR #749 merged as `acb102a38e17ddafc341135be74b217fb6181d9f`: warm-lane reuse no longer treats broad BUSY issue-number matches as capacity truth, and editor capacity uses actual hydrated/build/runtime occupancy rather than persistent editor labels. The live planner moved from five label-counted non-primary editor lanes to two actual resource occupants.

Canonical shared policy is now v1.29 after agents PRs #26/#27. Its generated block is 7889/8000 bytes. BusyCoordinator is explicitly the single ownership authority; job/checkpoint records are coordination bookkeeping and must not become workload, priority, liveness, capacity, cleanup or admission. The dead-owner recovery rule remains, but a claim alone still does not prove liveness.

The changelog control was also corrected instead of accepting fleet-wide history churn. Generated `AGENTS.md` projections are timeline-exempt while ordinary product/source changes remain changelog-gated. LowVRAM and Regression Research README timelines now use a merge-stable canonical `CHANGELOG.md` link instead of copying mutable recent entries. The rollout merged through P3 #752 (`f70a1bbf`), LowVRAM #112 (`b974a2a3`), Tiny3D #265 (`4d88cb8c`) and Regression Research #364 (`f4e29645`). Canonical `sync-agent-policy.mjs --check-remotes` then reported all four git-backed origin defaults matching the source; five non-git harness projections were skipped as intended.

Tiny3D #265 also provided a direct non-blocking-execution test. Its two hosted jobs remained queued on self-hosted runners with zero steps started. The exact PR head was mergeable and locally passed four focused tests plus the landing checker; the private repository exposed no enforceable branch-protection requirement. The unavailable runner transport therefore did not become task failure or an invented merge prohibition.

Temporary propagation worktrees were retired after landing. The post-cleanup snapshot was P3 9 worktrees, LowVRAM 5, Tiny3D 18 and Vault 9, with C: at 33.47 GiB free. That disk number is a real measurement; it is not evidence that BUSY/job metadata should restrict cleanup or capacity. Resource decisions must still be based on current attributable resource state.

One residual race remains worth preserving: a P3 source lane was legitimately reusable while the meteor worker had released its mutation claim, then that recurring worker later reacquired p3#603 and advanced its remote branch. The lane was restored to the meteor branch without resetting or reconciling worker-owned divergence. A reusable worktree path is therefore not worker identity; each run must rediscover current admitted checkout and exact ownership rather than assuming a persistent path remains reserved between released claims.
