# Regression Research

<!-- CHANGELOG-LANDING:BEGIN -->
## Project timeline

Canonical history: [CHANGELOG.md](CHANGELOG.md)
<!-- CHANGELOG-LANDING:END -->

Evidence bank for assistant behaviour regressions: what went wrong, what the correct
next move was, and enough preserved state to replay the case later.
This is research evidence. It is not an operating contract and not a worker prompt.
Operating rules live in `C:\Users\Lauri\Documents\agent-rules\RULES.md` plus the applicable `contexts\<project>.md`. Repository `AGENTS.md` files are pointer-only.

Run `python tools/verify.py` for the same deterministic, fixture-only verification used by CI. It does not read or rebuild the live conversation corpus.

Use `python tools/evidence_bundle.py create --output <manifest.json> <artifact...>` to bind regression proof to the current Git commit and artifact SHA-256 digests; `python tools/evidence_bundle.py verify <manifest.json>` re-checks that evidence read-only and rejects stale or tampered subjects.


## Layout

| Directory | Holds |
|---|---|
| `01 Reports/` | Incident reports â€” PRIMARY and SECONDARY, sharing one immutable incident id |
| `02 Evidence/` | Analyses, recovered rule records, provenance work |
| `03 Fixtures and Experiments/` | Replay-ready fixtures with scoring criteria |
| `04 Operating Contracts/` | Snapshots of contracts as they stood, for dating drift |
| `90 Raw Transcripts/` | Unchanged source exports |

## How a case is recorded

Each useful case is a paired behavioural model: the inherited objective and live
state, the first wrong substantive move, the user correction or falsifying evidence,
the correct next substantive action, the valid work that had to survive, the hard
exclusions on route and tool choice, the evidence that made the correction real, and
the actual completion condition.

Positive examples count. A case where the next move after a correction was right is
as useful as one where it was wrong, and both are needed to tell them apart.

## Fresh-session orientation and stable commands

The single fresh-session orientation entrypoint is `python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance`. It is a compact minimap, not product truth. It returns stable paths, concise defaults, exactly 20 recent memory titles, PC/disk pressure, recent worker utilization, and live MCP callers/activity including attributable Busy titles/scopes.

Stable follow-ups are intentionally boring: for any stack/infra work, consult Atlas before mutation?`stack_atlas.py lookup <id-or-alias>` for an exact owner, `stack_atlas.py find <query>` only when the exact stack name is unknown, and `stack_atlas.py blast-radius <id>` when shared dependents/routes may be affected?then leave Atlas for the live owner. Use `python -m tools.memory_bank context <query>` for targeted past decisions/attempts, `python -m tools.memory_bank timeline <query>` only when chronology matters, and `python tools\connector_reliability.py --last-hours 1` for compact MCP transport activity. `stack_atlas.py inventory` is a deep-audit command, never normal startup. Product repos remain their own live truth after orientation.

## Using it

Retrieve the closest failure case *and* the closest successful case, then ask what
the successful next action was, what valid state it preserved, and what evidence made
it correct. Read the source rather than inferring from a title or a snippet.

Historical full conversations are part of the same Vault memory corpus under the private Git-ignored `memory/conversations/` store. Ordinary `python tools/memory_bank.py search "..."` automatically returns matching curated memories and historical turns, while `recent` stays lightweight. The SQLite index is rebuildable solely from the Vault corpus; Downloads are not a required memory path. See [`docs/conversation-search.md`](docs/conversation-search.md).
For Personal Instructions / bootstrap / ChatGPT-memory provenance, use [`docs/assistant-stack-architecture.md`](docs/assistant-stack-architecture.md#personal-instructions-bootstrap-and-durable-memory-provenance). The exact #122 repaired blocks are historical evidence; the architecture doc separates them from current live account configuration and the lightweight Vault bootstrap.


Memory Bank ordinary retrieval uses the deterministic hybrid ranker validated in #172; audit/history keeps its lexical history semantics. CLI `search`, `history`, and `recent` output labels behavioral authority separately from relevance. A direct stored user `preference`, `decision`, or `correction` backed by `user-instruction:` is behavior-authoritative regardless of its factual claim state; the user does not have to prove an instruction. Live canonical policy/spec entries must be `PROVEN` before they can alter behavior. `USER_EXPLICIT` outranks `CANONICAL_POLICY`; everything else is `ADVISORY_EVIDENCE`, even when relevant or independently proven. User provenance authorizes behavior only and does not by itself prove hidden external causality. The canonical JSONL is unchanged by retrieval and derived indexes remain disposable.

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
duplicate/superseded report entries directly in the provenance index. Validate with
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
