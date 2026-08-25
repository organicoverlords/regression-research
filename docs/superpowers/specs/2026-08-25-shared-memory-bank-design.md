# Shared Memory Bank Design

**Date:** 2026-08-25  
**Issue:** #10  
**Status:** Proposed / approved in chat for specification

## Purpose

Replace the fragile bootstrap-seed model with a lightweight shared memory journal that preserves useful continuity without making ChatGPT, MCP, Library, browser automation, or any external retrieval surface a prerequisite for correct basic behavior.

The bank is not a transcript archive and not a second policy engine. It is a compact, append-only, Git-backed history of durable facts, decisions, lessons, corrections, preferences, and status changes that may be useful after conversational context is lost.

## Design principles

1. **Current user instruction wins.** Memory informs execution; it never overrides an explicit current instruction.
2. **No bootstrap dependency.** Failure to reach the bank must reduce historical context only. It must not disable normal reasoning or work.
3. **Append, do not rewrite history.** Corrections and changed facts supersede older entries while preserving provenance.
4. **Small entries, rich pointers.** Store the durable conclusion and tags; point to incidents, commits, issues, artifacts, or transcripts rather than embedding them.
5. **Evidence classes remain distinct.** Proven fact, provisional hypothesis, and rejected belief are represented explicitly.
6. **Routine memory is lightweight.** Full-conversation capture is exceptional regression/forensic evidence, not a per-session requirement.
7. **One shared history.** ChatGPT, MCP workers, local agents, and future tools read the same bank. No independent copies are allowed to silently diverge.
8. **Git is the audit/recovery layer.** The working bank is readable as a normal file; Git preserves change history and recovery.

## Canonical location

The first implementation lives in `organicoverlords/regression-research`, because Regression Research already owns incidents, evidence, fixtures, and operating contracts that justify behavioral lessons.

Canonical files:

- `memory/memory-bank.jsonl` — append-only journal.
- `memory/memory-bank.schema.json` — machine-readable entry schema.
- `memory/README.md` — human contract, retrieval rules, and contribution rules.
- `memory/sources.json` — versioned inventory of migration/evidence sources and their role. This is not injected into normal recall.

The old `chatgpt-memory-seed.md` is not canonical for the new system. It becomes one migration source and later a legacy/recovery artifact.

## Entry model

Each JSONL record is independently readable and immutable after commit except for emergency syntax repair. Semantic changes are represented by a later entry.

Required fields:

```json
{
  "id": "mem-20260825-<stable-random-id>",
  "timestamp": "2026-08-25T11:30:00+03:00",
  "kind": "fact|decision|lesson|preference|status|correction",
  "scope": "global|p3|tiny3d|mcp|aitube|<project>",
  "tags": ["short", "searchable", "terms"],
  "text": "One compact durable statement.",
  "state": "PROVEN|PROVISIONAL|REJECTED",
  "evidence": ["github:repo#issue", "commit:sha", "incident:INC-..."],
  "supersedes": []
}
```

Optional fields may include `expires_at` for genuinely time-bound memories and `project` when a scope spans multiple subprojects. No credentials, secrets, raw transcripts, huge logs, or temporary tool output belong in entries.

## Semantics

### Kinds

- `fact`: durable observed fact worth recalling later.
- `decision`: a choice that constrains or explains later work.
- `lesson`: a behavior/control learned from a regression or repeated failure.
- `preference`: stable user preference explicitly established by the user.
- `status`: durable project state likely to matter across conversations.
- `correction`: explicit correction of an earlier memory or rule.

### States

- `PROVEN`: directly supported by cited evidence or explicit current user instruction.
- `PROVISIONAL`: useful working hypothesis not yet sufficiently verified.
- `REJECTED`: preserved historical belief known not to be valid.

A `REJECTED` entry is retained for search/audit but excluded from ordinary positive recall unless the query asks about history, mistakes, regressions, or superseded rules.

### Supersession

`supersedes` lists entry IDs replaced by the new entry. Search should prefer the newest non-rejected descendant. The older entry stays in Git and JSONL so workers can understand how a rule or status changed.

Supersession is semantic, not destructive. There is no general in-place edit path for changing meaning.

## Retrieval

The first implementation deliberately avoids embeddings, databases, daemons, web automation, and model-based ranking.

A query uses:

1. exact `scope` match when supplied;
2. exact tag matches;
3. case-insensitive token/text matching;
4. recency as a tie-breaker;
5. supersession filtering;
6. `PROVEN` over `PROVISIONAL`; ordinary recall excludes `REJECTED`.

Default result count is small (target 3–8 entries). Retrieval should return the entry plus enough provenance to inspect deeper evidence only when needed.

Typical requests:

- recent entries for `scope=p3` and tag `chain-lightning`;
- recent `mcp routing` lessons;
- exact entry by ID;
- history including superseded/rejected entries;
- entries changed since a commit/time.

This is intentionally analogous to `git log --grep`, not a knowledge graph.

## When recall happens

Do not query the bank mechanically on every turn.

Recall is appropriate when:

- the user refers to prior work and current context does not resolve the referent;
- historical project state materially affects the task;
- the user explicitly asks what was decided/remembered;
- a worker resumes after losing context;
- a regression investigation needs prior lessons or corrections.

If current conversation context already supplies the answer, do not add retrieval latency or noise.

## Writing policy

A normal work session should add zero to a few entries, not a transcript-sized summary.

Good write triggers:

- a durable user correction or preference;
- a project decision that future workers must know;
- a material status transition (e.g. implementation proven, runtime proof still pending);
- a regression lesson that changes future behavior;
- a hypothesis being proven or rejected;
- an external memory contract/routing fact that is stable enough to outlive the current session.

Bad write triggers:

- every tool call;
- ordinary conversational detail;
- temporary process IDs or ephemeral machine snapshots;
- raw logs/transcripts already preserved elsewhere;
- speculative conclusions without a `PROVISIONAL` state;
- duplicated prose from repo docs.

## Source systems and what to reuse

### Regression Research — behavioral authority/evidence

Reuse incident reports, replay fixtures, and operating contracts as sources for `lesson`/`correction` entries. The bank does not replace Regression Research; it points back to it.

### AITubeTranscript — contract/version patterns

Reuse the ideas of stable-memory boundaries, explicit contract versions, stale-memory detection, durable-vs-volatile separation, and promotion of a best verified snapshot. Do not import YouTube-specific routing or API state.

### Level6 Memory — capture/recall hooks as optional future integration

Reuse the before-turn/after-turn abstraction and current-instruction-wins rule. The first bank implementation does not require the Level6 service or any daemon.

### ForgeStack — bounded context principles

Reuse the idea that historical context must remain bounded and visible when compacted. Do not inject the full bank into prompts.

### Agent Zero — simple procedural-memory primitives

Potentially reuse minimal kind/key/value mental models only where they simplify APIs.

### ContextRelay — explicitly not a runtime dependency

ContextRelay may remain a forensic/archive source, but its web-conversation routing/automation is outside the core memory-bank architecture. The bank must work without it.

## Initial migration

Migration is a one-time curation pass, not a dump.

Candidate sources:

- current `chatgpt-memory-seed.md` and existing durable memory exports;
- Regression Research operating contracts and incident conclusions;
- AITube `GPT_MEMORY.md` / `MEMORY_BANK.md` stable rules;
- Level6 stable memory contracts;
- verified current project facts from P3/Tiny3D/LowVRAM where cross-chat continuity is useful;
- other repo memory artifacts discovered during inventory.

Migration procedure:

1. extract candidate durable statements;
2. classify `kind`, `scope`, tags, state, and evidence;
3. collapse duplicates into one entry with multiple evidence pointers;
4. preserve conflicting historical claims as separate entries;
5. mark disproven claims `REJECTED` and link replacements with `supersedes`;
6. avoid importing transient paths/SHAs/process state unless they are themselves durable references;
7. validate JSONL/schema and run retrieval checks against known historical questions.

No source file is deleted during migration.

## Durable ChatGPT memory boundary

ChatGPT's always-present durable memory should remain much smaller than the external bank. It should contain only universal behavior that must work with zero tools plus the stable fact that the external memory bank exists and may be queried when historical context is needed.

It must not contain a command that requires reading the bank at conversation start. Bank retrieval is optional enrichment, not bootstrap.

External policy such as repo `AGENTS.md` remains authoritative for repo-specific work when inspected. The bank records historical knowledge; it is not allowed to silently override current repo policy or live evidence.

## MCP and worker access

MCP/local workers need no special memory service initially. They can read/search the Git checkout directly using a small CLI. This keeps the bank recoverable even if MCP routing itself is degraded: another worker with repo access sees the same committed history.

Future integrations may expose the same CLI through MCP, Level6, or other apps, but they must remain readers/writers of the canonical journal rather than independent memory stores.

## Failure behavior

- Bank unavailable: continue with current context and applicable policy; do not treat this as a bootstrap failure.
- Search returns nothing: say historical context was not found; do not invent it.
- Conflicting entries: prefer current user instruction/live evidence; otherwise surface the conflict rather than merging claims silently.
- Stale external contract: mark the old routing/status entry superseded or provisional; never let stale memory override validated current layout.
- Corrupt JSONL: stop writes, use Git to recover/repair syntax, preserve the corrupt artifact as evidence if meaningful.

## Validation and regression tests

The implementation should include automated tests for:

- schema validation and one-entry-per-line parsing;
- UTF-8 text/tags;
- tag/scope/text/recency ranking;
- supersession filtering;
- `REJECTED` exclusion from ordinary recall;
- history mode including superseded/rejected entries;
- duplicate migration collapse;
- conflicting migration claims preserved rather than overwritten;
- no mandatory bank read on startup;
- known regression questions retrieving the expected compact entries.

A practical acceptance fixture should include queries such as:

- “what did we learn about MCP safety blocks?”
- “what happened with Chain Lightning?”
- “what was the anti-churn rule?”
- “which old MCP size/path theories were rejected?”

## Non-goals for v1

- semantic embeddings/vector DB;
- autonomous LLM rewriting of existing memories;
- full-conversation capture on every session;
- web-browser automation for recall;
- replacing Regression Research evidence;
- replacing repo `AGENTS.md`/project policy;
- making Level6/ContextRelay/MCP a startup dependency;
- automatic deletion/garbage collection of historical entries.

## Rollout

1. implement schema, validator, append command, and search command;
2. seed a curated initial bank from existing sources;
3. verify retrieval against known historical questions;
4. expose the same repo/CLI to MCP/local workers;
5. only then update the small durable ChatGPT memory pointer/contract;
6. observe real use before considering indexing or automated after-turn writes.

The design intentionally favors inspectability and graceful failure over sophistication.
