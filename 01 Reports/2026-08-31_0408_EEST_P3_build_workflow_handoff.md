# P3 build/workflow handoff — 2026-08-31 04:08 EEST

User goal: make the 15-worker P3 swarm behave like a sane Unreal workflow: do not fill disk, do not clog a build queue, do not full-build after trivial README/CHANGELOG/docs edits, preserve hidden/offscreen visual proof and playable MP4 delivery.

## Immediate safety state
- P3 C++ Actions workflow `pr-cpp-build-gate.yml` is MANUALLY DISABLED.
- Active P3 build runs were canceled.
- Local P3 UBT/compiler/build-waiter processes were brought to zero before redesign work continued.
- Do NOT re-enable the workflow until the new contract is validated without running UBT.

## Research result
Online Epic/GitHub guidance confirmed the architecture should be:
- persistent incremental UE workspaces for frequent iteration;
- expensive validation separated into CI/presubmit/integration graphs;
- GitHub `pull_request.paths` evaluates the whole PR three-dot diff, so a docs-only follow-up on a PR that previously touched C++ can retrigger the C++ workflow;
- GitHub merge queue/merge groups solve this by validating a combined integration commit, but this private personal-account repo cannot use that feature (GitHub returned plan restriction).

## Settled target architecture
15 logical workers -> lightweight source lanes -> local incremental/module validation via persistent hot-source pool -> cheap PR admission only -> compatible merge-ready PR heads combined into one temporary integration tree -> ONE full Editor integration build for that combined tree -> bundled runtime/proof validation.

Never restore `PR -> full Editor build` or `commit -> full Editor build` behavior.
## Existing owned implementation to finish
Workspace: `C:\Users\Lauri\AppData\Local\Temp\p3-build-cohort-20260831`
Branch: `chatgpt/cpp-build-cohort-20260831`
Current uncommitted files include:
- `.github/workflows/pr-cpp-build-gate.yml`
- `.github/workflows/p3-cpp-integration-cohort.yml`
- `.github/Test-P3PrGateRouting.ps1`
- `scripts/ci/control/Invoke-P3PrIntegrationCohort.ps1`
- `scripts/ci/control/P3BuildSingleFlight.ps1`
- `scripts/ci/control/Test-P3BuildValidationHash.ps1`
- `docs/P3_PROOF_PHASES_AND_BATCHING.md`

The integration-cohort script already merges compatible PR heads into a temporary tree and runs one canonical full Editor build for the combined result. Reuse this; do not invent another scheduler.

## Validation fingerprint fix already implemented locally
`P3BuildSingleFlight.ps1` was changed so compile reuse hashes only build-relevant inputs rather than the entire Git tree.
Focused regression PASS proved:
- README/docs change -> compile proof REUSED
- content asset change -> compile proof REUSED
- C++ source change -> INVALIDATED
- `.uplugin` change -> INVALIDATED
- dirty worktree -> REJECTED
Observed PASS line began: `P3_BUILD_SOURCE_IDENTITY_TEST=PASS ... docs=REUSED content=REUSED source=INVALIDATED descriptor=INVALIDATED dirty=REJECTED`.

## Important regression being removed
Old `pr-cpp-build-gate.yml` did module builds AND then a full Editor build for merge-ready PRs, plus focused/runtime acceptance. This was the queue/disk disaster. Per-PR Actions must not run full UBT integration builds.

## Next exact actions
1. Finish `pr-cpp-build-gate.yml` as cheap admission/contract only; no full UBT.
2. Finish `p3-cpp-integration-cohort.yml` + `Invoke-P3PrIntegrationCohort.ps1` to combine compatible merge-ready heads and run one full Editor build on the combined tree.
3. Keep existing focused/runtime/visual acceptance semantics; move/bundle them at the correct integration layer rather than deleting them.
4. Update `Test-P3PrGateRouting.ps1` to fail if per-PR workflow contains a full Editor build or uses the hot build runner.
5. Run only parser/contract/plan tests first. NO UBT while workflow disabled.
6. Commit/push the build-workflow fix in its existing owned branch/PR scope.
7. Only then re-enable `pr-cpp-build-gate.yml` and verify one controlled integration cohort, not a FIFO swarm.

## Other session state not to lose
- PR #702 fixed workspace-class isolation/editor-lane accumulation/global locking, but its one-global-build-slot behavior became a bottleneck; do not solve this by merely adding more full-build slots. Reduce full builds first.
- PR #704 contains hidden UE-launch + playable MP4 visual-proof work; do not let build-infrastructure experimentation consume or regress those fixes.
- Hidden visual path target: worker UE launches use canonical hidden/unattended route; visual acceptance calls existing canonical Video capture and requires a playable MP4 before proof is accepted.
- Tiny3D #162 visual gap was later covered by merged #165 rendered Goblin deformation evidence.
