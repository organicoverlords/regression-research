# Agent rules authority centralization — incident and correction

## Incident
The prior operating-policy architecture copied a generated shared block into many `AGENTS.md`/tool files and also allowed repo/tool-local policy bodies. In live use this repeatedly turned policy propagation, stale generated blocks, merge conflicts, and metadata synchronization into engineering work. During the 2026-09-03/04 cutover, live inspection also found stale local MCP policy that still described retired 3003/Tailscale/6K/MCP-BUSY behavior and timeline code that privileged `origin/main` as the direct-mutation/current-history baseline. Those are concrete recurrence traps: a future worker could have followed stale local prose or treated the human validation branch as worker authority.

## Correction
- Created private canonical rule repository `organicoverlords/agent-rules`. Its default branch is `rules/live`; it has no `main` branch.
- Canonical rules are `RULES.md` plus files under `contexts/`. Local `AGENTS.md`, `CLAUDE.md`, and equivalent files are navigation pointers only and are explicitly not policy authorities.
- Retired the local generated-policy source/sync/audit/test files under `%USERPROFILE%\.agents`.
- Central rules require: rules -> Stack Atlas -> latest 20 memory saves -> recent all-branch Git history -> work; live repo/runtime proof outranks reports/status projections.
- Product `main`/`master`/`dev`/`develop` are protected human/integration branches. Agent mutation requires a clean named work/convergence branch; agents do not use product main as the routine work baseline.
- Repo chronology now uses one bounded `git log --all` stream. No mainline quota or `MAINLINE`/`LANE` hierarchy remains in the live timeline projection.
- North Star is product direction and can generate obvious missing feature work. Swarm performance is useful delivered output, not waiting/report/test churn.
- Proof/capture and artifact-transfer rules are centralized: one canonical proof path per product and user-facing media is complete only after exact-byte verified delivery.

## Live evidence / validation
- `organicoverlords/agent-rules` remote default: `rules/live`, private repository. Canonical live commit after MCP context centralization: `648c9db`.
- Atlas/source/bootstrap focused regression: `26 passed, 27 subtests passed`.
- Named-work-branch mutation-admission regression: `4 passed`.
- All-branch repo chronology + orientation regression: `9 passed`.
- Stack Atlas inventory parses as JSON and renders `agent_rules` + `repo_rule_pointer`; obsolete `shared_policy` / `repo_agents` live components are removed in this candidate.
- Changelog checker on this Vault version makes timeline edits optional, so this correction deliberately does not touch `CHANGELOG.md` or `README.md`.

## Boundaries
This report is evidence/history, not current truth. Current truth remains the canonical `agent-rules` repo, exact live Git/runtime state, North Star direction, and exact user instruction. The Vault migration is on named branch `chatgpt/agent-rules-authority-20260904`; no product or Vault `main` is advanced by this worker.

## Follow-up trap: memory writer advanced protected `main`
While recording the user-authored correction through the required `memory_bank.py record` path, the live `memory_git_sync.py` revealed a hard-coded `BRANCH = "main"` and automatically published commit `a04cdb11551fe3e5193a4857b6dfe6cb579d300c` (`memory: add mem-20260904-1bfc720f`) directly to `refs/heads/main`. That commit changed only `memory/memory-bank.jsonl` and had parent `87d59974caa0091036eaf3a04e57c533c83460a2`.

Before a safe lease-guarded restoration could be executed, `main` advanced through the independent convergence merge `c6c17b6985859b26399a5cb0484bbb59eef023d4` (`Converge YAGNI stack simplification (#452)`). Because `a04cdb1` is an ancestor of that newer merge, rewriting `main` would rewrite foreign/newer work and was rejected. The accidental memory commit was instead preserved exactly on dedicated remote branch `memory/live`, and newer `main` was left untouched.

The repair candidate changes `memory_git_sync.py` to `BRANCH = "memory/live"`, adds a fail-closed guard rejecting `main`, `master`, `dev`, or `develop`, and updates its alignment fixture to track the dedicated memory branch. Validation: `8 passed`; a live non-publishing sync resolved `memory/live` at exact `a04cdb1` with `pending_push=0`, `pushed=0`.

The current private-repository/account tier does not expose GitHub branch protection/rulesets (API returned HTTP 403 requiring GitHub Pro or public repository). To close the immediate live gap without mutating another worker's dirty Vault checkout, the shared Vault Git directory now has `.git/hooks/pre-push`, which rejects direct pushes to `refs/heads/main|master|dev|develop` and allows named branches. Manual hook validation returned reject exit 1 for `main` and allow exit 0 for `chatgpt/test`. This is an enforcement boundary for the canonical branch rule, not a second policy authority; the rule text remains only in `agent-rules`.

## Final five-repo convergence candidate — protected branches pending user approval
Live remote verification at 2026-09-04 01:39 EEST confirmed the canonical rules authority at `organicoverlords/agent-rules` `rules/live` = `ad93f5c1a86ab88d536bf4bf7cc1ab24228fed4e` and exact pointer/migration candidates:

- P3 `chatgpt/agent-rules-pointer-20260904` = `f246ff7a32c4e9d4b8565f5e4e64fadbf72f4da3`; protected `main` = `fa5a70b58120cb3b3da61587e486bbab350a646c`.
- Tiny3D `chatgpt/agent-rules-pointer-20260904` = `333ef57aa313cf0431d9845f8689e6b00ede113c`; protected `main` = `4a60114554abd46f0cfe49c7c2ab74f8451e5374`.
- LowVRAM `chatgpt/agent-rules-pointer-20260904` = `e838e818494bb70c95366aabac3c8e4f960e539f`; protected `main` = `defbdd7e4a00597b32309b0a64d4063862302b84`.
- MCP `chatgpt/agent-rules-pointer-20260904` = `45005d7c9645e958af22d7712944fc0bf2b18c88`; protected `master` = `ce948bfef93ba118887abd7fa340ce0b22319197`.
- Vault remote candidate `chatgpt/agent-rules-authority-20260904` = `bffa5f1fbdb2651624050f55ec44953f89cc3812`; protected Vault `main` = `98a0ed3f1b976b5929861c9739d3107f15e47898`. The local migration worktree also contains later unpushed convergence commits and concurrent dirty work from another actor; those are explicitly not treated as delivered candidate evidence and are not published by this task.

All protected product/integration branches remain outside this cutover. They still carry the old local policy until the user explicitly approves advancing the converged candidates. This is deliberate: the agent work is prepared and evidenced on named branches first; protected human-validation branches are not silently updated by workers.
