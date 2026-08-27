# Cross-surface local history coverage — 2026-08-27

Status: **EVIDENCE INVENTORY / GAP RECORD**

Purpose: establish which assistant-history surfaces are already represented in the regression stack and which are still missing, without modifying any live memory or personal-context store.

Target surfaces from the current user instruction:

- ChatGPT
- OpenCode
- Claude
- Codex
- Traycer
- Command-Code

## Current evidence

### ChatGPT — PRESENT / STRONGEST CURRENT COVERAGE

The repository already contains ChatGPT raw transcripts, ChatPort corpus catalogues, conversation-search tooling, Personal Instructions evidence, and multiple replay fixtures.

Current limitation: coverage is still incomplete for some exact conversations/screenshots, and those gaps are explicitly recorded elsewhere rather than guessed away.

### Claude — HISTORICALLY INVENTORIED, RAW COVERAGE NOT YET VERIFIED HERE

`memory/sources.json` records:

- source id: `claude-history`
- location: `local/.claude`
- class: `HISTORICAL_CONTEXT`
- freshness: `historical-turns`
- historical availability: `available`

Issue #15 required bounded extraction coverage across `Claude-Codex history`.

Current limitation: the current repository provenance index does not expose raw Claude log paths, and this ChatGPT session has no direct local-filesystem route to verify that `local/.claude` still exists or to enumerate its current contents. Treat the 2026-08-25 inventory as historical evidence of availability, not current filesystem proof.

### Codex — HISTORICALLY INVENTORIED + FIXTURE COVERAGE

`memory/sources.json` records:

- source id: `codex-history`
- location: `local/.codex`
- class: `HISTORICAL_CONTEXT`
- freshness: `historical-rollouts`
- historical availability: `available`

`tests/fixtures/memory-source-snippets.jsonl` contains a bounded `codex-history:rollout-42` extraction fixture.

Current limitation: this proves extractor/test coverage, not preservation of the full local Codex log corpus in this repository. Current local filesystem presence is not proven from this session.

### Traycer — HISTORICALLY INVENTORIED + FIXTURE COVERAGE

`memory/sources.json` records:

- source id: `traycer-artifacts`
- location: `local Traycer/TRACER.md/review artifacts`
- class: `HISTORICAL_CONTEXT`
- freshness: `artifact-timestamp`
- historical availability: `available`

`tests/fixtures/memory-source-snippets.jsonl` contains a bounded `traycer-review:review-7` extraction fixture.

Current limitation: as with Codex, the fixture proves extraction behavior, not that the complete current local Traycer corpus is preserved or indexed here.

### OpenCode — COVERAGE GAP

No OpenCode source id/location is present in the current `memory/sources.json` inventory, and no OpenCode-named artifact is exposed by the current repository tree/provenance inspection.

This does **not** prove that local OpenCode logs do not exist. It proves only that the regression repository currently lacks an explicit, auditable OpenCode source definition/pointer in the inspected source inventory.

Required future state:

- identify the canonical local OpenCode history/log location;
- record source class, timestamp semantics, and availability independently of memory recall;
- preserve pointers/hashes or bounded source receipts without copying secrets;
- add representative positive and negative replay fixtures;
- keep raw-history import/read paths side-effect free.

### Command-Code — COVERAGE GAP

No Command-Code source id/location is present in the current `memory/sources.json` inventory, and no Command-Code-named artifact is exposed by the current repository tree/provenance inspection.

This does **not** prove that local Command-Code logs do not exist. It proves only that the current regression stack has no explicit source definition/pointer for them.

Required future state is the same as OpenCode: canonical local source identification, provenance, timestamp semantics, safe bounded indexing, and replay coverage.

## Stack-level acceptance rule

The future evidence layer should treat all six surfaces as complementary sources rather than collapsing them into one generic "assistant history" stream.

For each source, preserve at minimum:

- source/product identity;
- canonical location or acquisition method;
- source timestamp and ingestion timestamp;
- immutable hash/receipt where practical;
- conversation/run/review identifier when available;
- current availability status;
- authority class (`CURRENT`, `LIVE_CANONICAL`, `VERIFIED_EVIDENCE`, `HISTORICAL_CONTEXT`, etc.);
- whether the record is raw evidence, a bounded fixture, or a derived conclusion.

Agreement across surfaces strengthens a behavioral conclusion. Disagreement must remain visible and should trigger source-specific investigation. Missing time ranges or unavailable sources are data gaps, not negative evidence.

## Critical anti-regression distinction

Existing Codex/Traycer extraction fixtures are **not** equivalent to complete local-log preservation. Likewise, a historical `availability: available` entry is **not** proof that a source is currently reachable.

The stack must keep these separate:

`source historically known` != `source currently reachable` != `raw corpus preserved` != `fixture coverage exists` != `behavioral conclusion proven`.

## Current next gap

Build/read-only adapters or import receipts for OpenCode and Command-Code first, then re-verify current Claude/Codex/Traycer local locations and coverage. Do not write to ChatGPT memory/personal context while doing this audit.
