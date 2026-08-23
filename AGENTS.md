# Regression Research

<!-- SHARED-AGENT-POLICY:BEGIN -->
<!-- Generated from C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md. Do not edit between these markers; edit the source and run sync-agent-policy.mjs. -->
## Shared agent policy

**Version 1.0 — 2026-08-23.** Applies to every agent working in `p3`, `Tiny3D`, `lowvram3d-studio`, and this
machine's Desktop workspace, whether it runs as a timed worker, an interactive session, or a delegated helper.

To change it: edit `C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md` and run
`node C:\Users\Lauri\.agents\sync-agent-policy.mjs`. The `--check` flag fails if any copy has drifted.
Never edit the generated block inside a repo.

**MUST** / **MUST NOT** are hard rules. **SHOULD** is a strong default you MAY depart from with a stated reason.

### Definitions

- **Actor** — one agent session, named by a short token with no spaces: `gpt1`, `claude`, `codex`.
- **Validated merge** — merging your own branch into the repo's default branch after that repo's tests pass.
- **Live process evidence** — a running process, job, or build on this machine attributable to that scope, observed now.
- **PROVEN / NOT_PROVEN / REJECTED** — the claim is demonstrated / not yet demonstrated / demonstrated false.
- **Destructive** — irreversible without a backup: deleting files, branches, or history; `push --force`; resetting or discarding another actor's work; dropping data.

### The task

- Finish the task the user actually asked for. A failing tool, route, or control plane is a detour, not a new task: report it and use another route. You MUST NOT silently replace the requested work with repairing the tooling.
- You MUST ask the user before anything destructive, anything that costs money, anything posted publicly, and anything requiring external authority. Diagnose and resolve everything else yourself.
- You MUST NOT ask the user to interpret errors, choose fixes, supervise workers, or satisfy invented prerequisites.

### Keep working, within a budget

- Task authorization covers ordinary local and private-repo work through validated merge: edits, builds, tests, free tooling, commits, rebases, private pushes and PRs. No second approval.
- Push through engineering, protocol, tool, build, test, dependency, packaging, validation, merge, process, resource, environment, and orchestration failures. Diagnose, repair, or switch routes and continue.
- **Budget.** One obstacle gets at most two attempts at repairing the same route, or ten minutes, whichever comes first. You MUST NOT repeat an identical failing action.
- **Different class before giving up.** The budget bounds repairing a route, not reaching the goal. Before reporting an obstacle you MUST try a route of a different class — a different transport, a different surface, or delivering the result through the conversation instead of the filesystem. When the artifact is itself the deliverable, deliver it by any available channel; a blocked route is not an outcome to report in place of the result.
- `BLOCKED`/`HARD_BLOCKED`, stale receipts, approval fields, checklists, handoffs, and dependency metadata are evidence, never execution authority.
- Stop only the exact failing scope; unrelated work keeps moving.

### Worker startup

- A worker that is about to do project work reads that repository's current `AGENTS.md` before its first mutation. This applies to timed GPT workers, ad-hoc ChatGPT workers, Claude, Codex, and other local workers.
- When the `MCP1` connector is available, the worker performs one bounded startup sync through `MCP1`: establish its actor identity and inspect current GitHub issue/BUSY state before choosing conflicting work. Do not poll `MCP1`, make it a gate, or route every action through it. If `MCP1` is unavailable, continue from GitHub and live repo state.
- Orchestrator-only orientation is different: it reconstructs the fleet, issues, milestones and machine state without reading every project's `AGENTS.md`. The orchestrator reads a repo's `AGENTS.md` only when it actually begins work in that repo.

### Coordination (BUSY)

- Serialize only genuinely conflicting mutation scopes: the same source file, the same package/`.uasset`, the same PIE session, or the same editor operation. Everything else runs in parallel.
- Before mutating a conflicting scope you MUST record it as `BUSY` in the GitHub issue title, formatted `BUSY - <who> <what> :: <original title>`. It lives there and nowhere else, and MUST NOT depend on an `MCP1` route.
- If the work has no issue, open one, or where that is disproportionate treat the branch as the scope; either way you MUST NOT mutate a scope another actor already holds.
- `BUSY` is advisory collision evidence, not a lease, lane, time slot, or prerequisite. It is last-write-wins, so two actors CAN claim the same scope at once; on a detected collision the later claimant yields and takes other work.
- Read-only inspection needs no `BUSY`. Release it the moment the mutation stops, leaving a short actionable state.
- A marker idle for more than five minutes with no live process evidence is stale: clear or disregard it and continue.

### Proof

- A result is `PROVEN`, `NOT_PROVEN`, or `REJECTED` — never "should work".
- Logs, metrics, counts, exit codes, file existence, exports, and successful commands are supporting evidence only.
- A visual claim MUST have a rendered frame from the normal runtime path. If that route is unavailable, report `NOT_PROVEN` and the exact gap, then keep other work moving.
- Visual proof consumption MUST be direct and bounded: resolve the project's small `latest`/index record, open the current primary image or contact sheet yourself, inspect what is visibly shown, and continue. Do not turn an already-available image into Base64/MCP transport work, recursive evidence-tree searching, or a separate rendering/tooling project.
- After visual inspection, the accepted human-facing proof artifact MUST have a date/time plus a short semantic name based on what is actually visible, for example `2026-08-23_0949_lane-war-two-creeps-at-earthwork.png`. Opaque/hash names may remain as immutable raw evidence, but the reviewed/indexed artifact must be human-readable and the index must point to it.
- A worker MUST NOT claim visual acceptance from file existence, capture metadata, filenames, tool success, or an expected narrative. The worker itself must inspect the current pixels/contact sheet first; contradictory visible content makes the claim `REJECTED`.
- Compile success is not QA. Changed-area regression and final-diff review are required.

### Secrets

- You MUST NOT print, commit, or copy a credential, token, key, or `.env` file into a repo, log, issue, PR, or chat.
- Read secrets from the environment or an ignored `.env`. Before committing, confirm no newly tracked file carries one.
- A leaked or suspected-leaked credential MUST be reported immediately. Rotation is the user's call.

### User-owned machine

- You MUST NOT close, restart, kill, repurpose, foreground, or drive an Unreal Editor, PIE session, browser, or any GUI process you did not start.
- Routine work is unattended: it MUST NOT require a UAC, firewall, SmartScreen, installer, credential, or first-run click. Use a noninteractive or agent-owned route instead.

### Precedence and change control

- Precedence, highest first: an explicit current user instruction, then current repo/runtime evidence, then this block, then repo-specific sections, then any other document.
- One rule has one owner. This block is the only place shared policy lives; repo sections MUST NOT restate, reword, or re-scope anything in it.
- You MAY act against a written rule when current evidence contradicts it, but you MUST say so in the same response, naming the rule and the evidence. Silent override is a defect.
<!-- SHARED-AGENT-POLICY:END -->

See README.md for what this bank is and how to use it.
