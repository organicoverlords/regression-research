# Shared Memory Bank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lightweight Git-backed shared memory journal with validated append/search/migration behavior and seed it from verified existing memory sources.

**Architecture:** A single UTF-8 JSONL journal is canonical. A small Python-stdlib CLI validates, appends, searches, and exposes history; migration is curated and evidence-linked rather than a source dump. Ordinary recall filters rejected/superseded entries and ranks exact scope/tag/text matches plus recency.

**Tech Stack:** Python 3 stdlib, JSON/JSONL, unittest, Git.

**Spec:** `docs/superpowers/specs/2026-08-25-shared-memory-bank-design.md`

## Global Constraints

- Current user instruction and live evidence always outrank recalled memory.
- Bank unavailability must never become a bootstrap/startup failure.
- No embeddings, vector DB, daemon, Level6, ContextRelay, browser automation, or MCP dependency in v1.
- Full transcripts/logs remain external evidence; bank entries stay compact and pointer-oriented.
- Existing source artifacts are never deleted during migration.
- Semantic corrections append new entries and use `supersedes`; committed history is not rewritten.

---

## File map

- `memory/memory-bank.schema.json` — normative entry schema/enums.
- `memory/memory-bank.jsonl` — canonical append-only journal.
- `memory/sources.json` — migration-source inventory/provenance.
- `memory/README.md` — contribution/retrieval/failure contract.
- `tools/memory_bank.py` — CLI + parser/ranking/append/history logic.
- `tools/migrate_memory_bank.py` — deterministic curated migration helper for prepared candidate records.
- `tests/test_memory_bank.py` — schema, UTF-8, append, ranking, supersession, rejected/history tests.
- `tests/test_memory_migration.py` — duplicate/conflict preservation and migration fixtures.
- `tests/fixtures/memory-candidates.jsonl` — small deterministic migration/retrieval fixture.

## Task 1 — Journal schema and validation

- [ ] Write failing tests for valid entry parsing, required fields, enums, UTF-8 tags/text, malformed JSONL, duplicate IDs, and invalid evidence/supersedes arrays.
- [ ] Run `python -m unittest tests.test_memory_bank -v` and verify RED for missing implementation/schema.
- [ ] Create `memory/memory-bank.schema.json` and minimal `tools/memory_bank.py validate` using only stdlib.
- [ ] Re-run focused tests and make them GREEN.
- [ ] Add `memory/README.md` with immutable-entry/supersession and failure-degradation rules copied from the spec.
- [ ] Commit: `feat: add memory bank schema and validator`.

## Task 2 — Append and retrieval semantics

- [ ] Write failing tests for append-generated IDs/timestamps, explicit IDs for migration, exact scope/tag/text ranking, recency tie-break, default exclusion of `REJECTED`, exclusion of superseded entries, and `--history` inclusion.
- [ ] Run focused tests and verify RED on missing commands/ranking.
- [ ] Implement `append`, `search`, and `history` subcommands in `tools/memory_bank.py`.
- [ ] Keep result output compact JSON by default, with optional readable text; cap default search results to 8.
- [ ] Re-run focused tests and full memory test module; verify GREEN.
- [ ] Commit: `feat: add memory bank append and search`.

## Task 3 — Curated migration and provenance

- [ ] Write failing migration tests: exact duplicate statements collapse with combined evidence; conflicting claims survive separately; replacement entries carry `supersedes`; rejected historical beliefs remain searchable only in history mode.
- [ ] Create `tests/fixtures/memory-candidates.jsonl` containing MCP size/path hypotheses, anti-churn rule, Chain Lightning status, and P3 fleet-convergence lesson.
- [ ] Run migration tests and verify RED.
- [ ] Implement `tools/migrate_memory_bank.py` as deterministic candidate-normalization/deduplication only; no LLM or automatic source scraping.
- [ ] Create `memory/sources.json` describing Regression Research, legacy seed/durable memory, AITubeTranscript, Level6, and verified project-state sources with roles and repository pointers.
- [ ] Re-run migration tests; verify GREEN.
- [ ] Commit: `feat: add curated memory migration`.

## Task 4 — Seed current known memory

- [ ] Build a reviewed candidate file from current verified material, keeping entries compact and evidence-linked.
- [ ] Include at minimum: executive/worker ownership; evidence-before-claims; research-after-first-unexpected-failure/anti-churn; current-instruction-wins; bank optional/not-bootstrap; MCP pre-dispatch non-arrival lesson with 6KB/path theories rejected/not-proven as appropriate; P3/Tiny3D/LowVRAM durable project status where still useful; Chain Lightning status; P3 issue #528 fleet convergence lesson; AITube stable memory contract facts.
- [ ] Validate every candidate state: `PROVEN`, `PROVISIONAL`, or `REJECTED`; do not promote inherited assistant claims without evidence.
- [ ] Run migration into `memory/memory-bank.jsonl` and run `validate`.
- [ ] Run acceptance searches: MCP safety blocks; Chain Lightning; anti-churn; rejected MCP size/path theories; P3 fleet hygiene.
- [ ] Inspect returned entries manually for compactness and correctness.
- [ ] Commit: `data: seed shared memory bank`.

## Task 5 — Integration proof and rollout boundary

- [ ] Add a smoke test that clones/copies only the repo and proves `tools/memory_bank.py search` works with no MCP/Library/daemon dependency.
- [ ] Run all unit tests and the acceptance searches fresh.
- [ ] Run `git diff --check` and validate JSON/JSONL files.
- [ ] Document exact MCP/local-worker usage as ordinary repo commands in `memory/README.md`; do not add an MCP-specific service.
- [ ] Update Regression Research issue #10 with commit IDs, test output, seeded entry count, and acceptance-search results.
- [ ] Push the feature branch and open a PR.
- [ ] Do **not** modify ChatGPT durable memory automatically in this code task; produce the compact durable-memory payload/pointer as a reviewed rollout artifact for the supported memory-write surface.
- [ ] Commit: `docs: prove memory bank rollout`.
