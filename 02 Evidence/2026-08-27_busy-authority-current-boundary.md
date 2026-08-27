# BUSY authority current boundary — 2026-08-27

Status: **CURRENT POLICY RECONCILIATION EVIDENCE**

## Current rule

The current shared `AGENTS.md` policy makes the live MCP BUSY claim the single ownership authority for shared mutation scope.

GitHub issue-title BUSY markers are human-visible projections only. Branches, PRs, processes, comments, and other activity are evidence of work, but they do not create ownership by themselves.

If a GitHub BUSY projection has no matching live MCP claim, it is stale and must not block another worker. If coordination is unavailable, the system must not invent a second authority; read-only and independent work can continue while shared mutation waits for the real ownership surface.

## Historical evidence and supersession

`01 Reports/incident_report_2026-08-22_0238_EEST.md` preserves an earlier coordination migration in which stale title-centric documentation was incorrectly promoted to current authority. At that time, live issue comments and newer policy disproved the stale title rule.

That historical report remains useful for the mechanism — **stale coordination residue misread as live authority** — but its then-current statement that issue comments represented live coordination is not the present ownership contract. The 2026-08-27 shared policy has since made MCP BUSY the explicit single live authority.

## Regression boundary

The stack must preserve these distinctions:

- live matching MCP claim → authoritative ownership;
- GitHub BUSY title or other projection with matching claim → consistent projection, still not authority itself;
- GitHub BUSY title without matching claim → stale projection, non-blocking;
- branch/PR/process/comment activity without matching claim → evidence only, non-authoritative;
- two simultaneous live claims for the exact same scope → invalid/conflict state, never silently resolved by a projection;
- coordination unavailable → no invented fallback authority; continue read-only/independent work and defer shared mutation.

## Acceptance

A worker can determine whether it may mutate a shared scope from live claim state without interpreting stale titles, comments, branch names, or process activity as permission. A dead coordination route degrades locally rather than converting GitHub metadata into a substitute lock service.

Tracks issue #125.
