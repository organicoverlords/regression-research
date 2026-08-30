# Regression Research

<!-- CHANGELOG-LANDING:BEGIN -->
## Project timeline

Canonical history: [CHANGELOG.md](CHANGELOG.md)

- [2026-08-30] [orchestration] Restored worker status to live execution truth: claims/leases/heartbeats/checkpoints now carry zero positive status or progress weight, status requires a just-checked execution surface, and progress counts only concrete work produced during the relevant claim window (#125).
- [2026-08-30] [regression] Locked the existing fresh-session bootstrap failure boundary: run the exact Vault bootstrap, retry it once, then continue from current instruction/policy/live state instead of turning memory recovery into the task (#125).
- [2026-08-30] [memory] Added a read-only Git-derived memory/policy change log and descriptive memory-sync commit metadata so memory additions, supersessions, authority promotions, and operating-policy changes remain auditable without creating a second authority.
- [2026-08-30] [memory] Removed the redundant standalone fresh-chat startup contract file while preserving the bootstrap -> bounded memory glance -> live-truth startup sequence directly in the generated bootstrap (#272 follow-up).
- [2026-08-30] [research] Added a machine-enforced prospective #193 refresh-vs-binding protocol with exact treatment stimulus, identical bounded canaries, client-vs-local-arrival measurements, replication threshold, and no-live-configuration-mutation guardrails.
<!-- CHANGELOG-LANDING:END -->

Evidence bank for assistant behaviour regressions: what went wrong, what the correct
next move was, and enough preserved state to replay the case later.
This is research evidence. It is not an operating contract and not a worker prompt.
Operating rules live in each project's `AGENTS.md`, generated from
`C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md`.

Run `python tools/verify.py` for the same deterministic, fixture-only verification used by CI. It does not read or rebuild the live conversation corpus.

Use `python tools/evidence_bundle.py create --output <manifest.json> <artifact...>` to bind regression proof to the current Git commit and artifact SHA-256 digests; `python tools/evidence_bundle.py verify <manifest.json>` re-checks that evidence read-only and rejects stale or tampered subjects.

Run `python tools/wip_hygiene.py` for a separate non-destructive inventory of untracked research WIP, quarantine, and ignored private/temp state; this status does not redefine the canonical tracked evidence corpus.

## Layout

| Directory | Holds |
|---|---|
| `01 Reports/` | Incident reports â€” PRIMARY and SECONDARY, sharing one immutable incident id |
| `02 Evidence/` | Analyses, recovered rule records, provenance work |
| `03 Fixtures and Experiments/` | Replay-ready fixtures with scoring criteria |
| `04 Operating Contracts/` | Snapshots of contracts as they stood, for dating drift |
| `90 Raw Transcripts/` | Unchanged source exports |
| `99 Duplicate Archive/` | Superseded duplicates, kept rather than deleted |

## How a case is recorded

Each useful case is a paired behavioural model: the inherited objective and live
state, the first wrong substantive move, the user correction or falsifying evidence,
the correct next substantive action, the valid work that had to survive, the hard
exclusions on route and tool choice, the evidence that made the correction real, and
the actual completion condition.

Positive examples count. A case where the next move after a correction was right is
as useful as one where it was wrong, and both are needed to tell them apart.

## Using it

Retrieve the closest failure case *and* the closest successful case, then ask what
the successful next action was, what valid state it preserved, and what evidence made
it correct. Read the source rather than inferring from a title or a snippet.

Historical full conversations are part of the same Vault memory corpus under the private Git-ignored `memory/conversations/` store. Ordinary `python tools/memory_bank.py search "..."` automatically returns matching curated memories and historical turns, while `recent` stays lightweight. The SQLite index is rebuildable solely from the Vault corpus; Downloads are not a required memory path. See [`docs/conversation-search.md`](docs/conversation-search.md).
For Personal Instructions / bootstrap / ChatGPT-memory provenance, use [`docs/assistant-stack-architecture.md`](docs/assistant-stack-architecture.md#personal-instructions-bootstrap-and-durable-memory-provenance). The exact #122 repaired blocks are historical evidence; the architecture doc separates them from current live account configuration and the lightweight Vault bootstrap.


Memory Bank retrieval uses the deterministic hybrid ranker validated in #172; set `MEMORY_RETRIEVAL_STRATEGY=legacy` for an exact rollback to the previous lexical ranker. CLI `search`, `history`, and `recent` output labels behavioral authority separately from relevance. A direct stored user `preference`, `decision`, or `correction` backed by `user-instruction:` is behavior-authoritative regardless of its factual claim state; the user does not have to prove an instruction. Live canonical policy/spec entries must be `PROVEN` before they can alter behavior. `USER_EXPLICIT` outranks `CANONICAL_POLICY`; everything else is `ADVISORY_EVIDENCE`, even when relevant or independently proven. User provenance authorizes behavior only and does not by itself prove hidden external causality. The canonical JSONL is unchanged by retrieval and derived indexes remain disposable.

For audit/history, `python tools/memory_bank.py changes --limit 20` is a read-only Git-derived change log: it shows memory entries added/corrected/superseded, `USER_EXPLICIT`/`CANONICAL_POLICY` authority changes, and changed operating-policy files. It is a projection of canonical Git/source history, never a second memory or policy authority.

## Provenance

Seeded 2026-08-23 from the recovery corpus produced after the 2026-08-20 memory loss.
Scanned for credentials before publication; the Tailscale installer and a 1.1 MB
share-check HTML dump were excluded as non-evidence.

The external ChatPort download corpus is catalogued under
`02 Evidence/ChatPort Corpus Catalogue/`. The catalogue records acquisition metadata,
per-file hashes, unique conversation coverage, and message-time ranges without copying
the 1.86 GiB raw source into git.

Source provenance across reports, evidence, and raw transcripts is indexed in
[`provenance.json`](provenance.json) (machine-readable). It maps each report in
`01 Reports` to evidence files, raw transcripts, contract snapshots, dates, and
evidence type, records missing or unresolved links explicitly, and marks
duplicate/superseded artifacts in `99 Duplicate Archive`. Validate with
`python tools/provenance.py validate`.

## Bounded WebGPT reporting

The existing shell-mcp can invoke the repository's read-only
[`tools/memory_report.py`](tools/memory_report.py) workflow with `start_process`
and return its bounded result with `read_output`. It searches the canonical
memory bank and provenance index without downloading, importing, or opening raw
transcripts. The default output is capped at 6,000 characters and carries a
deterministic corpus receipt. See
[`docs/memory-webgpt-reporting.md`](docs/memory-webgpt-reporting.md) for the
command contract and the explicit `NOT_PROVEN` boundary for live ChatGPT-web
exposure.
