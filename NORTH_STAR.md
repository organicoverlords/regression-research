# Regression Research North Star

Status: **PRODUCT DIRECTION.** This document defines the finish line for the assistant stack and the regression-research system that protects it.

Repository: `organicoverlords/regression-research`.

## North star

The stack should feel simple even when the machinery underneath is not.

A user gives a clear instruction once. The system understands which instruction source it came from, uses the right tools without ceremony, keeps private/personal state stable unless explicitly asked to change it, recovers from ordinary failures without handing the problem back to the user, and finishes the bounded task with evidence appropriate to the claim.

The user should never need to understand connector state, plugin topology, memory plumbing, worker ownership, retry policy, branch mechanics, or internal orchestration just to get ordinary work done.

## What finished looks like

### 1. One coherent policy

- There is one canonical shared policy owner for cross-project behaviour.
- Repo-local instructions add only genuinely local constraints; they do not restate or fork global rules.
- Current user instructions and live runtime/repo evidence win over stale defaults and historical context.
- Instruction provenance is explicit enough to distinguish user-authored preferences from system/platform rules, repo policy, memory, retrieved content, and historical evidence.
- A restriction on one part of a request does not erase allowed parts: execute the allowed work and isolate only the blocked portion.
- Policy changes are versioned, auditable, migration-safe, and regression-tested before they become relied upon.

### 2. Non-blocking execution by default

- Ordinary transient failures trigger bounded retry, rediscovery, or a lower-coupling route automatically.
- A tool, plugin, connector, worker, CI lane, or coordination service is never mistaken for permission to work.
- A failed transport path is not reported as task failure while another valid path exists.
- The assistant asks the user only for real external authority, destructive intent, spending, publication, or genuinely missing information that cannot be resolved from available state.
- Partial completion is preferred to unnecessary clarification or total refusal.
- The user is not asked to interpret tool errors, choose routine recovery steps, supervise workers, or perform mechanical repository work the system can do itself.

### 3. Tools and plugins are replaceable adapters

- Capabilities are discovered from current availability rather than assumed from names or history.
- Business logic does not depend on one connector implementation when an equivalent supported route exists.
- Plugin/tool failure degrades capability locally instead of destabilizing the whole workflow.
- Writes are explicit, scoped, and verifiable; reads should be side-effect free.
- Tool chatter stays out of the user experience unless it materially changes the decision, risk, or result.
- Adding, replacing, or removing a plugin should require a small adapter/configuration change, not a policy rewrite.

### 4. Memory and personal context are safe, inspectable, and non-authoritative

- Memory/personal context is read-only by default during ordinary work.
- No memory or personal-context write occurs merely because an assistant inferred that something might be useful later.
- Explicit current user instructions outrank recalled context.
- Historical context can inform a task but cannot silently override current live state.
- Memory writes, when explicitly authorized, preserve provenance, supersession, and auditability so contradictory or stale entries can be found and corrected.
- The regression repository may preserve snapshots/evidence about personal-context behaviour without mutating the live personal-context store.

### 5. One boring workflow

For repository work, the normal path is predictable:

1. Read the current repo contract and live state.
2. Reuse or create the relevant issue/task anchor.
3. Take an isolated branch/scope.
4. Make the smallest complete change.
5. Prove the actual claim on the artifact or runtime path that matters.
6. Add or update the regression that would catch the same failure again.
7. Commit, push, open the PR, validate, and merge when evidence is sufficient.
8. Remove temporary ownership/branch state and leave a durable audit trail.

The workflow should not expose process theater to the user. Branches, retries, rebases, routine CI recovery, connector rediscovery, and ordinary bookkeeping are implementation details.

### 6. Regression research closes the loop

Every recurring failure mode should eventually have all three:

- preserved evidence showing what actually happened;
- a replayable fixture with explicit pass/fail criteria; and
- a named policy or implementation rule that the fixture exercises.

A rule with no test is a hope. A fixture with no behavioural rule is an anecdote. A claimed fix without replay evidence is provisional.

Positive controls matter too: the suite should preserve examples where the system correctly handled correction, ambiguity, failure recovery, provenance, and scope so later hardening does not destroy good behaviour.

### 7. Future compatibility is designed in

- Policy describes invariants and decisions, not brittle product-specific UI steps unless the UI itself is the subject of the rule.
- Tool/plugin names live at adapter boundaries; core behaviour is capability-based.
- Every external dependency has an explicit failure mode and fallback or a clearly defined genuine hard stop.
- Deprecated components can be removed without losing policy history or replay coverage.
- New models, plugins, repos, and orchestration surfaces should inherit the same behavioural contract without copy-paste drift.

### 8. The user experience is the ultimate acceptance test

The stack is succeeding when ordinary work becomes uneventful:

- no repeated instructions;
- no mysterious blockers;
- no false claims of completion or failure;
- no silent personal-context mutation;
- no unnecessary questions;
- no process dumps when a concise answer will do;
- no loss of allowed work because one sub-part is restricted;
- no need for the user to know which subsystem recovered the task.

Complexity may exist internally, but it must be absorbed by the stack rather than exported to the user.

## Hard boundaries

- Never trade data safety, credential safety, or real external authorization for convenience.
- Never call something proven without observing evidence appropriate to the claim.
- Never silently change the user's request to make the workflow easier.
- Never make memory/personal-context mutation a hidden side effect of ordinary assistance.

Everything else should bias toward completing useful work.

## Current focus

*Refreshed 2026-08-27 from the live conversation, issue #123, current repository contract, and existing regression corpus. No memory or personal-context store was modified.*

1. **Policy/provenance correctness.** Ensure user-authored preferences are distinguishable from protected/platform instructions and from recalled or retrieved context, so safe requests are not over-refused and provenance mistakes become testable regressions.
2. **Non-blocking recovery.** Consolidate the existing blocker-substitution, premature-finalization, MCP/connector, harness-vs-product, and scope-drift cases into one coherent recovery contract with capability-based fallbacks.
3. **Memory boundary.** Keep ordinary reads side-effect free, make writes explicit and auditable, and preserve regression evidence externally so personal context can be analyzed without silently changing it.
4. **Stack simplification.** Inventory plugins/tools/workflows by capability, remove duplicate authorities and unnecessary coupling, define a preferred route plus fallback for each capability, and make failure local rather than systemic.
5. **End-to-end acceptance.** Build replay scenarios that exercise the whole contract: instruction provenance, tool selection, recovery, bounded completion, evidence, and concise reporting. The target is not merely passing individual fixtures; it is a stack that stays predictable as models and integrations change.
