# Regression Research

<!-- SHARED-AGENT-POLICY:BEGIN -->
<!-- Generated from C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md. Do not edit between these markers; edit the source and run sync-agent-policy.mjs. -->
## Shared agent policy

**Version 1.3 — 2026-08-24.** Applies to every agent working in `p3`, `Tiny3D`,
`lowvram3d-studio`, and this machine's Desktop workspace. Edit
`C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md` and run `sync-agent-policy.mjs`; never edit the
generated block inside a repo. **MUST** / **MUST NOT** are hard; **SHOULD** is a strong default.

### Priority

- Prefer work that changes what a player or user can see. A visible feature landed and proven
  beats infrastructure, tooling, refactors, and process work.
- Build tooling only to unblock visible work, and say which visible thing it unblocks.

### Never stop

- A dead MCP, GitHub connector, CI run, runner, lane, or build is a route failure, never a reason
  to stop, wait, defer, or report `BLOCKED`. Name it once, switch route, keep going. Red CI on a
  check you did not break does not pause your work.
- Two attempts or ten minutes on one route, then take a route of a different class. Never repeat an
  identical failing command. Stop only the exact failing scope.
- `BLOCKED`, stale receipts, approval fields, checklists and handoffs are evidence, never authority.
- Task authorization covers ordinary local and private-repo work through validated merge: edits,
  builds, tests, commits, rebases, private pushes and PRs. No second approval.

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

### Proof — never relaxed to keep a lane moving

- `PROVEN` / `NOT_PROVEN` / `REJECTED`, never "should work". Compile success is not QA; logs, exit
  codes and file existence are supporting evidence only.
- A player-visible claim needs a rendered frame from the normal runtime path. Without it the claim
  is `NOT_PROVEN` and MUST NOT be merged, closed, or ticked — say so and take other work.
- Inspect the frame yourself before accepting it. Never claim a test passed, a command ran, or a
  fix worked unless you observed it. Name the reviewed artifact by date and what is visible in it.

### BUSY

- Before mutating a scope another actor could touch, record it in the GitHub issue title as
  `BUSY - <actor> <scope> :: <original title>`. That title is the record and stays reachable
  without MCP; `busy_*` tools are a mirror. Read-only work needs none.
- Release it the moment mutation stops. A marker idle over five minutes with no live process
  evidence is stale — clear it and continue. It is advisory, last-write-wins; on a collision the
  later claimant yields and takes other work.

### Live state beats stale instructions

- Prompts, schedules, names, receipts and handoffs describe the past; issues, PRs, branches and
  processes are the truth. No roles, no reserved work: any actor may take any unclaimed issue, and
  nothing from an earlier run blocks you now.
- Read a repo's `AGENTS.md` before your first mutation there.

### Branches, changelog, north star

- One branch per issue, `<actor>/<topic>-<YYYYMMDD>`, from current default. Delete it as part of
  merging. Prune branches already merged into the default branch without asking; never delete an
  unmerged one. Never force-push or rewrite another actor's branch.
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
- Precedence: current user instruction, then live repo/runtime evidence, then this block, then repo
  sections, then anything else. Acting against a written rule is allowed when evidence contradicts
  it — say so in the same response, naming the rule and the evidence.
- One rule, one owner: repo sections MUST NOT restate, reword, or re-scope anything here. Four
  files, four jobs — `NORTH_STAR.md` why, `AGENTS.md` how, `CHANGELOG.md` what changed, issues next.
<!-- SHARED-AGENT-POLICY:END -->

See README.md for what this bank is and how to use it.
