# Assistant Stack Companion — 2026-08-27

This document accompanies the architecture map for [regression-research #155](https://github.com/organicoverlords/regression-research/issues/155). It maps the current stack; it does not redesign it.

## Component definitions

**WebGPT — INTENDED primary continuity/orchestration surface; PROVEN current context capabilities.** The user explicitly designates WebGPT as the continuity/orchestration brain. In the observed surface, WebGPT has current conversation history, user-authored personal instructions, advisory memory context, task-scheduler access, GitHub access, and a conversation-scoped MCP0 integration. Private instruction/memory contents are deliberately not reproduced here.

**Timed WebGPT workers — PROVEN scheduler records, mixed live state.** Five named `P3 Asset Sprint` records exist. Only Sprint 3 is currently enabled. Sprint 1/2 are convergence-first workers; Sprint 3/4/5 use the bounded asset-placement scope. Scheduler metadata alone does not prove which PR/commit a run produced.

**Codex — PROVEN distinct execution surface; UNKNOWN current MCP0 binding.** Issue #155 records a historical case where Codex had MCP0 availability. That is evidence about Codex at that time, not evidence about WebGPT or current Codex state.

**Other execution workers — PROVEN as supported stack components; INTENDED bounded implementation role.** Current P3 policy names detached Codex/OpenCode/Traycer/Command-Code helpers. They are not a second continuity brain and must not create hidden ownership/scheduler systems.

**Personal instructions, ChatGPT memory, conversation history, Vault corpus — PROVEN/INTENDED distinct sources.** These are separate context/evidence channels. Shared policy and the north star require live user instruction and live repo/runtime state to outrank stale context. Memory is read-only by default; Vault is an external evidence/corpus store, not live ownership authority.

**MCP0 — PROVEN deployed adapter topology/configured seven-tool contract.** `chatgpt-mcp-clean` defines a stable local front door at `127.0.0.1:3003/mcp`, replaceable loopback backends on 3001/3002, Tailscale Funnel in front of the stable origin, and exactly seven worker-visible tools: `view_image`, `start_process`, `read_output`, `kill_process`, `busy_list`, `busy_claim`, `busy_release`.

**GitHub — PROVEN durable work/publication surface for private repo work.** Issues are durable task/evidence anchors; branches/commits/PRs carry implementation; CI provides supporting validation. GitHub BUSY titles are intended to be projections only under shared v1.18.

**Runtime proof — PROVEN acceptance surface for player-visible P3 claims.** Current policy requires a rendered frame through the normal runtime path. Recent asset-placement PRs visibly remain unmerged/NOT_PROVEN when source/build gates pass but runtime/render evidence is absent.

## Authority matrix

| Question | Canonical/current authority | Status | Notes |
|---|---|---|---|
| What did the user ask? | Current user instruction | **PROVEN** | Highest ordinary task authority, subject to platform constraints |
| Cross-project behavior | Canonical shared policy v1.18 | **PROVEN** | Local source is canonical; GitHub `organicoverlords/agents` is an auditable mirror |
| Why is a repo being changed? | Repo `NORTH_STAR.md` | **PROVEN** | Product direction/current focus |
| How is repo work performed? | Repo `AGENTS.md` plus shared policy | **PROVEN** | Repo section must not re-scope shared rules |
| What work exists next? | GitHub issues/live repo state | **PROVEN** | Durable backlog/evidence |
| Who owns mutable shared scope now? | MCP0 BUSY | **PROVEN policy authority** | If unavailable, do not invent a second authority or mutate contested scope blindly |
| What code/version is real? | Git refs/branch/commit/PR + current working/runtime state | **PROVEN** | Live state beats stale handoff text |
| Did tests/builds pass? | Observed exact-run CI/build/test evidence | **PROVEN when inspected** | Supporting evidence only |
| Is a player-visible result accepted? | Normal runtime rendered proof + inspection | **PROVEN policy authority** | Compile/file existence alone is insufficient |
| What may memory decide? | Nothing authoritatively | **PROVEN policy** | Advisory context; current live instruction/state wins |
| What is the durable evidence corpus? | Regression repo + Vault/corpus sources with provenance | **INTENDED/PROVEN in repo direction** | Missing coverage stays explicit |
| Who may publish externally/publicly? | User | **PROVEN policy** | Private repo branch/PR/merge is ordinary authorized work; public external publication remains user-owned |

## Normal end-to-end flow

1. **Request — INTENDED.** The user gives a short instruction to WebGPT; WebGPT retains continuity without requiring the user to explain internal topology.
2. **Orient — PROVEN policy.** Read the applicable `NORTH_STAR.md`, `AGENTS.md`, issue/PR/live state, and only the context sources that materially affect the task.
3. **Ownership — PROVEN policy.** Read MCP0 BUSY and claim the exact mutable scope. Read-only work requires no claim.
4. **Dispatch/execution — INTENDED.** WebGPT either executes directly or uses an authorized timed/bounded worker. Worker names/schedules do not reserve work between runs.
5. **Isolated change — PROVEN workflow.** Use issue anchor, branch, smallest complete implementation, changed-area test, commit and PR.
6. **Supporting validation — PROVEN workflow.** CI/build/test must be observed on the exact relevant revision.
7. **Acceptance proof — PROVEN workflow.** For player-visible work, execute the normal runtime path and inspect the rendered result. Missing proof stays `NOT_PROVEN`.
8. **Land/cleanup — INTENDED/PROVEN policy.** Merge only with sufficient evidence, release MCP BUSY, reconcile stale projections, delete/reuse temporary branch/worktree state safely.
9. **Report — INTENDED.** WebGPT gives the user the material result and any genuine remaining decision, not internal recovery mechanics.
10. **Evidence preservation — INTENDED.** Durable issue/PR/CI/runtime/corpus evidence is kept with provenance. Memory/personal-instruction state is not mutated unless explicitly requested.

## Degraded flows

### MCP0 is not injected/discoverable in the WebGPT conversation
**INTENDED behavior:** distinguish conversation binding from account configuration and backend health. Perform bounded rediscovery in the same surface. Continue safe read-only or independent work. Do not infer ownership, create a GitHub-title ownership substitute, or mutate contested shared scope.

### MCP0 is discoverable but calls are unavailable
**PROVEN current example:** this conversation first made a successful MCP0 `busy_list`, then after switching connector surfaces rediscovered the seven tools but direct calls returned `Resource not found`. This establishes a conversation-level callability failure, not backend failure. The same no-second-BUSY degraded rule applies.

### Backend/public/front-door failure
**PROVEN classification exists; current incident class UNKNOWN.** `chatgpt-mcp-clean#7` separates pre-dispatch/non-arrival, local-listener stalls, public/Funnel failures, server-arrived abnormal responses, and intentional bounded waits. Diagnose at the boundary; do not collapse all into “MCP died.”

### GitHub BUSY projection looks stale
**PROVEN shared policy:** the GitHub marker is evidence only. If a matching live MCP claim is proven absent, the projection is stale. If MCP itself is unavailable, absence cannot be proven; avoid contested mutation until live ownership is readable.

### A timed worker is paused/unavailable
**PROVEN current state / INTENDED behavior:** only Sprint 3 is enabled. Paused worker names do not reserve work. Safe unclaimed work can be taken by another authorized actor once live ownership can be established.

### CI/build capacity is contended
**INTENDED policy:** queue/retry the required heavy gate and continue useful non-conflicting work. Resource contention is not product failure.

### Runtime/render proof is unavailable
**PROVEN current P3 practice:** preserve the exact claim as `NOT_PROVEN`; do not merge/close a player-visible claim as accepted; record the first unmet proof stage and advance other safe work.

### Memory/context is stale or contradictory
**PROVEN policy:** current user instruction and live repo/runtime evidence win. Historical context stays evidence with provenance. Do not “repair” memory as a side effect of ordinary work.

## Explicit unknowns

- Current persistent/account-level MCP0 configuration state.
- Current MCP0 backend/front-door health at the exact time later WebGPT calls returned `Resource not found`; no matching server telemetry was inspected.
- Current Codex conversation MCP0 binding/callability; historical Codex availability is not current proof.
- Attributable recent outcomes for P3 Asset Sprint 1, 3, 4, and 5; the observed scheduler metadata did not provide run-to-PR/commit linkage. No specific GitHub artifact should be assigned to those workers without stronger provenance.
- Direct current Vault `recent` output in this work session. The local read route could not be executed after the WebGPT MCP binding became unavailable. The Vault’s role is therefore mapped from current policy/context provenance without exporting its private contents.
- Whether the live P3 and LowVRAM ownership contradictions have already been assigned to another worker for remediation. #155 only records the contradiction.

## Concrete evidence-backed follow-up gaps

These are findings suitable for follow-up under #125; #155 should not redesign them itself.

1. **Resolve duplicate ownership authority text.** P3’s repo-local “GitHub title is the claim” language and LowVRAM’s Traycer YAML ownership language conflict with the shared v1.18 MCP0-BUSY-only rule.
2. **Add worker-run provenance linkage.** The five timed worker records should have a durable run identity that can be correlated with issue/branch/PR/commit outcomes without relying on generic `PROVENANCE=chatgpt`.
3. **Regression-test conversation binding vs backend health.** Preserve a fixture where MCP0 is discoverable but callability fails before server dispatch, ensuring the stack does not blame backend health or create a second BUSY authority.

## What the user never has to manage

The user should not have to manage MCP binding recovery, BUSY reconciliation, worker schedules, worker-to-PR attribution, branch/worktree mechanics, CI retries, runtime-proof logistics, stale handoffs, memory/corpus plumbing, connector topology, or choosing routine technical recovery steps. Those are stack responsibilities.

The user remains responsible for genuine product/creative choices and external authority such as destructive intent, spending, secrets/approvals, or public external publication.
