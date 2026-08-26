# Regression Research

<!-- CHANGELOG-LANDING:BEGIN -->
## Project timeline

Canonical history: [CHANGELOG.md](CHANGELOG.md)

- [2026-08-27] Normalized the append-only memory corpus by collapsing four stale/duplicate clusters through supersession, added a derived exhaustive audit over all bank plus candidate-only records, reconciled an incoming unindexed incident report, and made committed audits self-identifying point-in-time source receipts so later appends cannot masquerade as part of an older snapshot (#87).
- [2026-08-27] Extended the `slopwall` corpus with four timestamp-bound prior-turn occurrences, raising the confirmed lower bound to 16 lexical occurrences and 12 corrective interventions while keeping incomplete contexts unscored (#89).
- [2026-08-26] Expanded the `slopwall` study to separate literal lexical occurrences from canonical corrective interventions, including recent-history and meta-reference accounting without guessing weak-evidence scores (#89).
- [2026-08-26] Fixed canonical memory Git synchronization to decode Git subprocess output as UTF-8 on Windows, preventing encoding-only identity conflicts, and made manual changelog verification compare non-main refs with `origin/main`.
- [2026-08-26] Added a dedicated Windows Actions runner, per-branch concurrency cancellation, and a manual dispatch path so duplicate or stalled changelog checks cannot starve the queue (#76).
<!-- CHANGELOG-LANDING:END -->

Evidence bank for assistant behaviour regressions: what went wrong, what the correct
next move was, and enough preserved state to replay the case later.
This is research evidence. It is not an operating contract and not a worker prompt.
Operating rules live in each project's `AGENTS.md`, generated from
`C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md`.

## Layout

| Directory | Holds |
|---|---|
| `01 Reports/` | Incident reports — PRIMARY and SECONDARY, sharing one immutable incident id |
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
