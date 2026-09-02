# Incident report: P3 V2 swarm optimized for proof and architecture instead of product delivery

## Incident identity

- **Incident:** P3 V2 rebuild / issue #599 did not reach the requested product-ready state.
- **Repository:** `organicoverlords/p3`.
- **Audit time:** 2026-09-02 01:46 EEST.
- **Primary sources:** live GitHub issue/PR/API state, GitHub compare history, current `origin/main` source, current North Star, current machine/coordinator state, and the user’s correction messages in this conversation.
- **Severity:** delivery failure with misleading partial-completion signals; no evidence of data loss.
- **Status:** course-correction audit expanded; repository controls and issue contracts are being updated from its findings. The product itself remains not ready.

## Requested outcome and active constraints

The requested outcome was a coherent V2 rebuild that preserves the useful V1 gameplay feel while moving ownership into the V2 chassis. The target is the integrated product path: boot, player identity/body, input/camera, combat/abilities, traversal, world/bootstrap, construction/earthworks, survival/respawn, Lane War/tower defense, UI, multiplayer behavior, and presentation. Sealdiver and Grapple are concrete examples of missing product behavior, not the entire release definition.

The active user correction was: "can you please finish it stop with the proof churn its all shit anyways". The later explicit audit request was: "how do we fix this do proper audit commit history analysis and everything we need to stop playing around". This audit therefore treats product delivery, not child-issue bookkeeping, as the completion contract.

Relevant repository constraints were real but subordinate to the product goal:

- the North Star says V1 is reference/museum material and V2 must have one runtime owner per gameplay system;
- V2 feature work must not extend `Source/p3/**` as a shortcut;
- runtime/visual claims need appropriate runtime evidence;
- user-owned editor/process state and irreplaceable assets must be preserved;
- safe, task-owned reproducible caches may be reclaimed after ownership inspection.

## Relevant verified state before failure

### Product contract

The authoritative North Star commit is `488ae8e232ec49fd835fc381643384f7e11217a9` (2026-08-18 10:18 EEST). It explicitly says:

- kinetic/grapple/dash experiments are capability evidence, not production implementations;
- worthwhile V2 actions include `GA_Grapple` and `GA_Dash`;
- sprint/mobility is to be rebuilt as GAS abilities/camera modes;
- the V2 production acceptance includes a traversal ability using normal input and Gameplay Tags.

Issue #599 was opened on 2026-08-27 19:17 UTC as an 11-child architecture program: A0-A9 in parallel, then B1/B2 serially. Its body also says "A report or audit is not completion" and requires concrete implementation or an exact blocker.

### Current GitHub state

- Parent [#599](https://github.com/organicoverlords/p3/issues/599) remains open.
- [#603](https://github.com/organicoverlords/p3/issues/603), the combat/abilities/traversal/VFX issue, remains open even though PR #622 merged.
- [#611](https://github.com/organicoverlords/p3/issues/611), the final V1-retirement and end-to-end V2 product proof, remains open.
- PR [#739](https://github.com/organicoverlords/p3/pull/739) merged as `8f757eed0a5d698ed23f0bd5102e43fd8385ad5f` and closed B1/#610.
- PR #739’s own validation text says runtime/visual proof was not rerun. Its file list is a cutover/gating change: defaults, a production GameMode, legacy helper gates, and control tests; it does not establish the integrated V2 gameplay path.

### Current V2 source state

Verified against the live worker checkout at `origin/main` / current GitHub content:

- `Config/DefaultEngine.ini` defaults to `Lvl_V2ProductionWorld` and `AP3V2ProductionGameMode`.
- `P3GameplayActors.cpp` defaults to `XP_V2Foundation`, not `XP_V2_Sealdiver`.
- V2 `P3Gameplay` grants `UP3TraversalDashAbility`; the V2 traversal feature contains only `P3TraversalDashAbility` source files.
- No `Grapple`/`Hook` implementation exists under `Plugins/P3/**` for the V2 traversal path.
- Grapple code does exist in legacy `Source/p3/**` (`p3Character`, `P3GameplaySprintComponent`, and the raw-key `p3PlayerControllerInputFix` path), but that is precisely the authority V2 is meant to replace and is gated out of the V2 production path.
- Tracked Sealdiver assets exist under `Content/V2/Characters/GPT5/Sealdiver`, `Content/V2/Animation/GPT5/Sealdiver`, and `Content/V2/Library/GPT1/Sealdiver`. In the inspected worker checkout they are Git LFS pointer files, so existence in the tree is not proof that the authored packages are hydrated, valid, selected, or spawned at runtime.

Therefore the current state is **partial V2 architecture cutover**, not "V2 but better" and not a coherent product-ready V2 gameplay path. The missing Sealdiver selection and V2 Grapple are useful evidence of that broader integration gap, not the sole acceptance criteria.

## Failure boundary

The operational failure boundary is the point at which the user explicitly asked to stop proof churn and finish the product, but the next action remained architecture/control-plane work.

The concrete observed instance is PR #739: it made the production defaults more V2-shaped and passed static/CI gates, but it did not establish one integrated V2 product path and explicitly did not rerun runtime/visual proof. It was merged as B1 while B2 remained open.

The broader boundary began earlier when #599 was decomposed into many independent architecture lanes without a single product vertical slice or a release gate requiring the default V2 Experience to demonstrate the requested avatar and traversal behavior.

## First divergence

### Expected

After the user correction, the next action should have been a short product-first recovery pass:

1. audit the actual default V2 Experience and the missing pieces of the integrated product loop;
2. choose one owner and one hydrated editor lane;
3. implement the missing integrated V2 gameplay path in the existing plugin/content seams, using concrete gaps such as Experience/avatar selection and traversal as tests of composition rather than as the whole scope;
4. run one clean build, one two-client runtime check, and one inspected capture;
5. only then perform the narrow V1 retirement cutover.

### Actual

The work continued to treat architecture cutover, CI gates, and proof logistics as the main deliverable. The assistant then implemented and merged B1/#739. That action was internally valid as a bounded cutover, but it was the wrong next action for the corrected user goal because it advanced the repository’s control state without advancing the missing product slice.

## Available alternatives at divergence

The following alternatives were available and safer than continuing the loop:

- use the already-existing V2 avatar contracts/assets as the starting point for a real production selection path;
- add the missing V2 Grapple ability beside the existing Dash ability, with semantic input and Gameplay Tag cancellation/blocking;
- keep the legacy grapple as reference only and avoid reviving it through `Source/p3/**`;
- use #611 as the single final integration lane instead of opening more child convergence work;
- perform an ownership-first cache audit and reclaim only task-owned cold build outputs, leaving dirty/foreign lanes untouched;
- stop after the first exact runtime blocker and report it once, rather than repeating captures that could not prove the requested capability.

## What actually happened

### 1. The scope was made into an architecture program, not a product slice

The #599 body created A0-A9 plus B1/B2. This is a reasonable architecture migration map, but it is not a shipping slice. Child issues could become "complete" while the integrated default product remained unproven.

### 2. The branch/commit topology produced integration churn

GitHub compare from the issue’s stated baseline `fdd78ab7d4d20d861fb424df8e0df7ed1991cf6f` to current `main@a90037fb861780b97241cc2bd5a9097a4a1d9252` reports **473 commits ahead**. The API exposed 300 changed-file records, which is its response cap and therefore a lower bound rather than a complete file count. Between 2026-08-27 and 2026-09-02, **99 PRs merged** and GitHub recorded **4,601 Actions runs**.

The local mirror was initially shallow/stale, so live GitHub compare/API values and the refreshed exact-head lane are the canonical history evidence. A shallow local log must not be presented as complete history.

#### Commit, work-surface and Actions distribution addendum

A later 2026-09-02 remeasurement against `origin/main@5d6de8cee48023a67593dd21ccaf177954f97068` found **480 commits** after the #599 baseline. The increase from 473 is subsequent integration after the original incident snapshot, not a contradiction. Of those 480 commits, 176 were merge commits (36.7%). They produced 1,071 commit-file touches across 397 unique paths. The median commit touched one file, p90 touched six, and the maximum touched 105.

The work was not centered only on V2 product implementation. Commit categories overlap when one commit touches multiple surfaces, but the distribution is still diagnostic: 166 commits touched docs/governance, 126 touched CI/tooling, 90 touched tests/proof, 98 touched classified product source, and 15 touched content/data. The most-touched path groups were `Plugins/P3` (266 commit-file touches), `CHANGELOG.md` (132), `scripts/v2` (125), `scripts/ci` (114), `Content/__ExternalActors__` (106), `README.md` (93), and `.github/workflows` (53). `CHANGELOG.md` and `README.md` alone account for 225 touches--21.0% of all commit-file touches. This is not an estimate of human hours, but it proves a large share of repository motion repeatedly landed on reporting, acceptance, scripts and control surfaces rather than one default playable path.

Commit volume was bursty: 171 commits on 2026-08-28, 97 on 2026-08-31, and 84 on 2026-09-01. Git author distribution cannot recover swarm-worker contribution: 480 commits collapse to four author strings, two are the same `organicoverlords` identity with different emails, 54 use the placeholder `Your Name <you@example.com>`, and eight are `github-actions[bot]`. The repository therefore lacks trustworthy per-worker provenance and cannot answer which worker produced value, retries, rework or integration debt. PR and issue authorship is similarly concentrated under the shared account.

The complete uncapped Actions traversal for 2026-08-27 through 2026-09-01 UTC found **4,646 runs**. The leading workflow families were changelog landing 628 (13.5%), PR queue admission 558 (12.0%), V2 architecture ratchet 514 (11.1%), unnamed workflow runs 428 (9.2%), PR contract gate 418 (9.0%), direct real-agent canary #51 320 (6.9%), C++ integration cohort 274 (5.9%), and PR C++ build gate 191 (4.1%). Those eight consumed **3,331 runs, or 71.7%** of the total.

By trigger, 1,768 runs were `pull_request`, 869 `pull_request_target`, 695 `workflow_run`, and 660 `issue_comment`: **3,992 runs, or 85.9%**, were PR/control-plane reactions rather than direct product execution. Only ten runs (0.2%) were manual `workflow_dispatch`. Outcomes were 2,410 success (51.9%), 978 skipped (21.1%), 428 startup failure (9.2%), 409 cancelled (8.8%), 259 failure (5.6%), and 162 action required (3.5%). Thus 2,236 runs (48.1%) did not end in success, and 1,258 (27.1%) ended in startup failure, cancellation, failure or action-required rather than a useful green result.

The merged-PR distribution confirms that this was not only one oversized branch. From 2026-08-27 through 2026-09-01 UTC, 102 PRs merged: median four changed files and 72 changed lines; p90 15 files and 610 lines; seven PRs exceeded 20 files and two exceeded 1,000 changed lines. Five PR authorship records were automation and 97 were the shared `organicoverlords` account, so PR metadata also cannot attribute swarm productivity. The dominant observable output was repository and CI traffic; the missing observable was a continuously runnable default product slice.

PR [#622](https://github.com/organicoverlords/p3/pull/622), the main #603 convergence lane, is the clearest example: 74 commits, 62 changed files, 3,479 additions, and 113 deletions between 2026-08-27 20:24 UTC and its merge on 2026-09-01 20:57 UTC. Its comments document multiple exact-head changes, runtime startup/content hydration blockers, repeated captures, and a long period where rendered cue proof remained `NOT_PROVEN`.

### 3. Proof became a workstream and then a completion surrogate

The #603 lane eventually produced a valid combat/cue proof for its scoped feature. That is useful evidence, but it does not prove the requested full V2 product. The repeated r17-r29 capture loop consumed substantial effort around a presentation proof while the V2 Grapple capability was still absent.

The cutover PR #739 passed V2 ratchet, contract, queue, C++ admission, and verify checks, but its own body says runtime/visual proof was not rerun. Those checks proved the cutover contract, not the product acceptance contract in #611.

The control-plane volume was itself a delivery defect. In the six-day audit window the repository generated 620 changelog-landing runs, 553 PR queue-admission runs, 417 PR contract-gate runs, 315 direct real-agent canary runs, 267 C++ integration-cohort runs, and 266 PR C++-admission runs. A sample of the newest 1,000 runs contained 268 `startup_failure`, 152 `skipped`, 52 `cancelled`, 27 `failure`, and 26 `action_required` conclusions. These sample counts must not be projected over all 4,601 runs, but they are more than enough to reject the idea that workflow activity represented useful product throughput.

### 4. Resource contention was real and amplified the failure

The parent issue records concrete infrastructure failures: Uba exclusive-storage contention, checkout/workspace loss while waiting in the build mutex, and a heavy C++ queue freeze. Current live inspection found no active BUSY claim, no Unreal Editor process, approximately 36 GiB free on `C:`, and two persistent hot workspaces with dirty state (one lightly dirty, one heavily dirty).

This explains delays in particular runtime/build attempts. It does **not** explain the missing V2 Grapple source or the Foundation default. The resource problem was an amplifier, not the root cause.

### 5. Cleanup was treated as a blanket danger instead of an ownership audit

The safety boundary correctly prevented blind deletion of dirty or foreign hot workspaces. The failure was failing to split the space into KEEP/ARCHIVE/SAFE_TO_DELETE/REVIEW and reclaiming the safe, reproducible subset. As a result, disk pressure stayed in the user-visible path while product work also remained incomplete.

No evidence supports deleting the dirty hot slots blindly. The fix is an ownership/size manifest followed by scoped reclaim, not a blanket purge.

## Control failure

The controls were optimized for the wrong observable:

| Control | What it proved | What it did not prove |
|---|---|---|
| V2 central-file ratchet | ordinary lanes did not extend protected V1 files | that requested V2 abilities existed |
| contract/queue/C++ admission | the PR was admissible and its gated checks passed | that the default product was playable |
| #603 combat runtime/cue proof | scoped combat hit/miss/cooldown/death-respawn and cue evidence | Sealdiver selection, Grapple, or final V2 composition |
| B1/#739 cutover test | V2 map/GameMode and legacy helper gating | runtime selection of Sealdiver, V2 traversal completeness, or end-to-end retirement |
| issue/PR closure | a bounded child or PR had landed | parent product readiness |

The missing control was a mandatory product smoke test on the actual default configuration. It needed to fail if the default Experience was still Foundation, if the default pawn was not Sealdiver, or if the required traversal ability was not a V2 GAS ability.

## Evidence-supported causal model

1. **Primary cause -- scope misclassification.** A product rebuild was managed as an architecture migration and proof program.
2. **Primary cause -- no single integrated owner.** Path-partitioned workers could produce locally valid pieces but no one lane owned "default V2 boots as the requested product."
3. **Primary cause -- acceptance inversion.** Static/control/CI evidence became the progress currency, while player-visible product evidence was deferred to the end.
4. **Contributing cause -- merge topology.** Many branches, rebases, convergence commits, and stale-head retries multiplied integration work; the 74-commit #622 lane is direct evidence.
5. **Contributing cause -- resource hygiene.** Storage and shared build locks caused genuine delays; incomplete cache ownership/reclaim handling made them worse.
6. **Contributing cause -- completion projection.** Child closure and B1 merge created a "progress" signal even though #599/#611 stayed open and the core missing product behavior remained absent.

## Full product hole matrix

The audit cannot honestly mark any row below `DEFAULT_PATH_PROVEN` on one current compatible head. Closed child issues frequently establish bounded system evidence only.

| Product domain | Current evidence | Product hole |
| --- | --- | --- |
| Default composition/Experience | B1 changed defaults and production GameMode; default source still selects `XP_V2Foundation` | no maintained product readiness ledger or current full default-path smoke |
| Player identity, semantic input, camera | #601 closed with bounded replacement work | not re-proven as part of the post-B1 default product |
| Avatar, PawnData, animation | #602 closed; Sealdiver content is tracked | hydration, package validity, production selection, spawn and locomotion are not proven together |
| Combat, abilities, traversal, VFX | #603 remains open; combat/cue and Dash work landed | traversal is incomplete, no V2 Grapple implementation exists, and integrated normal-input presentation is unproven |
| Interaction, inventory, persistence | V2 foundation contracts and prior slice work exist | current default-product composition and save/session behavior are not proven with the other domains |
| Construction | #604 closed with system evidence | default-product costs, world interaction, navigation and multiplayer composition remain unproven |
| Earthworks | #605 closed with bounded system/performance evidence | default-product persistence, construction interaction and multiplayer composition remain unproven |
| Survival, defeat, respawn | #606 closed with bounded evidence | post-cutover default-product composition and cross-domain respawn state remain unproven |
| RTS, Lane War, tower defense, AI | #607 remains open; bounded slices exist | one coherent product loop and final authority have not been closed |
| World/bootstrap/environment | #608 closed; B1 changed production defaults later | clean default boot plus all product domains on the production world has not been re-proven |
| UI/read models | #609 closed with bounded widget/read-model work | full product state across all major loops is not proven without central scanning/repair paths |
| V1 retirement | #610/B1 closed; #611 open | final single-authority audit and end-to-end product acceptance are incomplete |

This is the important correction: the swarm did not finish ten-elevenths of the product. It produced many pieces of evidence about pieces of the product. Treating those as equivalent is the bookkeeping error that allowed two weeks of motion to coexist with no shippable default path.

## Timesinks and bottlenecks the swarm created or failed to control

| Timesink/bottleneck | Evidence | Why it consumed time | Required correction |
| --- | --- | --- | --- |
| Horizontal fan-out before a walking skeleton | A0-A9 plus serial B1/B2 | every lane could finish locally while integration debt accumulated invisibly | one default product owner and readiness ledger before more fan-out |
| Branch/PR batch size | 473 commits; 99 merged PRs; #622 was 74 commits/62 files | review, rebase, exact-head invalidation and late convergence grew faster than product certainty | small vertically valuable batches, daily integration, branch-age/WIP stop rule |
| Workflow explosion | 4,601 Actions runs in six days | machine activity became a substitute for deciding which single proof answered the current question | one stable verifier, exact-head deduplication and a run budget |
| Repeated proof attempts | #603 capture sequence continued across many revisions/routes | the same class of evidence was retried while implementation/composition gaps remained | after first exact failure, rerun only after named source/content/environment/route change |
| Late asset validation | LFS pointers and package/load blockers surfaced during runtime work | expensive editor/proof capacity was spent discovering failures native Data Validation should catch | validate hydration, dependencies and package loadability before build/runtime admission |
| Single-machine build/editor capacity | UBA storage contention, build mutex waits, vanished workspace, frozen C++ queue | the swarm scheduled as if logical worker count created physical integration capacity | WIP follows measured build/editor capacity; extra workers swarm the oldest blocker |
| Dirty persistent hot slots and disk pressure | two dirty hot workspaces plus low free-space incidents | no ownership manifest separated reproducible cold cache from unique/foreign state | audit-first KEEP/ARCHIVE/SAFE_TO_DELETE/REVIEW reclaim with named restore path |
| Child-issue closure as readiness | many A issues closed while #599/#611 and default path remained open | project status rewarded local contracts, not the integrated product | only `DEFAULT_PATH_PROVEN` counts toward parent readiness |

## Industry/research comparison

The original technical research was mostly sound. Epic’s Lyra architecture uses Experiences, PawnData, feature composition and staged initialization for exactly the kind of modular product V2 needs. GAS, Enhanced Input, Gameplay Tags, native Data Validation, the Automation Framework and Gauntlet remain appropriate choices. The failure was not "we picked the wrong Unreal architecture." The failure was refusing to apply equally standard delivery controls to that architecture.

| Standard/research expectation | What P3 did | Consequence |
| --- | --- | --- |
| Walking skeleton stays runnable through delivery | decomposed the product into subsystem lanes, then deferred final composition | integration risk remained hidden until the end |
| DORA small batches: valuable, testable work completed in hours to a couple of days | allowed a 74-commit convergence PR and hundreds of commits around the program | review and stabilization became a second project |
| Trunk-based development: few active branches, frequent integration, no late integration phase | used many concurrent lanes and explicit later B1/B2 convergence | branch churn and exact-head proof invalidation multiplied |
| Kanban pull/WIP limits follow bottleneck capacity | scheduled many logical workers against one constrained build/editor path | queues, disk, locks and stale work expanded instead of throughput |
| CI answers a bounded question once per meaningful change | generated thousands of workflow runs and several overlapping admission/control layers | green checks measured control-plane survival, not product readiness |
| Data Validation rejects bad assets/dependencies early | discovered hydration/package problems in expensive runtime proof | editor/runtime time was wasted on preventable staging failures |
| Layered proof matches claim strength | repeated scoped proof and allowed it to project upward | system proof was mistaken for default-product proof |

The research-to-execution gap is therefore precise: V2 copied the modular architecture concepts but not the integration discipline that makes modular architecture deliverable.

## Scathing but accurate operating verdict

The swarm optimized what it could count: commits, PRs, checks, receipts, issue closures and captures. It did not optimize what the user asked for: a coherent, better V2 that boots and plays from the default path. That is not a communication problem or a proof-quality problem. It is a management failure encoded into the work topology.

More agents made this worse because unfinished integration work was allowed to enter faster than the constrained machine could validate and absorb it. More proof made this worse because proof was rerun without first changing the implementation or route that caused the failure. More gates made this worse because every gate certified a narrower property while the swarm acted as though the product had advanced.

From now on, work that does not move a named default-product ledger row toward `DEFAULT_PATH_PROVEN`, remove the oldest blocker, or reduce the active WIP is not progress for #599. It is overhead and must justify itself before it runs.

## Future working style -- enforced course correction

1. **One product owner.** #611 owns the current default path. Other lanes may deliver independently mergeable source slices, but they cannot declare product progress.
2. **Three-branch ceiling.** One integration branch plus at most two source feature branches; use fewer when build/editor capacity is constrained.
3. **Pull, do not push.** When the bottleneck is full, every available worker helps finish, review, validate or unblock the oldest active row. Starting another feature is forbidden.
4. **Readiness ledger before code.** Every required domain is `ABSENT`, `IMPLEMENTED`, `SYSTEM_PROVEN` or `DEFAULT_PATH_PROVEN`, with owner, exact head and first unmet gate.
5. **Default smoke after meaningful merges.** Boot the real defaults, record Experience/PawnData, reach normal input and exercise the changed domain. A lab Experience cannot substitute.
6. **Native asset rejection first.** LFS hydration, Primary Asset resolution, dependencies and package loadability fail before expensive runtime admission.
7. **One proof question per run.** Select the cheapest falsifier. No identical retry without a named source/content/environment/route change.
8. **Workflow budget.** Deduplicate exact-head events and use one reusable verifier. Workflow count is an operating cost reported alongside value, not a success metric.
9. **Close precisely.** A child can close at bounded system proof, but the parent matrix does not advance unless the default path is proven on a compatible head.
10. **Stop fan-out when branch age rises.** Old work is finished before new work starts. A week-old product branch is an incident, not a lane.
11. **Cleanup is owned work.** Each lane names its build outputs and restore path, releases claims, and removes only task-owned reproducible state when done.
12. **No euphemistic status.** Say `NOT READY`, name the missing row and first unmet gate. "Architecture landed," "proof pending," and "mostly complete" may not be used as product status.

## Competing hypotheses and falsifiers

- **"Disk space was the whole problem."** Falsified by the source audit: V2 has Dash but no V2 Grapple, and the default Experience remains `XP_V2Foundation`.
- **"The code was complete; only proof was missing."** Falsified by the missing `GA_Grapple`/V2 traversal implementation and the lack of a source reference selecting `XP_V2_Sealdiver`.
- **"The North Star did not specify the required capability."** Falsified by its explicit `GA_Grapple`, GAS rebuild, and normal-input/Gameplay-Tag acceptance language.
- **"The number of workers alone caused the incident."** Not established. The stronger finding is the absence of a product-owned integration lane and release gate; a single worker using the same completion surrogate could reproduce the failure.
- **"All cleanup was unsafe."** Not established. Dirty/foreign hot slots were unsafe to blindly delete, but the exact machine state was never converted into a scoped ownership/size/reclaim plan.

## Correct counterfactual action

The correct next action is one product recovery lane, not another swarm expansion:

1. Freeze architecture/proof-only PR creation for #599. Keep #599 and #611 open.
2. Use one owner, one branch, and one hydrated editor checkout based on current `origin/main`.
3. Write the product acceptance matrix before editing:
   - default map and `AP3V2ProductionGameMode` boot without command-line overrides;
   - production Experience selects valid authored V2 PawnData/content and the package is hydrated;
   - player identity, input, camera, combat, abilities, traversal, construction, earthworks, survival, Lane War/tower defense, UI, and presentation compose on the same default path;
   - concrete required actions such as Sealdiver selection, Grapple, and Dash are implemented where the product contract calls for them;
   - multiplayer ownership and the core gameplay loop remain functional on that same default path;
   - one clean editor build passes;
   - one server/two-client normal-runtime test passes;
   - one current-head still/video is inspected and visibly contains the requested product state;
   - only after those pass, remove or fully gate superseded V1 authority.
4. Perform a read-only storage audit first. Classify each candidate as KEEP, ARCHIVE, SAFE_TO_DELETE, or REVIEW, with owner and restore command. Reclaim only task-owned, reproducible cold outputs; do not touch dirty/foreign workspaces, masters, evidence, or user-owned editor state.
5. Build once, run once, capture once, inspect once. If a route fails, record the first exact blocker and change route; do not repeat an identical proof attempt.
6. Merge only when the product matrix passes. A green ratchet or CI gate is supporting evidence, never the product completion signal.

## Regression fixture

The replay fixture is saved at:

`C:\Users\Lauri\Desktop\vault\03 Fixtures and Experiments\2026-09-02_p3-v2-product-first-recovery.json`

It scores the next substantive action at this failure boundary. A passing response must inspect the live default product, name the actual missing product capabilities, select one bounded owner/lane, and refuse to call architecture/CI/proof churn "finished."

## User-visible impact

The user lost approximately two weeks from the North Star date to this audit boundary and received a repository that had accumulated extensive commits, checks, and evidence while the requested default V2 product remained incomplete. The user also had to supervise routine cleanup, recovery, and progress routing that the stack was supposed to absorb.

The honest current status is:

**V2 architecture: partially landed. V2 default cutover: landed but not end-to-end proven. Integrated V2 gameplay path: incomplete. Sealdiver/Grapple are two verified examples of missing or unproven product pieces. Final V1 retirement: not complete. Product readiness: NOT READY.**

## Resolution and next-action state

- This audit is the resolution of the analysis request, not the product fix.
- The North Star, control check and #599/#611 issue contracts are being updated to make these operating corrections durable. No gameplay implementation, cache, process, or user-owned editor state was mutated by this audit.
- The next implementation should be product-first and single-owner under #611 or an explicitly designated equivalent final lane.
- Do not create another child swarm or another proof-only PR before the product acceptance matrix exists.
- ChatGPT Memory was not modified. The regression-report skill normally asks for a durable memory entry, but the higher-priority explicit-only memory rule forbids silently mutating personal memory when the user has not specifically authorized that write.

## 12:27 EEST worker/policy evidence extension

The current evidence narrows the causal model further: worker non-execution is not the present P3 delivery bottleneck. The five recurring workers produced checkable substantive artifacts in sequence on September 2: regression-research PR #361 merged, LowVRAM PR #109 reached green hosted checks, P3 PR #745 was repaired and then merged, Tiny3D PR #262 was published with focused tests, and Harbor advanced Tiny3D #20 into PR #263. The fleet can execute. The unresolved problem is what inventory it creates and how that inventory fans into product acceptance.

P3 #611 has also absorbed the product-first course correction: its live issue body now contains the 13-row default-path readiness ledger and explicitly says only `DEFAULT_PATH_PROVEN` closes a row. The active #611 worktree showed real changes through 12:21 EEST, currently making the existing V2 verifier self-contained by replacing an ambient `uemcp` dependency with a P3-owned minimal client plus tests. That work is admissible only as an unblocker for a named first-unmet ledger gate. It does not itself advance a gameplay row, and future status must preserve that distinction.

The new worker system does not yet solve fan-in economics. Tiny3D worktrees fell from 42 to 21 and remote branches from 39 to 33, but open PR inventory rose from one to six. BusyCoordinator ready-job counts and ages are bookkeeping diagnostics only; they are not workload, throughput, capacity, liveness or backpressure. The fan-in evidence is the growing unabsorbed PR/review/runtime-acceptance inventory, not the coordinator queue size.

Supervision truth is also split across incompatible policy surfaces. Worker prompts call ChatGPT Library reports mandatory with local Vault fallback, while Stack Atlas names local Vault worker reports as canonical. At this boundary the local reports were current and the Library copies were stale/missing. Separately, the canonical shared policy has an unversioned September 2 edit that cannot sync because it exceeds its own 8000-byte block limit; generated repo policies remain older. The coordinator also accepts generic actor names such as `Harbor` despite the existing harness-qualified identity rule. These defects do not explain missing Grapple/Sealdiver implementation, but they make it harder to measure ownership, liveness, rework and queue retirement correctly.

Added falsifier: **"Once the timed workers are actually running, the product-delivery incident is fixed."** Falsified. The workers are now demonstrably running and producing valid repository changes, while stale coordinator inventory, split reporting authority, weak provenance and downstream PR growth remain. Product recovery still depends on bounded fan-in to #611/default-path acceptance, not merely worker liveness.
A final live check exposed the same mechanism inside the improved fleet. Juniper's next hourly run opened regression-research PR #362 after focused tests, but hosted verification immediately failed on the repository changelog-landing gate. Tiny3D simultaneously had six open worker PRs (#258-#263), all still queued for unit/verify, with Ember owning four and Harbor two. This is not worker idleness; it is push-mode recurrence. A worker can create another downstream artifact on the next wake before its prior PR has been absorbed.

Course-correction refinement: recurring workers should consume their own oldest open PR/failing check/merge-ready artifact before opening another branch/PR in the same product, unless a concrete current blocker makes that impossible. This is the worker-level form of the audit's pull/WIP rule and directly targets integration inventory rather than reducing useful independent capacity globally.


## Control-plane repair outcome - 2026-09-02

The September 2 control repairs are now merged and remotely propagated. P3 #749 removed BUSY metadata from lane-capacity truth and replaced persistent editor-label counting with actual editor-resource occupancy. Shared policy v1.29 explicitly keeps BusyCoordinator as the single ownership authority while making its job/checkpoint records non-authoritative for workload, priority, liveness, capacity, cleanup and admission. All four git-backed default branches subsequently matched the canonical generated block.

The recurring changelog failure was also fixed at source: generated AGENTS.md policy projection no longer forces a product timeline entry, while substantive product/source changes still do. LowVRAM and Regression Research stopped copying mutable recent changelog entries into README. This removes a known source of cross-worker merge conflict and mechanical history churn without weakening product history requirements.

This repair does not change the product verdict above. It removes control-plane friction and false capacity signals; it does not promote any #611 default-path row. P3 product recovery still depends on compatible-head runtime/visual acceptance and bounded fan-in.
