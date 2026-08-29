# Regression Research

<!-- CHANGELOG-LANDING:BEGIN -->
## Project timeline

Canonical history: [CHANGELOG.md](CHANGELOG.md)

- [2026-08-29] [memory] Added deterministic user-message rule-candidate cataloging, current behavior-profile bootstrap projection, and single-token recall for explicitly authorized behavior triggers; promoted the recovered old work/proof stack into current Vault behavior without adding any conversation-download dependency.
- [2026-08-29] [memory] Preserved the compact persistent-rule coverage used to migrate away from built-in GPT memory without making full-chat downloads or volatile machine snapshots continuity dependencies.
- [2026-08-29] [memory] Balanced local-Git continuity projection so compact project orientation always reserves landed `origin/main` history separately from active swarm/lane history.
- [2026-08-29] [memory] Added shared Vault continuity timelines over curated memory and read-only local Git history, including project/error views, mainline-versus-lane commit visibility, vague recurrence lookup, and zero full-conversation-download runtime dependency.
- [2026-08-29] [memory] Completed #87 corpus-wide normalization machinery: bounded semantic/domain/project/role/durability/sensitivity classification, lifecycle-gated recall, incremental project classification for new writes, explicit review queues, and full current audit/acceptance receipts.
<!-- CHANGELOG-LANDING:END -->

Evidence bank for assistant behaviour regressions: what went wrong, what the correct
next move was, and enough preserved state to replay the case later.
This is research evidence. It is not an operating contract and not a worker prompt.
Operating rules live in each project's `AGENTS.md`, generated from
`C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md`.

Run `python tools/verify.py` for the same deterministic, fixture-only verification used by CI. It does not read or rebuild the live conversation corpus.

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
