# Assistant Stack North Star

Status: **PRODUCT DIRECTION.** This document defines the finish line for the shared ruleset, BUSY/MCP coordination system, tool/plugin stack, memory boundary, repository workflow, and the regression-research system that protects them.

Repository: `organicoverlords/regression-research`.

## North star

The stack should be boring to use.

A user gives a clear instruction once. The system classifies the instruction source correctly, respects live ownership, chooses the right capability, keeps memory/personal context stable unless explicitly asked to change it, recovers from ordinary failures without exporting the failure to the user, and finishes the bounded task with evidence appropriate to the claim.

The user should not need to understand policy precedence, BUSY state, MCP binding, plugin topology, connector state, memory plumbing, worker ownership, retry policy, branch mechanics, CI routing, or orchestration just to get ordinary work done.

Complexity may exist internally. It must be absorbed by the stack rather than exported to the user.

## The anti-regression contract

Known failures must become permanently expensive to repeat.

Once a failure mode has trustworthy evidence, a replayable fixture, and a policy or implementation rule, future stack changes must continue to satisfy that fixture. The same known regression should not return because a model, plugin, connector, repo, or workflow changed.

If a known regression reappears, one of these must be true and explicitly identified:

1. the evidence was wrong or incomplete;
2. the fixture did not actually encode the intended behaviour;
3. the relevant fixture was not run or enforced;
4. the environment changed in a way the fixture did not model; or
5. a new higher-priority constraint genuinely changes the allowed behaviour.

"The assistant forgot," "the plugin changed," "the model behaved differently," or "the route was inconvenient" are not acceptable explanations by themselves.

Bad data must be correctable without destroying history. Superseded evidence stays traceable, and corrected evidence must identify what changed and why.

## Evidence coverage

The evidence model must not depend on one assistant surface. Local histories from **ChatGPT, OpenCode, Claude, Codex, Traycer, and Command-Code** are complementary evidence sources for the same operating stack.

- Preserve source, timestamp, repo/task scope, model/surface when known, and enough surrounding context to reconstruct the decision.
- Normalize common behavioural events across surfaces without erasing source-specific details.
- Cross-surface agreement strengthens a conclusion; disagreement is a finding that must remain visible.
- Missing logs or unavailable periods are explicit coverage gaps, not evidence that a behaviour did or did not occur.
- Prefer primary local logs/transcripts over summaries when establishing what actually happened.
- Use one surface to fill chronology/context gaps in another only when provenance makes the relationship defensible.
- Never merge contradictory records into a synthetic "consensus" event. Preserve both and resolve with stronger evidence or mark unresolved.
- Evidence ingestion/indexing must not mutate live personal-context or memory state.

The target is a corpus rich enough that a future regression can normally be compared against prior failures and successful controls across multiple agents rather than relying on one model's history.

## What finished looks like

### 1. One coherent ruleset

- There is one canonical shared policy owner for cross-project behaviour.
- Repo-local instructions add only genuinely local constraints; they do not restate, fork, or silently reinterpret global rules.
- Current user instructions and live runtime/repo evidence outrank stale defaults and historical context where higher-priority constraints permit.
- Instruction provenance is explicit enough to distinguish user-authored instructions/preferences, repo policy, memory/personal context, retrieved content, historical evidence, and higher-priority platform constraints without conflating them.
- A restriction on one part of a request does not erase allowed parts. Execute the allowed work and isolate only the blocked portion.
- Policy changes are versioned, auditable, migration-safe, and regression-tested before they become relied upon.
- Rules describe durable invariants and decisions. Volatile product/tool details live at adapter boundaries.

### 2. BUSY/MCP is the single live ownership system

- The standalone BusyCoordinator defined by current live repo/runtime state is the live ownership authority for shared mutable scope; MCP/plugin/process surfaces are transports, not ownership authorities.
- Before mutating shared scope, read live ownership and claim the exact scope. Read-only work needs no claim.
- If another live claim owns a scope, yield that scope without treating the entire task as blocked; continue independent work where possible.
- GitHub issue titles, branches, PRs, processes, receipts, schedules, handoffs, and status markers are projections/evidence, never a second ownership authority.
- When mutation stops, changes scope, or is handed off, release the matching live claim and reconcile any projection at the same boundary.
- MCP or connector transport failure must never be confused with ownership, authorization, or product failure.
- The coordination layer must fail locally: if BUSY state is temporarily unavailable, do not invent ownership, do not mutate contested shared scope blindly, and continue safe independent/read-only work while the route recovers.
- There must never be two competing BUSY authorities.

### 3. Non-blocking execution is the default

- Ordinary transient failures trigger bounded retry, rediscovery, reconnection, or a lower-coupling supported route automatically.
- A tool, plugin, connector, worker, CI lane, or coordination service is transport/capability, not permission.
- A failed transport path is not reported as task failure while another valid path exists.
- The assistant asks the user only for real external authority, destructive intent, spending, publication, or genuinely missing information that cannot be resolved from available state.
- Partial completion is preferred to unnecessary clarification or total refusal.
- The user is not asked to interpret tool errors, choose routine recovery steps, supervise workers, or perform mechanical repository work the stack can do itself.
- A failure in one subsystem must degrade only the affected capability, not collapse unrelated work.

### 4. Tools and plugins are replaceable adapters

- Capabilities are discovered from current availability rather than assumed from names or history.
- Core workflow is capability-based: read, search, mutate, coordinate, validate, publish, schedule, etc.
- Business logic does not depend on a specific connector implementation when an equivalent supported route exists.
- Each capability has one preferred route and a small, explicit fallback order.
- Plugin/tool failure degrades capability locally instead of destabilizing the whole workflow.
- Reads should be side-effect free. Writes are explicit, scoped, and verifiable.
- Tool chatter stays out of the user experience unless it materially changes the decision, risk, or result.
- Adding, replacing, or removing a plugin should require an adapter/configuration change, not a policy rewrite.
- Duplicate plugins or duplicate authorities are removed unless they provide a deliberate fallback with clearly different failure characteristics.

### 5. ChatGPT Memory carries continuity; Vault is history/notebook

- ChatGPT Memory and the current conversation provide ordinary conversational continuity so the user does not need to restate active context.
- Explicit current user instructions and verified live state outrank remembered context.
- Vault memory, reports, timelines, and conversation archives are optional searchable history/notebook/evidence, not startup gates or runtime behavior authority.
- Use targeted Vault retrieval when past context materially helps; never load the whole Vault as a mandatory startup constitution.
- Memory/history reads must not trigger hidden synchronization, ownership, scheduler mutation, or other control-plane work.
- Regression evidence remains preserved externally without becoming live behavior by accident.

### 6. One boring repository workflow

For repository work, use the smallest safe path that proves the requested outcome:

1. For stack/infra work, consult the Stack Atlas first; then inspect only the contract and live state the map and task make relevant.
2. Make the smallest complete change while preserving unrelated work.
3. Run focused proof. Escalate to an issue, claim, isolated branch/worktree, PR, broad CI, or publication only when collision risk, change risk, repository enforcement, or the actual delivery path requires it.

Control-plane machinery is conditional, not a checklist. A small low-risk change should stay small.

Historical caution, 2026-08-30: repository cleanup removed **470 remote branches** that had accumulated across the stack: Vault 45, Agents 8, LowVRAM 54, Tiny3D 68, and P3 295. No single branch created the failure. The accumulated temporary state made finished work look active, multiplied plausible sources of truth, and turned ordinary repository orientation into archaeology. This is evidence for the cleanup boundary above, not a new policy layer: temporary Git state should end when its bounded work ends.

Branches, retries, rebases, routine CI recovery, connector rediscovery, and bookkeeping are implementation details. They should not become user work.

### 7. Regression research closes the loop

Every recurring failure mode should eventually have all three:

- preserved evidence showing what actually happened;
- a replayable fixture with explicit pass/fail criteria; and
- a named policy or implementation rule that the fixture exercises.

A rule with no test is a hope. A fixture with no behavioural rule is an anecdote. A claimed fix without replay evidence is provisional.

Positive controls matter too. The suite should preserve examples where the system correctly handled correction, ambiguity, failure recovery, provenance, scope, ownership, and partial restriction so later hardening does not destroy good behaviour.

The evidence corpus is append-preserving. Corrections supersede; they do not erase the record that produced the old conclusion.

### 8. Future compatibility is designed in

- Policy describes invariants and decisions, not brittle product-specific UI steps unless the UI itself is the subject of the rule.
- Tool/plugin names live at adapter boundaries; core behaviour is capability-based.
- Every external dependency has an explicit failure mode and fallback or a clearly defined genuine hard stop.
- Deprecated components can be removed without losing policy history or replay coverage.
- New models, plugins, repos, and orchestration surfaces inherit the same behavioural contract without copy-paste drift.
- New stack components must prove compatibility against the existing regression suite before becoming the default route.

### 9. The user experience is the ultimate acceptance test

The stack is succeeding when ordinary work becomes uneventful:

- no repeated instructions;
- no mysterious blockers;
- no false claims of completion or failure;
- no silent personal-context mutation;
- no unnecessary questions;
- no process dumps when a concise answer will do;
- no loss of allowed work because one sub-part is restricted;
- no duplicate ownership systems;
- no need for the user to know which subsystem recovered the task;
- no recurrence of a known failure without a concrete evidence/test gap explaining why.

## Hard boundaries

- Never trade data safety, credential safety, or real external authorization for convenience.
- Never call something proven without observing evidence appropriate to the claim.
- Never silently change the user's request to make the workflow easier.
- Never make memory/personal-context mutation a hidden side effect of ordinary assistance.
- Never create a second authority for ownership, policy, or source truth when one already exists.

Everything else should bias toward completing useful work.

## Current focus

*Refreshed 2026-08-27 from the live conversation, the recovered #122 good-state boundary, issues #123, #125, and #155, the current repository contract, and the existing regression corpus. Historical PI/memory evidence remains separate from current live account configuration; no ChatGPT memory, Personal Instructions, or other personal-context store was modified by this documentation refresh.*

1. **Ruleset convergence.** Reduce cross-project behaviour to one canonical shared policy with repo-local additions only where genuinely local.
2. **Coordinator correctness.** Keep the standalone BusyCoordinator as the only ownership authority; treat its exact-scope checkpoint metadata as coordination context rather than workload, queue, priority, or capacity, MCP/plugin/process surfaces as transports, and legacy BUSY surfaces as compatibility evidence, and regression-test stale projections, route failures, claim/release boundaries, and independent-work continuation.
3. **Cross-surface evidence.** Inventory and provenance local ChatGPT, OpenCode, Claude, Codex, Traycer, and Command-Code logs; normalize common events while preserving disagreement and missing-coverage boundaries.
4. **Capability routing.** Inventory tools/plugins by capability, define one preferred path plus explicit fallbacks, eliminate duplicate authority/coupling, and make failures local.
5. **Instruction provenance.** Regression-test user-authored instructions versus repo policy, recalled context, retrieved content, and higher-priority constraints so safe requests are not over-refused or misclassified.
6. **Memory boundary.** Keep ordinary reads side-effect free, writes explicit/auditable, and analysis snapshots external to the live personal-context store.
7. **Evidence enforcement.** Map every known recurring failure to evidence + fixture + rule, add positive controls, and make those fixtures mandatory for changes that touch the relevant stack surface.
8. **End-to-end acceptance.** Build whole-stack replay scenarios covering provenance, BUSY ownership, tool selection, failure recovery, bounded completion, proof, cleanup, and concise reporting. The finish line is a stack that stays predictable as models and integrations change.
