# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
The rule this file follows is `organicoverlords/docs` → `standards/changelog.md`.

## [Unreleased]

### Added

- `CHANGELOG.md`, adopting the org-wide changelog standard (`organicoverlords/docs` ->
  `standards/changelog.md`). Changes from 2026-08-24 onward get an entry here; history is
  not backfilled.

### Changed

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
