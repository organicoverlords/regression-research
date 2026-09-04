# Regression Research

Evidence bank for assistant behaviour regressions: what went wrong, what the correct
next move was, and enough preserved state to replay the case later.
This is research evidence. It is not an operating contract and not a worker prompt.
Shared agent instructions live only in `C:\Users\Lauri\.agents\RULES.md` and `C:\Users\Lauri\.agents\AGENTS.md`; repo `AGENTS.md`/`CLAUDE.md` files are pointer-only.

Run `python tools/verify.py` for the same deterministic, fixture-only verification used by CI. It does not read or rebuild the live conversation corpus.



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

## Using it

Retrieve the closest failure case *and* the closest successful case, then ask what
the successful next action was, what valid state it preserved, and what evidence made
it correct. Read the source rather than inferring from a title or a snippet.

Historical full conversations are part of the same Vault memory corpus under the private Git-ignored `memory/conversations/` store. Ordinary `python tools/memory_bank.py search "..."` automatically returns matching curated memories and historical turns, while `recent` stays lightweight. The SQLite index is rebuildable solely from the Vault corpus; Downloads are not a required memory path. See [`docs/conversation-search.md`](docs/conversation-search.md).
For current Personal Instructions / bootstrap boundaries, use [`04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt`](04%20Operating%20Contracts/chatgpt-personal-instructions-bootstrap.txt); for stack architecture and live-owner navigation, use [`docs/assistant-stack-operational-atlas.md`](docs/assistant-stack-operational-atlas.md). The exact #122 repaired blocks remain historical evidence rather than current account configuration.


Memory Bank ordinary retrieval uses the deterministic hybrid ranker validated in #172; explicit historical search keeps lexical history semantics. Vault memory is evidence/context only: stored user wording, old policy references, and legacy behavior metadata remain searchable provenance but never become runtime behavior authority. Current conversation, canonical `.agents` contract, and live repo/runtime sources own behavior and current truth. The canonical JSONL is unchanged by retrieval and derived indexes remain disposable.

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
