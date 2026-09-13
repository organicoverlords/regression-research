# Assistant behavior regression contract (DRAFT / NON-LIVE)

Status: design WIP only. This document is not serving policy and is not an additional behavior-policy authority.

## Purpose

Assistant behavior prose can state what should happen, but prose alone does not prove that the same failure will be rejected later. This contract owns the deterministic regression layer that turns preserved incidents into executable next-action checks.

The layers have different jobs:

- **RULES/AGENTS prose** owns desired shared behavior and policy.
- **Incident reports/evidence** preserve what actually failed and why the conclusion is supported.
- **Replay fixtures** preserve one bounded historical decision boundary with failure/success controls.
- **Replay scoring assertions** are the executable behavior-contract vocabulary. A fixture selects assertions through its `scoring` object.
- **Memory** is retrieval/indexing and a compact reusable lesson; it is not enforcement or the full incident.
- **Stack Atlas** is navigation to these owners, never another policy or regression registry.

## Existing owner

Use the existing surfaces instead of creating a second registry:

- `tools/replay_scoring.py` — provider-free deterministic assertion implementation and fixture validation;
- `tools/behavior_incident_capture.py` - bounded visible-context capture materializer; no conversation reconstruction and no canonical-memory write;
- `tools/behavior_incident_close.py` - resumable canonical-memory closure owner using `memory_bank.py`, followed by replay/provenance finalization;
- `tools/slopwall_v2.py` - behavior-incident identity, linkage, scoring, and closure validator;
- `03 Fixtures and Experiments/` — tracked replay instances and positive/negative controls;
- `tools/verify.py` and focused tests — repository regression verification;
- `01 Reports/` / evidence — forensic source for incidents;
- `memory_bank.py` — searchable lesson/pointer.

The assertion names in `SUPPORTED_ASSERTIONS` are the executable contract vocabulary. A fixture's `scoring` block binds a historical case to those contracts. Shared semantic grouping may be described in prose, but no second hand-maintained contract registry is required.

## Reuse before promotion

For a new incident, including events explicitly triggered by `slopwall` or `incident report`:

1. Inspect the smallest relevant existing replay/assertion owner.
2. Reuse existing assertions when they already discriminate the failure.
3. Do not add an assertion merely because the incident is important or because a prose rule was violated.
4. Propose a new assertion only when the incident exposes a reusable observable invariant not covered by the existing assertion vocabulary.
5. A new assertion must be deterministic from supplied candidate/evidence data, have a known success control and known failure control, identify the violated condition, and have focused automated tests.
6. Wire the relevant replay/test into normal verification when it is promoted from design WIP.

One incident may justify a new assertion when the uncovered boundary is strongly evidenced; multiple independent incidents strengthen confidence but are not an arbitrary prerequisite.

## Behavior contract versus shared-rule change

These are deliberately separate decisions.

A **new behavior contract/assertion** may be useful even when the existing prose rule was already correct: the replay gives the system a concrete regression guard for a rule-consumption, authority-selection, or reasoning/action-selection failure.

A **shared RULES/AGENTS change** requires stronger evidence. A bad answer alone is insufficient. Shared prose changes are proposed only when the incident proves `RULE_GAP` or `RULE_CONFLICT` (including bounded evidence for that classification). Otherwise preserve the existing rule and add/reuse replay coverage as appropriate.

## Slopwall V2 binding

Every corrective event triggered by `slopwall` or `incident report` gets a replay fixture, but not every incident creates a new behavior contract. The event records a behavior-contract review:

- which existing assertions were checked;
- whether they cover the failure;
- disposition: `REUSE_EXISTING`, `PROPOSE_NEW`, or `NONE`;
- for `PROPOSE_NEW`, which assertion names are proposed and what uncovered invariant they encode.

Repeated corrective triggers (`slopwall` or `incident report`) create linked events. They may reuse the same contract while increasing observed correction resistance, or expose a new contract gap if the repair mechanism itself fails in a distinct way.

## Shared-rule mutation contracts

The Slopwall V2 semantics incident exposed two previously uncovered executable invariants for candidate actions that propose a shared-rule change:

- `existing_behavior_authority_checked_before_shared_rule_change`
- `shared_rule_change_requires_proven_gap_or_conflict`

These assertions consume structured `candidate.rule_change` evidence rather than trusting explanatory prose. If no shared-rule change is proposed, they do not manufacture one.

## Non-goals

- no model/provider invocation inside the deterministic scorer;
- no automatic policy mutation from a replay failure;
- no requirement to restore the retired bulk Slopwall corpus-reconstruction pipeline;
- no second behavior-contract database or dashboard as authority;
- no claim that passing deterministic fixtures proves all future model behavior. It proves only that the supplied candidate satisfies the encoded bounded invariants.

## Discoverability

Stack Atlas should navigate `behavior contract`, `replay fixture`, `replay scoring`, `acceptance contract`, `assistant regression`, and `slopwall replay` to the `assistant_behavior_regressions` owner. From there, leave Atlas and use the replay/scorer/report owners directly.

## Visible-context capture boundary

Behavior-incident capture never requires a whole-conversation reload. Raw incident evidence is the relevant material already visible to the agent, preserved verbatim. Additional retrieval is allowed only when needed to diagnose or repair the incident, not to reconstruct unseen transcript history for archival completeness.

`tools/behavior_incident_capture.py` consumes an explicit visible-context capture spec. It preflights destination/provenance collisions, validates the complete generated bundle in staging, then commits evidence + report + replay + pending-memory handoff + provenance as one rollback-capable write set. It never calls transcript/conversation retrieval and never writes `memory/memory-bank.jsonl`; canonical memory remains a separate closure step. Capture is forbidden directly on a Git `main` checkout: materialize in an isolated feature worktree so incident durability cannot make the serving Vault dirty or degrade bootstrap.

`tools/behavior_incident_close.py` owns that separate closure step. Before any canonical memory write in a Git checkout, the exact source report, replay, and visible-context evidence bytes must already exist on `refs/remotes/origin/main`; an unmerged branch or dirty working tree cannot serve as canonical evidence. For newly captured incidents, closure also requires the actual subsequent user-facing repair reply/action to be observed from visible context, appended verbatim to the bounded evidence, bound as `repair_candidate`, and replay-scored PASS. A report claim that a repair occurred is not repair proof. Every new capture also records an explicit `repair_authority` review. When the repair itself is an authority-sensitive mutation, replay scoring and closure require independent PASS evidence from the named normal owner/gate; `slopwall`, `incident report`, or any corrective trigger is never authorization by itself. It then uses a deterministic event-derived memory ID and the public `memory_bank.append_entry/load_bank` interfaces. Canonical memory is recorded first; replay and provenance are finalized to `CLOSED` second. If repository finalization fails, the memory is retained and rerun reuses the exact same memory instead of deleting or duplicating durable evidence.
