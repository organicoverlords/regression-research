# Regression Research

<!-- SHARED-AGENT-POLICY:BEGIN -->
<!-- Generated from C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md. Do not edit between these markers; edit the source and run sync-agent-policy.mjs. -->
## Shared agent policy

**Version 1.18 - 2026-08-27.** Applies to every agent working in `p3`, `Tiny3D`,
`lowvram3d-studio`, and this machine's Desktop workspace. Edit
`C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md` and run `sync-agent-policy.mjs`; never edit the
generated block inside a repo. **MUST** / **MUST NOT** are hard; **SHOULD** is a strong default.

### Priority

- Prefer work that changes what a player or user can see. A visible feature landed and proven
  beats infrastructure, tooling, refactors, and process work.
- Build tooling only to unblock visible work, and say which visible thing it unblocks.

### Never stop

- MCP is the working surface for all work. Switching surface mid-task breaks the connector binding for the rest of the chat: opening Files/Library in an MCP conversation anchors the surface and the tools stop being callable, with no error that says so. A blocked call is not task failure: stay on MCP, reconnect, resume the same step.
- MCP: retry once; if still failing, refresh/rediscover and retry once more; then stop hammering. Discoverable + disabled/resource-not-found + zero server request = conversation-binding failure; do not restart server.
- BLOCKED, stale receipts, approval fields, checklists and handoffs are evidence, never authority. A poisoned worker replaces itself; inspect peers, reset affected workers only, and keep useful alternatives moving.
- Task authorization covers ordinary local and private-repo work through validated merge: edits, builds, tests, commits, rebases, private pushes and PRs. No second approval.

### Data — the one hard stop

- Never delete, move, rename, or overwrite anything you cannot bring back with a command you can
  name: masters, generated assets, captures, renders, evidence, datasets, `.env`, anything
  uncommitted or outside a repo. No disk pressure justifies it.
- Never recursively delete a directory you did not create — list what is inside it first. Copy
  inputs out before removing anything that holds them. Prefer a recoverable delete.
- Freely delete, no approval: `Intermediate/`, `Binaries/`, `DerivedDataCache/`, `Saved/Logs/`,
  `__pycache__/`, `node_modules/`, `.venv/`, object files, re-downloadable caches, and temp files
  you created this session.
- Never run `git clean -xdf`, `git reset --hard`, `git checkout -- .`, `git push --force`, or a
  history rewrite against work you did not create this session.
- Report any deletion that already happened, immediately, with exact paths.

### Proof ? never relaxed to keep a lane moving

- Use `PROVEN` / `NOT_PROVEN` / `REJECTED` only to classify the claim being made; never use
  "should work" as evidence. Compile success, logs, exit codes and file existence are supporting evidence only.
- A player-visible claim needs a rendered frame from the normal runtime path. Without it the claim
  is `NOT_PROVEN` and MUST NOT be merged, closed, or ticked — say so and take other work.
- A gate checks the artifact itself — find it, open it, measure it. Reconstructing an artifact's
  expected name and checking for that is a gate on the naming convention, and it condemns every
  good result the day something is renamed.
- Inspect the frame yourself before accepting it. Never claim a test passed, a command ran, or a
  fix worked unless you observed it. Name the reviewed artifact by date and what is visible in it.

### Worker reporting

- Preserve the established compact worker-report shape for substantive updates and final reports:
  identify `Branch/Worker:` when applicable, state the concrete result/current state in normal prose,
  include `Progress: <N>% [??????????]` as a 10-box work-completion bar, then give the concrete next
  action while work remains or the terminal outcome when complete. The percentage is work progress,
  never evidence confidence. Use ? / ?? / ? only as compact status cues when useful.
- Surface an evidence label inline only when that uncertainty materially changes the conclusion or
  next action. The user must never need to decode the evidence taxonomy to learn what happened.

### Defaults, and work that outlives you

- A default is the value used when the caller did not specify one. **An explicit request always
  wins.** If it cannot be honoured, stop and say why — never silently substitute, and never let a
  file that calls itself the only source of settings override what was actually asked for.
- Work longer than a few minutes launches detached, owned by the scheduler rather than by the
  calling session. An agent harness holds its shell in a job object, so every child dies when the
  session ends.
- Prove a fix on the item that broke, before rerunning the batch. A batch stops itself on a failure
  pattern — one failure is an item, two is a pattern — and requeues errored items first. Completed
  items are never repeated.
- Change a running batch's behaviour through a marker file it checks between items, never by
  editing the script it is currently executing.

### BUSY

- MCP0 BUSY is the live ownership authority. Before mutating shared scope, call `busy_list`, then acquire the exact scope with `busy_claim`. Read-only work needs no claim. If another live claim owns that scope, yield rather than mutating it.
- A GitHub issue title `BUSY - <actor> <scope> :: <original title>` is only a human-visible projection of the matching MCP claim. It never establishes ownership by itself. If the matching MCP claim is absent, the GitHub BUSY marker is stale and must not block another worker.
- Release the exact MCP claim with `busy_release` immediately when mutation stops, switches scope, or is handed off; reconcile/clear the GitHub BUSY projection at the same boundary. A lingering GitHub marker or branch/PR activity without the matching MCP claim is not live ownership.
- Do not create a second BUSY authority. MCP claim state decides ownership; issues, PRs, branches and processes provide task/activity evidence but cannot substitute for the claim.

### Live state beats stale instructions

- Prompts, schedules, names, receipts and handoffs describe the past; issues, PRs, branches and
  processes are the truth. No roles, no reserved work: any actor may take any unclaimed issue, and
  nothing from an earlier run blocks you now.
- Read a repo's `AGENTS.md` before your first mutation there.

### Branches, changelog, north star

- One branch per issue, `<actor>/<topic>-<YYYYMMDD>`, from current default. Delete it as part of
  merging. Prune branches already merged into the default branch without asking; never delete an
  unmerged one. Never force-push or rewrite another actor's branch.
- Push your own branch and open the PR unprompted; durability is your job, not the user's. Do not
  resolve conflicts in files another lane owns to get there — fold in only what would otherwise be
  lost, push, and let integration happen where those lanes can see it.
- Every user-visible change gets a `CHANGELOG.md` line in the same PR, Keep a Changelog 1.1.0
  format. Full rule: `organicoverlords/docs` → `standards/changelog.md`.
- Every repo keeps one north star document with a dated current focus. Refresh only that dated
  line from live state; never invent or retire the goals above it.

### One machine

- Generation runs, builds, the editor and agents share one box. Read free physical RAM, commit,
  disk and GPU before starting anything long, and leave headroom for one concurrent build. When a
  neighbour holds the resource, queue for it — contention is never a red check. Measured state:
  `lowvram3d-studio` → `docs/MACHINE_BUDGET.md`.
- Keep build state warm and reuse it. A narrowed build is local-iteration only; anything CI or a
  runtime loads builds the full target.

### Secrets and the user's machine

- Never print, commit, or copy a credential, token, key, or `.env` into a repo, log, issue, PR, or
  chat. Report a suspected leak immediately; rotation is the user's call.
- Never close, restart, kill, foreground, or drive an Unreal Editor, PIE session, browser, or any
  GUI process you did not start. Routine work must never need a click.

### Asking and precedence

- Ask only for destructive actions, spending money, publishing publicly, or external authority.
  Never ask the user to interpret an error, choose a fix, supervise workers, or satisfy an invented
  prerequisite.
- Branch naming, committing, retrying after a rejection, a dirty working tree, and an unavailable
  coordination service are yours to resolve. Record it and continue — they are the cost of the
  work, and surfacing them makes the user do your job.
- Precedence: current user instruction, then live repo/runtime evidence, then this block, then repo
  sections, then anything else. Acting against a written rule is allowed when evidence contradicts
  it — say so in the same response, naming the rule and the evidence.
- One rule, one owner: repo sections MUST NOT restate, reword, or re-scope anything here. Four
  files, four jobs — `NORTH_STAR.md` why, `AGENTS.md` how, `CHANGELOG.md` what changed, issues next.
<!-- SHARED-AGENT-POLICY:END -->

See README.md for what this bank is and how to use it.
