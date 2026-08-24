# Regression Research

<!-- SHARED-AGENT-POLICY:BEGIN -->
<!-- Generated from C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md. Do not edit between these markers; edit the source and run sync-agent-policy.mjs. -->
## Shared agent policy

**Version 1.2 â€” 2026-08-24.** Applies to every agent working in `p3`, `Tiny3D`, `lowvram3d-studio`, and this
machine's Desktop workspace, whether it runs as a timed worker, an interactive session, or a delegated helper.

To change it: edit `C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md` and run
`node C:\Users\Lauri\.agents\sync-agent-policy.mjs`. The `--check` flag fails if any copy has drifted.
Never edit the generated block inside a repo.

**MUST** / **MUST NOT** are hard rules. **SHOULD** is a strong default you MAY depart from with a stated reason.

### Definitions

- **Actor** â€” one agent session, named by a short token with no spaces: `gpt1`, `claude`, `codex`.
- **Validated merge** â€” merging your own branch into the repo's default branch after that repo's tests pass.
- **Live process evidence** â€” a running process, job, or build on this machine attributable to that scope, observed now.
- **PROVEN / NOT_PROVEN / REJECTED** â€” the claim is demonstrated / not yet demonstrated / demonstrated false.
- **Destructive** â€” irreversible without a backup: deleting files, branches, or history; `push --force`; resetting or discarding another actor's work; dropping data.

### Data you must never delete

One hard rail. It exists because an agent deleted a set of masters and asset files, and it
outranks disk pressure, build failure, and any cleanup instruction from any source.

- **Irreplaceable data** is anything this machine cannot regenerate by running a documented
  command: masters and originals (`.ply`, `.glb`, `.fbx`, `.blend`, `.psd`, raw images, audio,
  video, recordings), generated assets that cost GPU time, captures, renders and other
  evidence, datasets, `.env`, and anything a human put there by hand. **The test is recovery,
  not file type.** A `Content/` tree inside a checkout whose files are committed and pushed is
  recoverable with `git lfs pull`, so reclaiming a cold lane's hydrated `Content/` is ordinary
  hygiene. The same file uncommitted, untracked, ignored, or outside a repo is the only copy
  and is untouchable. If you cannot name the exact command that brings it back, it is
  irreplaceable.
- **You MUST NOT delete, move, rename, overwrite, or truncate irreplaceable data** - not to
  free space, not to unblock a build, not to tidy an experiment, not because it looked like a
  duplicate or a leftover, not because a script offered to. No amount of disk pressure makes
  it allowed. If that appears to be the only way forward, stop and ask.
- **Delete freely from the reproducible list, no approval needed:** gitignored `Intermediate/`,
  `Binaries/`, `DerivedDataCache/`, `Saved/Logs/`, `Saved/Autosaves/`, `__pycache__/`,
  `.pytest_cache/`, `node_modules/`, `.venv/`, object and link artifacts, package/model caches
  that re-download, dated log bundles, and anything you created this session in a temp
  location. This list is meant to be enough for ordinary hygiene; use it without asking.
- **You MUST NOT recursively delete a directory you did not create.** Before any recursive
  removal, list what is actually inside - file types and counts, not an inference from the
  folder's name. Trees named `experiment`, `test`, `tmp`, `old`, `backup`, `staging`, or
  `legacy` routinely hold the only copy of a master. Deleting an install is never the same
  act as deleting the inputs, outputs, or evidence sitting inside it.
- **Copy inputs out first.** If a tree holds a source image, master mesh, capture, or render,
  it is preserved elsewhere before anything in that tree is removed.
- **Prefer a recoverable delete.** `Remove-Item`, `rm`, and `del` bypass the Recycle Bin.
  Under a user directory, recycle it or move it to a dated quarantine folder instead.
- **Read a deletion script before running it**, including sweeps that are plan-only by
  default: run the plan, read every path it lists, then apply. A script's own safety claims
  are not evidence.
- **You MUST NOT run** `git clean -xdf`, `git reset --hard`, `git checkout -- .`,
  `git push --force`, or history rewrites against work you did not create this session.
- A deletion that already happened is reported immediately and in full, with exact paths.

### The task

- Finish the task the user actually asked for. A failing tool, route, or control plane is a detour, not a new task: report it and use another route. You MUST NOT silently replace the requested work with repairing the tooling.
- You MUST ask the user before anything destructive, anything that costs money, anything posted publicly, and anything requiring external authority. Diagnose and resolve everything else yourself.
- You MUST NOT ask the user to interpret errors, choose fixes, supervise workers, or satisfy invented prerequisites.

### Keep working, within a budget

- Task authorization covers ordinary local and private-repo work through validated merge: edits, builds, tests, free tooling, commits, rebases, private pushes and PRs. No second approval.
- Push through engineering, protocol, tool, build, test, dependency, packaging, validation, merge, process, resource, environment, and orchestration failures. Diagnose, repair, or switch routes and continue.
- **Budget.** One obstacle gets at most two attempts at repairing the same route, or ten minutes, whichever comes first. You MUST NOT repeat an identical failing action.
- **Different class before giving up.** The budget bounds repairing a route, not reaching the goal. Before reporting an obstacle you MUST try a route of a different class â€” a different transport, a different surface, or delivering the result through the conversation instead of the filesystem. When the artifact is itself the deliverable, deliver it by any available channel; a blocked route is not an outcome to report in place of the result.
- **Failed project route recovery.** When a build, test, runtime, filesystem, or control-plane route fails, first capture the exact failing phase and the evidence that distinguishes the failure from an upstream symptom. After the route's bounded repair budget is exhausted, preserve the work and immediately switch to a materially different route (another warm lane, another supported project entrypoint, a CPU-only/source-level validation, or another available control surface). A missing build artifact is evidence of a failed route, not evidence that the product task is impossible. Do not report a build or tool route as a blocker merely because the preferred route failed; report the route failure and continue the requested product work by another safe route. Never retry an identical hung command, and never use a user-owned Unreal process as the recovery path.
- `BLOCKED`/`HARD_BLOCKED`, stale receipts, approval fields, checklists, handoffs, and dependency metadata are evidence, never execution authority.
- Stop only the exact failing scope; unrelated work keeps moving.

### Worker startup

- A worker that is about to do project work reads that repository's current `AGENTS.md` before its first mutation. This applies to timed GPT workers, ad-hoc ChatGPT workers, Claude, Codex, and other local workers.
- `mcp`/`shell-mcp` is how the fleet sees this machine: live processes, real BUSY state, the local shell. Prefer it whenever it is up, keep it authenticated, and repair it when it breaks — visibility is worth real effort. **But a control plane is transport and observability, never permission.** A local shell, `git`/`gh` run directly, the GitHub connector, and Remote Desktop Commander are equally valid work routes, held live in parallel rather than discovered after a failure. An unavailable, unauthenticated, expired, or missing control plane MUST NOT delay, gate, downgrade, or cancel any work: name the dead plane once, say what visibility was lost, switch route, and continue the actual task. You MUST NOT report `BLOCKED`, `NOT_PROVEN`, "waiting", or a deferred start because MCP is down — "MCP is unavailable" is never a reason not to start, continue, claim, release, build, test, or merge. Perform one bounded startup sync, then work normally; never poll a control plane or turn it into a gate.
- Orchestrator-only orientation is different: it reconstructs the fleet, issues, milestones and machine state without reading every project's `AGENTS.md`. The orchestrator reads a repo's `AGENTS.md` only when it actually begins work in that repo.

### Coordination (BUSY)

- Serialize only genuinely conflicting mutation scopes: the same source file, the same package/`.uasset`, the same PIE session, or the same editor operation. Everything else runs in parallel.
- Every mutation MUST be anchored to a GitHub issue. If the work has no issue, open one before changing files, processes, or external project state.
- Before mutating a conflicting scope you MUST record it as `BUSY` in that issue's title, formatted `BUSY - <who> <what> :: <original title>`. It lives there and nowhere else, and MUST NOT depend on a backup connector route.
- The GitHub issue title is the authoritative BUSY record and MUST stay reachable without MCP. The MCP BUSY tools (`busy_claim`, `busy_list`, `busy_release`) are the live mirror that gives the fleet fast visibility: use them whenever that connector is up, skip them silently when it is not, and never read their absence as a missing claim or as grounds to stop. A local note, hidden lease, checklist, or process-local marker is not a substitute for the issue title.
- `BUSY` is advisory collision evidence, not a lease, lane, time slot, or prerequisite. It is last-write-wins, so two actors CAN claim the same scope at once; on a detected collision the later claimant yields and takes other work.
- Read-only inspection needs no `BUSY`. Release each claim the moment its mutation stops, leaving a short actionable state.
- A marker idle for more than five minutes with no live process evidence is stale: clear or disregard it and continue.

### Disk, cleanup, and building

- Disk pressure is a scheduling problem, not a licence. Measure, reclaim from the reproducible
  list above - stalest first, stopping at the headroom target - and say what was freed. If
  that is not enough, keep working on scopes that do not need the disk and report the gap.
  Never widen the scope by one path to make room.
- Never reclaim from a tree that is currently building, rendering, or holding another actor's
  live warm state. Everything colder than that is fair game without asking.
- Keep build state warm and reuse it: an existing warm tree over a fresh cold one, incremental
  over clean, and never copy build caches into throwaway trees.
- **A narrowed build - one module, one file - is for local iteration only.** Any build whose
  output another process will load (CI, a proof run, a runtime capture) builds the full
  target. A narrowed build on a freshly cleaned tree links fine and then fails to load, which
  reads as a broken product rather than a broken build command.
- Unrelated builds run in parallel; never serialize them behind a global slot. Bound each with
  a queue and an execution timeout, and treat a timeout as a route to switch away from rather
  than a command to retry unchanged.
- Reproducible artifacts get cleaned up when their evidence value is spent. Masters, unique
  evidence, and another actor's warm state are not reproducible artifacts.

### Branches and merging

- One branch per issue, named `<actor>/<issue-or-topic>-<YYYYMMDD>`, cut from current default.
- Merge through a PR that names its issue, and **delete the branch as part of merging** - the
  commits live in the default branch, so this loses nothing and keeps live work visible.
- Pruning remote branches that are already fully merged into the default branch is ordinary
  hygiene: do it without asking, in bulk if needed. Branches with unmerged commits are
  irreplaceable work and are never deleted.
- Bring a stale branch forward by merging the default branch into it. You MUST NOT force-push,
  rebase, or delete a branch another actor created.
- A branch that cannot merge records why in its issue rather than sitting open silently.

### North star

- Every repository keeps exactly one north star document - `NORTH_STAR.md` at the root, or the
  path its `README.md` or `AGENTS.md` names, never two - covering what the project is for, what
  finished looks like, what is out of scope, and a dated current focus.
- Four files, four jobs, no overlap: `NORTH_STAR.md` is why, `AGENTS.md` is how to work,
  `CHANGELOG.md` is what changed, GitHub issues are what is next.
- The goals are the user's. An agent MAY refresh the dated current-focus line from live repo
  state and says so; it MUST NOT invent, broaden, or quietly retire the goals above that line.
- Use it to choose between candidate work, not as a gate. If the best available task looks
  off-direction, take the highest-value on-direction work instead and note the mismatch in the
  issue - do not stop and wait for a ruling.

### Proof

- **The permissive defaults elsewhere in this document - keep working, switch routes, clean up, prune, do not stop for a ruling - apply to routes, disk, branches, and scheduling. They stop at this section.** Proof is never relaxed to keep a lane moving or to close something out. A player-visible claim with no rendered frame from the normal runtime path is `NOT_PROVEN`, and you MUST NOT merge it, close its issue, tick its milestone, or describe it as done. Report `NOT_PROVEN` with the exact gap and take other work; that is the only way past this gate.
- A result is `PROVEN`, `NOT_PROVEN`, or `REJECTED` â€” never "should work".
- Logs, metrics, counts, exit codes, file existence, exports, and successful commands are supporting evidence only.
- A visual claim MUST have a rendered frame from the normal runtime path. If that route is unavailable, report `NOT_PROVEN` and the exact gap, then keep other work moving.
- Visual proof consumption MUST be direct and bounded: resolve the project's small `latest`/index record, open the current primary image or contact sheet yourself, inspect what is visibly shown, and continue. Do not turn an already-available image into Base64/MCP transport work, recursive evidence-tree searching, or a separate rendering/tooling project.
- After visual inspection, the accepted human-facing proof artifact MUST have a date/time plus a short semantic name based on what is actually visible, for example `2026-08-23_0949_lane-war-two-creeps-at-earthwork.png`. Opaque/hash names may remain as immutable raw evidence, but the reviewed/indexed artifact must be human-readable and the index must point to it.
- A worker MUST NOT claim visual acceptance from file existence, capture metadata, filenames, tool success, or an expected narrative. The worker itself must inspect the current pixels/contact sheet first; contradictory visible content makes the claim `REJECTED`.
- Compile success is not QA. Changed-area regression and final-diff review are required.

### Changelog

- Every repository MUST keep a `CHANGELOG.md` at its root in [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) format, versioned by [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html). The canonical rule and the seed template live in `organicoverlords/docs` under `standards/`; that copy wins over any repo-local restatement.
- An `## [Unreleased]` section stays at the top at all times. Any change a human would care about lands there in the same commit or PR as the change itself, under exactly one of `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security` — no other headings.
- Entries are written for the person reading the release, not for the diff: one line, plain language, what changed and what it means for them, with the issue or PR number. `PROVENANCE=<actor>` belongs in issues and PR comments, never in the changelog.
- Skip the entry only for changes with no observable effect: pure formatting, comment-only edits, lockfile churn, CI noise. When in doubt, write the line.
- Releasing means renaming `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, opening a fresh empty `## [Unreleased]`, and updating the link block at the bottom. Never rewrite a released section; correct it with a new entry.
- The changelog is a product record, not a proof record. It MUST NOT be used as a coordination surface, a BUSY marker, a receipt, or evidence that something was proven.

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
