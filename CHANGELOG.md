# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
The rule this file follows is `organicoverlords/docs` → `standards/changelog.md`.

## [Unreleased]

### Added

- An observed-incident-only regression taxonomy and coverage matrix distinguish
  eight mechanisms, link each row to preserved reports/fixtures and positive
  controls, and mark the pending task-anchor capture as a research gap (#6).

- A deterministic, provider-free replay scoring harness accepts supplied
  candidate actions, reports machine-readable and human-readable assertion
  results, and keeps pending-capture records out of scoreable fixtures (#3).

- Created machine-readable source provenance index (`provenance.json`) mapping every report in `01 Reports` to raw transcripts, evidence files, contract snapshots, dates, and evidence type, with explicit missing-link records, duplicate/superseded marking via `99 Duplicate Archive`, and a validator that detects broken paths and duplicate incident ids; no credential-bearing material is indexed (#5).

- Exposed the canonical changelog on the GitHub landing page and added CI enforcement for changelog and landing-page synchronization.

- Added optional ChatGPT durable-memory and personal-context adapter that imports a bounded fixture/export into curated candidates with DURABLE_MEMORY provenance, skips sensitive/unsupported material, and remains inert when the surface is unavailable; current explicit instruction still outranks recalled personal context via source-authority ranking (#19).

- Added deterministic heterogeneous memory-candidate extraction with bounded text, source provenance, conservative provisional state, and fixtures spanning agents policy, Regression Research, Codex history, and Traycer artifacts (#15).
- Indexed current shared policy separately from a historical v1.3 snapshot, so ordinary recall prefers LIVE_CANONICAL policy while history still exposes the superseded policy record (#20).
- Added deterministic 5,000+ candidate stress coverage proving bounded memory recall limits, relevance filtering, and routine runtime/memory use (#17).
- Source-authority conflict handling in memory migration: a supersession is honoured only when
  the claiming entry's source class ranks at or above the entry it supersedes, so a
  `RECOVERY_ONLY` seed claim can no longer silently remove `LIVE_CANONICAL` policy from ordinary
  recall. Every promotion, duplicate collapse and rejected supersession is recorded with its
  reason and both source classes, written by `--audit`.

- `NORTH_STAR.md`, naming the three live regression classes this corpus is currently tracking.

- `CHANGELOG.md`, adopting the org-wide changelog standard (`organicoverlords/docs` ->
  `standards/changelog.md`). Changes from 2026-08-24 onward get an entry here; history is
  not backfilled.

### Changed

- `AGENTS.md` shared policy raised to v1.2, adding a hard rail on deleting irreplaceable data
  (masters, assets, evidence) after an agent destroyed a set of masters, plus non-blocking
  defaults for disk reclaim, branch prune-on-merge, and full-target builds for anything CI or a
  runtime loads. The visual-proof gate is explicitly excluded from those relaxations.

- `AGENTS.md` shared policy raised to v1.1: a control plane, MCP included, is transport and
  visibility and never permission, so an unavailable connector can no longer be reported as
  the reason work did not start, and BUSY stays authoritative in the GitHub issue title.

<!--
Delete the headings you do not use. Keep this section at the top at all times.

To release:
  1. Rename this heading to `## [X.Y.Z] - YYYY-MM-DD`.
  2. Open a fresh empty `## [Unreleased]` above it.
  3. Update the link block below.

Entry style — one line, for a human, with the issue or PR number:
  - Sprint combat effects are now server-authoritative; clients can no longer apply
    damage locally (#494).
-->

[Unreleased]: https://github.com/organicoverlords/regression-research/commits/main
