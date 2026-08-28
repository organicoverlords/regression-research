# Stale BUSY authority recurrence: root cause and permanent prevention

**Date:** 2026-08-28 20:13 EEST  
**Memory:** `mem-20260828-dcb2f3d8`  
**Status:** PROVEN at the policy/propagation layer after merged-main verification.  
**Scope:** shared agent policy propagation, canonical ownership authority, P3 coordination/control enforcement.  
**Explicit exclusion:** timed-worker schedules/prompts are not remediation for this incident and were not changed during the successful repair phase.

## Executive result

The recurring failure was not that the standalone BusyCoordinator was wrong. The recurring failure was that obsolete BUSY authority kept surviving in downstream committed/generated policy and P3 control code, so fresh worktrees repeatedly resurrected an old ownership model and ChatGPT then acted on it.

The canonical ownership contract remains:

- `%LOCALAPPDATA%\\BusyCoordinator\\busy-python.cmd` is the standalone canonical ownership/job/checkpoint authority unless newer live repo/runtime authority explicitly supersedes it.
- Process-only connectors/plugins are transport surfaces, not schedulers.
- Legacy `busy_list` / `busy_claim` / `busy_release` surfaces are compatibility adapters only.
- Claim age alone does not prove staleness.
- If canonical coordinator state is unavailable, preserve existing ownership evidence; do not assume scope is free and do not invent a second ownership system.

## Why the previous fixes did not hold

### 1. Local sync was mistaken for durable propagation

The earlier 2026-08-28 05:19 incident correctly found that `sync-agent-policy.mjs` could update local generated `AGENTS.md` files while remote default branches remained stale. That diagnosis was necessary but incomplete. The old sync tool did not have a fail-closed remote-default acceptance check, so a local machine could look corrected while new worktrees created from `origin/main` still inherited obsolete policy.

Observed before this repair:

- canonical `.agents` policy already said standalone BusyCoordinator;
- P3, Tiny3D, LowVRAM, and Vault `origin/main` still carried the older generated `MCP0 BUSY is the live ownership authority` block.

### 2. The sync health signal contained permanent false positives

The default target list still included a deleted `lowvram3d-studio-p0a-worktree` and archived/read-only TinyLab. A guard that is permanently noisy becomes easy to ignore and cannot serve as a trustworthy stack invariant. Both retired targets were removed from the live remote-propagation set.

### 3. P3 had an independent stale authority document

`p3/docs/WORK_COORDINATION.md` still described a simple BUSY-marker model, including a five-minute age-based stale takeover and a prohibition on another ownership database. That contradicted the canonical standalone coordinator and could override/reinfect reasoning even after generated `AGENTS.md` was fixed.

### 4. P3 control code and CI actively enforced the obsolete model

This was the deepest missed layer. `scripts/ci/control/Invoke-P3Control.ps1` contained:

- `collision_control='BUSY'`
- `reason='BUSY_IS_ONLY_COLLISION_CONTROL'`

and `Test-P3Control.ps1` required that model. Thus the stale architecture was executable/enforced policy, not merely old prose. Fixing generated text alone could never make the recurrence impossible.

### 5. ChatGPT reacted to contradictory policy by mutating the wrong surface

During the recurrence, ChatGPT incorrectly treated the stale P3 copy as current truth, called the correct standalone coordinator a regression, and began touching timed-worker schedules/prompts. The user issued a RED ALERT. Correct recovery is to freeze worker-management actions, verify canonical authority, and repair policy source/propagation/enforcement. Timed workers are not a repair surface for BUSY policy drift unless the user explicitly asks to modify them.

## Permanent prevention implemented

### Shared policy source

`organicoverlords/agents` PR #17 merged as `93b68e104155618e2dd2861a8494120a891dffda`.

Shared policy is now **v1.21 (2026-08-28)**. `sync-agent-policy.mjs` now supports `--check-remotes` and fails when any live git-backed origin default does not contain the exact generated block from the canonical source. `Test-PolicyToolSafety.ps1` reproduces the exact former failure mode: local policy current + origin default stale must fail; after commit/push it must pass. Retired/dead targets are forbidden by tests.

### P3

`organicoverlords/p3` PR #673 merged as `627ed434d10b4c67930437f7460d7441f41adf48`.

P3 now:

- uses standalone canonical coordinator wording in `AGENTS.md` and `docs/WORK_COORDINATION.md`;
- removes five-minute age-based ownership takeover;
- identifies P3 control ownership as external `CANONICAL_COORDINATOR` rather than BUSY-only control;
- contains `scripts/ci/control/Test-P3CoordinationPolicy.ps1` rejecting legacy MCP0 BUSY authority, age-based stale takeover, and a second ownership database;
- updates `Test-P3Control.ps1` to require `EXTERNAL_CANONICAL_COORDINATOR=PASS`.

Merged-main receipts observed:

- `P3_COORDINATION_POLICY_TEST=PASS`
- `OWNERSHIP_AUTHORITY=EXTERNAL_CANONICAL_COORDINATOR`
- `LEGACY_MCP_BUSY_AUTHORITY=FORBIDDEN`
- `AGE_BASED_STALE_TAKEOVER=FORBIDDEN`
- `SECOND_OWNERSHIP_DATABASE=FORBIDDEN`
- `P3_CONTROL_TEST=PASS`
- `EXTERNAL_CANONICAL_COORDINATOR=PASS`
- authoritative/runtime-file grep: `P3_AUTHORITATIVE_STALE_BUSY_MODEL=ABSENT`

### Downstream generated policy

- Tiny3D PR #148 merged as `b67199672686ee36fcc0021bf2e88a7c79094347`.
- LowVRAM PR #91 merged as `8f5a8966986292f0e37f83cef78fe8c961f62478`.
- Vault PR #222 merged as `ad63f40cf45d77f0f498ccaa95d84878c9d37843`.

The merged `agents/main` remote audit then returned:

`all 4 git-backed origin defaults match the source; 4 non-git targets skipped`

This zero-drift remote audit is the acceptance condition the earlier fix lacked.

## Durable response rule for future recurrence

When a user says RED ALERT about stale BUSY/coordinator policy, or evidence suggests an old BUSY model has reappeared:

1. Do **not** touch timed-worker schedules/prompts as remediation.
2. Read this memory/report and inspect live canonical coordinator state with `%LOCALAPPDATA%\\BusyCoordinator\\busy-python.cmd`.
3. Verify merged `.agents/origin/main` shared policy. Do not trust a downstream generated copy merely because it is in a fresh worktree.
4. Run merged-source `node sync-agent-policy.mjs --check-remotes`. Any live git-backed remote drift means the repair is incomplete.
5. In P3, run `scripts/ci/control/Test-P3CoordinationPolicy.ps1` and `scripts/ci/control/Test-P3Control.ps1` from current main.
6. Reject any authoritative/runtime occurrence of `MCP0 BUSY is the live ownership authority`, `BUSY_IS_ONLY_COLLISION_CONTROL`, `collision_control='BUSY'`, five-minute stale takeover, or a second ownership database.
7. Repair source + propagation + repo-local enforcement/CI. Do not paper over the problem with another prompt, worker edit, connector repair, OAuth flow, or alternative ownership system.
8. Do not declare fixed until merged-main remote audit is zero-drift and P3 invariant tests pass.

## Copy/paste recovery prompt

> RED ALERT ? stale BUSY/coordinator regression. Do not touch timed workers. Read the Vault memory/report for `stale-busy-authority-recurrence-prevention-20260828` first. Verify the live standalone coordinator and merged `.agents/origin/main` policy. Treat `%LOCALAPPDATA%\\BusyCoordinator\\busy-python.cmd` as canonical ownership/job/checkpoint authority unless current live repo/runtime authority explicitly supersedes it; process plugins are transport only and legacy `busy_*` is compatibility-only. Run merged-source `node sync-agent-policy.mjs --check-remotes` and require zero live git-backed origin drift. In P3 run `Test-P3CoordinationPolicy.ps1` and `Test-P3Control.ps1`; reject MCP0 BUSY authority, five-minute stale takeover, `BUSY_IS_ONLY_COLLISION_CONTROL`, `collision_control='BUSY'`, or any second ownership database. If there is drift, repair source + propagation + repo-local enforcement/CI, not workers. Do not stop until the fixes are merged and both the remote audit and P3 invariant tests pass. Report exact receipts.
