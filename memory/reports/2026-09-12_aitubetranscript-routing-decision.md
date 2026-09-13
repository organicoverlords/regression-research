# Pending canonical memory handoff — AITubeTranscript routing

Recorded: 2026-09-12
State: pending append-only handoff; not live authority
Target canonical memory: next `memory_bank.py record` / `memory/live` reconciliation when the local canonical writer is available

## Verbatim user source

> update vault and find and rules and such to include aitubetranscript

## Assistant interpretation

The user directs the shared system to make the existing `organicoverlords/AITubeTranscript` tool a first-class discoverable route rather than requiring historical-memory archaeology. The intended stable routing facts are:

- AITubeTranscript is the canonical tool/repository for YouTube transcript evidence and related description/comment/API-overlay research.
- Canonical navigation terms include `aitubetranscript`, `aitube`, and `youtube transcript`.
- Shared policy and centralized human-facing guidance should point to the existing AITubeTranscript product contracts instead of duplicating their executable/storage semantics.
- Vault history remains historical/navigation evidence, not current runtime/store truth.
- No parallel transcript store, registry, recurring worker, or scheduler should be created.

Confidence: high. This interpretation is directly supported by the user's explicit instruction and the existing AITubeTranscript repository contracts inspected in the same task.

## Current convergence evidence

- `organicoverlords/agents#381` tracks cross-repo convergence.
- `organicoverlords/agents#382` centralized AITubeTranscript routing/evidence guidance and merged.
- `organicoverlords/agents#383` preserved the detailed AITube agent guidance centrally and merged.
- `organicoverlords/AITubeTranscript#41` converted the product `AGENTS.md` to the shared-policy/central-doc pointer form and merged.
- `04 Operating Contracts/aitubetranscript-routing.md` records the current navigation/ownership boundary in this repository.

## Remaining source-level convergence

The direct Stack Atlas alias/component mapping in `tools/stack_atlas.py` and the paired shared-contract `RULES.md` / `AGENTS.md` edit remain tracked by `organicoverlords/agents#381`. Do not claim those source edits are complete until current repository evidence proves them.

This report exists because the local canonical memory writer/mirror freshness could not be proved through the available machine route. Per `memory/README.md`, a GitHub-only writer must not reconstruct or replace `memory-bank.jsonl`; this append-only report is the safe handoff for later canonical reconciliation.
