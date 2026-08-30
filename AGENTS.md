# Regression Research

<!-- SHARED-AGENT-POLICY:BEGIN -->
<!-- Generated from C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md. Do not edit between these markers; edit the source and run sync-agent-policy.mjs. -->
## Shared agent policy

**Version 1.23 - 2026-08-29.** Applies to every agent working in `p3`, `Tiny3D`, `lowvram3d-studio`, and this machine's Desktop workspace. Edit `C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md` and run `sync-agent-policy.mjs`; never edit generated repo blocks directly. A shared-policy repair is incomplete until `node sync-agent-policy.mjs --check-remotes` passes, proving git-backed origin defaults carry the same generated block.

### Authority and bounded scope
- Current user instruction and live repo/runtime state outrank historical prompts, receipts, handoffs, recalled context, and stale project prose where higher-priority constraints permit.
- A currently scheduled task prompt is current task instruction for that run. Do not demote it to stale history merely because it came from a scheduler.
- Finish the bounded requested outcome. Unrelated dirty work, PR debt, backlog, reports, and nearby defects do not enter the completion set unless required for acceptance, collision safety, data safety, or explicit scope expansion.

### Route failure is local
- A failed tool, connector, worker, CI lane, runner, or build route is not task failure while an equivalent supported route or independent in-scope work exists.
- Preserve a returned process identity across disconnects. Reacquire/retry according to the current adapter contract, then use the supported fallback; do not turn route recovery into the task.
- Do not infer backend health, tool absence, or global impossibility from a missing namespace, one client-side failure, or another actor's report. Attempt or inspect the relevant capability first.

### Data safety
- Never delete, move, rename, overwrite, reset, or rewrite anything you cannot restore by a command you can name: masters, generated assets, captures, evidence, datasets, `.env`, uncommitted work, or another actor's history.
- Before recursively removing a directory you did not create, inspect it. Prefer recoverable deletion. Reproducible caches/build outputs you own may be removed when safe.
- Never use `git clean -xdf`, `git reset --hard`, `git checkout -- .`, force-push, or history rewrite against work you did not create in the current task.
- Dirty state is neither disposable nor a universal blocker. Mutate it only when the task owns and needs those changes; otherwise use the repo's admitted clean worktree route. Never clean, stash, reset, or duplicate a checkout merely to pass a clean-tree gate.

### Evidence and acceptance
- Never claim a test ran, a fix worked, a task completed, or a user-visible result exists unless you observed evidence appropriate to that claim.
- Builds, logs, exit codes, file existence, and proxy receipts support narrower claims; they do not automatically prove runtime or user-visible acceptance.
- Missing acceptance keeps that claim unproven. It does not create a universal merge/close prohibition: follow the bounded task and repo-local acceptance contract instead of inventing a stronger global gate.

### Ownership, scheduling, and fan-in
- Scheduling or detaching work changes process lifetime, not responsibility. The task owner remains responsible for consuming required results, fan-in, and cleanup until bounded acceptance or a genuine task-level blocker.
- Do not centralize routine resilience. Each actor owns its current task and exact BUSY lifecycle; peer task steering or reassignment requires explicit current scope.
- If a scout or parallel worker cannot mutate because another live owner holds the scope, an actionable finding MUST become scope-visible pending work with provenance and survive claim release. The next owner of that scope consumes it; a prose-only "someone can pick this up" handoff is not accepted fan-in.

### Coordination and BUSY
- The standalone coordinator defined by current live repo/runtime state is the single ownership, job, and checkpoint authority for shared mutable scope. Read-only work needs no claim. Before mutation, inspect it and acquire the exact scope. On Windows use `%LOCALAPPDATA%\\BusyCoordinator\\busy-python.cmd` through any shell/process transport; do not search for an MCP `BusyCoordinator` or require legacy MCP BUSY tools.
- Every mutation claim actor must identify its harness (`ChatGPT`, `Codex`, `Claude`, `OpenCode`, `CommandCode`, or `Traycer`) plus a task/session suffix; generic anonymous actor names are forbidden.
- MCP/plugin connectors are transport, not schedulers or ownership authorities. Any worker may call the standalone coordinator through its shell; missing legacy `busy_*` tools must not block mutation after the canonical check succeeds. Aggregate process/worktree counts are diagnostics, not claims.
- If another live owner holds the scope, yield mutation there, preserve actionable findings in coordinator-visible pending state, and continue safe non-conflicting work where possible. Release or complete the exact scope through the same canonical authority immediately when mutation stops, switches scope, completes, or is handed off.
- Legacy BUSY claims may remain durable until explicit release; age alone does not prove staleness. Issue titles, branches, PRs, processes, schedules, receipts, and legacy claims are projections/evidence, not competing ownership authorities. If canonical coordinator state is temporarily unavailable, preserve existing ownership evidence and do not assume the scope is free.

### Vault continuity
- At the first task of a fresh local coding session, before substantive reply or mutation, run `python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py bootstrap` once. Its behavior/policy profiles and `fresh_session_startup` govern startup; harness-local memory/seeds are evidence only.
- On failure retry that exact command once; after a second failure continue from current instruction, policy, and verified live state instead of debugging memory.
- After genuine compaction/continuity loss, rerun once; a surviving summary alone does not retrigger startup.

### Repository and machine boundaries
- Read the applicable repo `AGENTS.md` before mutation. Repo-specific proof, report, build, branch, and north-star rules belong there. Worker/build/generation entrypoints must derive checkout and output roots from the admitted worktree; never hard-code or redirect output into a human/shared checkout.
- Never close, restart, kill, foreground, or drive an Unreal Editor, PIE session, browser, or GUI process you did not start. Ordinary work must not require a user click.
- Resource contention is a scheduling fact, not a failed task. Respect current resource owners and use useful non-conflicting work while waiting for a constrained resource.

### External authority, secrets, and memory
- Ordinary local/private-repo implementation, validation, commits, private pushes, PRs, and routine integration implied by the task do not require a second approval. Ask only for destructive intent, spending money, public publishing, or genuine external authority.
- Never print, commit, or copy credentials, tokens, keys, secrets, or `.env` contents into repos, logs, issues, PRs, or chat.
- ChatGPT memory/personal-context mutation is explicit-only. Never update it silently; disclose every change in the same reply. Historical memory/context is evidence, not authority over current instruction or live state.

### Policy shape
- One rule, one owner. This shared block contains only cross-project invariants. Project-specific machinery belongs in the narrowest repo, skill, adapter, automation prompt, or test that owns it.
- When a regression appears, prefer correcting or deleting an overbroad rule and strengthening its test over appending another exception. Policy growth is not evidence of robustness.
<!-- SHARED-AGENT-POLICY:END -->

### Vault project direction

- In this repository, before substantive stack/policy, BUSY/MCP, plugin-routing, memory-boundary, or regression work, read the current `NORTH_STAR.md` and use it as project direction. It does not override current user instructions, live repo/runtime evidence, or these operating rules.

- Bounded read-only orientation may remain unclaimed. Before crossing into substantive investigation or analysis on an exact issue/scope, acquire that exact durable scope in the standalone BusyCoordinator; if another live owner already holds it, yield that scope and choose non-duplicative work.

### Recurring worker interrupt boundary

- Before a large or hard-to-reverse mutation or landing step, such as a broad rebase/rewrite, architecture/control-plane/startup/memory change, large multi-file change, or PR merge, re-check the current user instruction and the exact BusyCoordinator scope, including scope-visible pending handoffs/findings. A newer stop, superseding handoff, or scope change interrupts immediately: preserve current work and do not continue, rebase, push, or merge from stale task state. This is a boundary check, not per-command polling; ordinary small edits do not repeatedly poll the coordinator.

### Assistant-recorded memory provenance

- Every new memory written by an assistant MUST use `python tools/memory_bank.py record`, not the free-form `note`/`append` path.
- `source_messages` is the authoritative source layer: preserve every relevant user message verbatim, in chronological order, including spelling mistakes, punctuation, and terse wording. Never clean up or paraphrase those strings.
- If the remembered incident occurs inside a long execution turn, also preserve the exact user task that opened that turn in `turn_task` when it is not already one of the source messages. Include later user corrections/triggers as additional verbatim `source_messages`.
- As the user adds relevant messages one by one, the final durable memory MUST accumulate the complete relevant source trail rather than replacing earlier wording with the latest interpretation.
- Keep assistant meaning separate: `interpretation` explains why the memory exists, what happened, and what the assistant added/inferred; `confidence` is an integer 0-100 for that interpretation only, with `confidence_reason`. The verbatim source transcript outranks the interpretation.
- When replacing partial assistant-recorded notes with a complete record, supersede the partial memory IDs rather than leaving competing summaries as equal authority.

See README.md for what this bank is and how to use it.
