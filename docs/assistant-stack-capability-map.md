# Assistant stack capability and authority map

Status: **CURRENT DESCRIPTIVE INDEX**, observed 2026-08-30. This document is not a control plane and is never authoritative merely because it is centralized.

Purpose: make existing capabilities and their real owners obvious **before** anyone proposes another cross-stack component. Current user instruction and the cited live/source authority always outrank this map when they disagree.

Start with the human-facing map: [`assistant-stack-human-map.md`](assistant-stack-human-map.md). Companion machine-readable index: [`assistant-stack-capability-map.json`](assistant-stack-capability-map.json). Standalone overview source: [`assistant-stack-capability-map.mmd`](assistant-stack-capability-map.mmd).

## The rule this map exists to enforce

Before proposing a new component, search this map for the capability. If an existing authority already owns it, the default choices are:

1. use the existing capability;
2. make the smallest change at that existing owner if evidence proves a gap; or
3. do nothing.

A dashboard, transport, plugin, issue, branch, worker, memory entry, cached packet, or generated map never acquires authority merely because it is convenient.

## Why this became necessary: issue #271

Regression-research #271 proposed a derived resume/context layer with a live registry, structured checkpoints, and resume packets. The proposal was reviewed and narrowed before live inspection established that the standalone BusyCoordinator already owned most of the proposed resumability mechanism.

BusyCoordinator already exposes jobs, `checkpoint`, `snapshot`, `inspect`, `next`, `recover`, and `handoff`. `handoff` records parent scope, finding ID, reporter, source, summary and timestamp, then creates a ready child job whose checkpoint carries the resumable finding.
A live example observed during this work was `standalone-coordinator:audit-logging::handoff:deployed-source-divergence`, which already preserved source evidence and resumable next work.

The failure was therefore **capability invisibility**, not missing resumability infrastructure. The dated #155 architecture diagram described components, but it still named the old MCP0 BUSY topology and did not expose current BusyCoordinator job/checkpoint/handoff capability prominently enough to stop a duplicate design.

## Authority model

Different questions intentionally have different authorities. There is no single global database that should answer all of them.

| Question / capability | Canonical owner | Read/projection surfaces | Explicit non-authorities |
|---|---|---|---|
| What does the user want now? | Current user instruction | Current conversation | Memory, old issue text, old handoff |
| Cross-project behavioral invariants | Canonical shared policy | Generated repo policy blocks | Per-project prose, worker prompts |
| Repo-local operating rules | Current repo `AGENTS.md` | Checkout / GitHub file view | Global map, progress board |
| Project direction | Current `NORTH_STAR.md` or equivalent + user priority | Docs / board summaries | Worker recency, issue number |
| Exact shared-mutation ownership | **Standalone BusyCoordinator** | `snapshot`, `inspect`, operator projection | GitHub titles, branches, processes, schedules |
| Job ready/active/blocked/completed state | **Standalone BusyCoordinator** | `snapshot`, `next`, operator projection | Issue labels, board status |
| Checkpoints / resumable task state | **Standalone BusyCoordinator** | job `checkpoint`, `inspect`, operator projection | Ad-hoc resume packet copies |
| Durable actionable handoff | **Standalone BusyCoordinator `handoff`** | ready child job + checkpoint | Prose-only â€œsomeone can pick this upâ€ |
| Process execution | Replaceable process transport | ChatGPTMcpClean/plugin2, Remote Desktop Commander, native shell | Transport does not imply ownership |
| Local file/branch/HEAD/dirty truth | Local filesystem + Git/worktree | operator projection | GitHub issue prose, memory |
| Remote issue/PR/published revision | GitHub | `gh`, connector/API | BUSY/coordinator state |
| CI result | Exact GitHub Actions workflow/run | operator projection | â€œtests should passâ€ prose |
| Runtime/product behavior | Exact runtime/artifact observation | logs/captures/test receipts | source inspection alone |
| Fresh-session behavior continuity | current conversation + ChatGPT Memory | live repo/runtime evidence; Vault only as optional history/notebook/evidence | Vault behavior bootstrap, generated Library bootstrap, full memory bank |
| Historical/regression evidence | Vault / regression-research corpus | `context`, `timeline`, `orient`, reports/fixtures | live operational truth |
| Product progress presentation | DevProgressBoard derived state | browser, status/operator feeds | product/repo authority |
| Timed recurrence | ChatGPT Automations | scheduler state | mutation ownership |

## Component map

### User and orchestration

**User / current instruction** owns the current goal, scope changes, destructive intent, spending/publication decisions and other genuine external authority.

**ChatGPT direct chat** is the continuity/orchestration surface. It combines current instruction with applicable policy and live evidence, chooses a supported route, delegates bounded work when useful, reconciles results and reports concisely. It consumes authorities; it does not become one by summarizing them.

**ChatGPT Automations** owns timed wakeups and recurrence. Five enabled recurring repo workers were observed on 2026-08-30: Alder, Cedar, Ember, Harbor and Juniper. Scheduler state is not repository ownership.

**Execution workers** include timed ChatGPT workers and other available executor surfaces such as Codex, Claude, OpenCode, Command-Code and Traycer. They perform bounded work under the same current policy and coordinator. Worker names, process existence and recent activity are evidence, not authority.
### Context, behavior and policy

**Vault / regression-research** at `C:\Users\Lauri\Desktop\vault` owns the external behavior bootstrap, durable historical evidence, regression corpus, reports and fixtures. Historical memory is evidence rather than live repo/runtime truth.

**`tools/memory_bank.py`** provides separate read paths: `bootstrap` for the compact fresh-session behavior constitution; `context` for bounded task recall; `timeline` for chronology; and `orient` for richer diagnostics. Ordinary reads are side-effect free.

**ChatGPT Personal Instructions / saved memory** are separate product-level context surfaces. They are not the Vault, and Vault evidence does not prove or silently mutate current product configuration.

**Canonical shared policy** lives at `C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md`. Generated repo blocks are synchronized copies of one logical cross-project authority.

**Repo `AGENTS.md`** owns genuinely repo-local operating constraints. **`NORTH_STAR.md` / equivalent** owns project direction and finish-line intent, not live mutation ownership.

### Coordination: one owner

**Standalone BusyCoordinator** is the single live ownership/job/checkpoint authority for shared mutable scope. Installed entrypoints are `%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd` and `busy-rust.cmd`.

Its current contract requires: `list`, `sweep`, `snapshot`, `enqueue`, `ready`, `next`, `recover`, `handoff`, `claim`, `heartbeat`, `release`, `block`, `complete`, `inspect`, plus installed observability commands `contract`, `log`, and `audit`.

The canonical store is `%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json`. Contract invariants include one canonical claims store, one claim per exact scope, matching active job/claim ownership, bounded replay/completed history, and parity between Python/Rust cores.

**Important boundary:** legacy `busy_*` tools exposed by some MCP profiles are compatibility adapters only. GitHub issues, branches, PRs, worker processes, schedules and progress-board state are projections/evidence and never a second ownership authority.
### Process and tool transport

**ChatGPTMcpClean / plugin2** at `C:\Users\Lauri\AppData\Local\ChatGPTMcpClean` is process transport behind a stable front door. Its minimal process profile intentionally exposes only start/read/kill process operations. Current README explicitly keeps BUSY/job coordination outside MCP in standalone Rust/Python coordinator apps.

**Remote Desktop Commander** is another authorized machine/files/process transport when exposed. It is a route to capabilities, not a scheduler, policy source, coordinator or repository authority.

A route failure is local: losing one transport must not redefine the task, declare the backend globally dead, or create a replacement authority while an equivalent supported route exists.

### Source, publication and proof

**Local filesystem + Git/worktrees** own current local bytes, branch/HEAD, dirty state and local commit identity. Worktree/process counts can help detect collisions, but they are not claims.

**GitHub** owns remote repository state, issues, PRs, published commits and workflow records. It is task/publication/evidence transport, not BUSY.

**GitHub Actions and self-hosted runners** provide CI evidence for exact revisions/runs. Current runner/workflow counts are live state and must be queried when needed; this structural map does not cache them.

**Local runtime / Unreal / exact artifact proof** owns claims about actual runtime or user-visible behavior when observed. Builds, source inspection and CI are narrower evidence unless the repo acceptance contract says otherwise.

### Read models and observability

**DevProgressBoard** at `C:\Users\Lauri\Desktop\DevProgressBoard` is a deterministic derived product-progress board. Workers append facts; reconciliation derives visible state. AI summaries are optional and do not replace its event ledger or live Git/GitHub probes.

**`state/operator-live.json`** is a near-live operator projection (15-second feed) containing machine pressure, coordinator counts/scopes, repo/worktree state, runner/workflow state and recent progress. It is ideal for orientation but is never authoritative over the sources it projects.
### Product/data pipeline

Current product repo architecture defines one active flow:

`LowVRAM -> Tiny3D -> P3`

- **LowVRAM 3D Pipeline**: `C:\Users\Lauri\Desktop\lowvram3d-repo`, remote `organicoverlords/lowvram3d-studio`. Generator/source-recovery boundary: image-to-3D geometry, textures, provenance, preserved masters and producer visual QA.
- **Tiny3D**: `C:\Users\Lauri\Desktop\tiny3d`, remote `organicoverlords/tiny3d`. Single post-generation 3D asset product: compilation, rigging/skinning, animation/deformation preparation, validation/adapters, packaging/lifecycle evidence, catalogue operations and asset-library ownership.
- **Tiny3D asset library**: external content-addressed store at `C:\Users\Lauri\Desktop\Tiny3D_LIBRARY`; a Tiny3D subsystem, not a separate product or authority.
- **P3**: `C:\Users\Lauri\Documents\Unreal Projects\p3`, remote `organicoverlords/p3`. Downstream Unreal/game materialization and runtime/gameplay/visual acceptance.
- **TinyLab**: historical naming/schema compatibility only. It is not a current product-stage authority.

For product-stage ownership questions, read the current LowVRAM/Tiny3D/P3 repo architecture contracts first. Historical migration issues, old handoffs, archived capability maps and DevProgressBoard projections may explain lineage but cannot redefine the active boundary.

### Stack implementation repositories

- **regression-research / Vault**: assistant behavior, regression evidence/fixtures, shared-stack acceptance work and canonical source for recent BusyCoordinator development.
- **ChatGPTMcpClean**: stable MCP/process front door and connector implementation; coordination remains outside it.
- **DevProgressBoard**: local deterministic product-progress/read-model implementation.
- **P3 / Tiny3D / LowVRAM**: product engineering repos with their own local authority and proof requirements.

## Known drift and unresolved seams

1. [`assistant-stack-architecture.md`](assistant-stack-architecture.md) is a dated 2026-08-27 snapshot, not current topology.
2. DevProgressBoard is a user-facing derived progress cockpit. It is not the authority for product-stage ownership.
3. TinyLab names/schema identifiers may remain for historical compatibility; current Tiny3D README/North Star define Tiny3D as the single post-generation product.
4. Dynamic resource, runner, worker and repo counts belong in live reads, not durable structural maps.
5. If retrieved history conflicts with the current product repo architecture contract, current repo architecture wins and the stale map/history becomes a regression finding.

## Pre-design duplicate check

Before starting an RFC or implementation for cross-stack infrastructure, answer these in order:

1. **What exact capability is missing?** Use a verb such as handoff, checkpoint, schedule, execute, publish, validate, remember, observe.
2. **Who owns that capability today?** Search this map and inspect the cited live/source authority.
3. **Does the owner already have the needed command/field/path?** Test it before proposing architecture.
4. **Is the apparent gap only discoverability or projection?** If yes, improve the map/read view rather than adding a system.
5. **Would the proposal store a second copy of authoritative state?** If yes, reject by default.
6. **Would correctness require synchronized writes across multiple systems?** If yes, the design is probably too coupled.
7. **Can the need be solved by a source-local field, adapter change, or documentation index?** Prefer that.
8. **What evidence would make us delete the proposal?** State the falsifier before implementation.

## Acceptance for this map

The map is doing its job when a fresh assistant can answer â€œwho already owns X?â€ before designing X, and can distinguish authority, transport, projection, evidence, context and product pipeline without asking the user to supervise those mechanics.
