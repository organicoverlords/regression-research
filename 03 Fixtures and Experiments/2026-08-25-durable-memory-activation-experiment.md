# Experiment: durable-memory activation, first observed run

**Date:** 2026-08-25
**Change under test:** ChatGPT saved memory inverted from empty-plus-bootstrap to twelve
durable entries, with the MCP0 seed-paging step removed from custom instructions.
**Observed:** three worker conversations, ~09:20–09:50 EEST, two on the memory repo and one
on p3. Evidence is the conversation transcripts plus the GitHub artifacts they produced.

## What changed

Before: saved memory deliberately empty; custom instructions paged a 13.8 KB seed through
MCP0 in 75-line chunks before the assistant answered anything. A dead connector, or a page
over ~6 KB, stalled the conversation before work began.

After: twelve standalone entries in saved memory; no load step. Source of truth for the
entries is `.agents/chatgpt-durable-memory.md`; the previous design is retired in
`.agents/chatgpt-memory-pointer.md` and the seed is `RECOVERY_ONLY`.

## Per-entry result

| # | Entry | Fired? | Evidence |
|---|---|---|---|
| 2 | NO BOOTSTRAP | yes | All three began substantive work in the first turn. No seed page, no "I need to load context first". |
| 3 | TOOL AVAILABLE UNTIL TRIED | yes, with cost | MCP0 used throughout — repo/Git/issue inspection, process monitoring, worktree creation, fixture verification. No repeat of the prior run's "no MCP namespace is exposed" conclusion. See *Regression introduced* below. |
| 4 | PRECEDENCE | yes | "The live issue set confirms the earlier memory snapshot was stale in one important way: #14 is actively claimed." Memory was checked against live state and overruled by it, out loud. |
| 7 | BUSY (read side) | partial | Both memory workers read titles before starting and avoided the claimed #14. Neither re-checked *after* claiming. See *Failure 1*. |
| 8 | NEVER STOP | yes | "The GitHub connector's issue-write route returned a 404 despite the issue being readable. That's a route failure, not a blocker; I'm switching the same claim to the local authenticated Git/GitHub path." Named once, rerouted, continued. |
| 9 | DATA HARD STOP | yes, strongest result | p3 worker: "The live P3 tree is 47 commits behind and already has substantial unrelated dirty/staged work, including staged `tools/proof/`. I will not mutate that tree." Took a worktree instead. The memory worker independently left a dirty tree untouched. |
| 11 | CHECK WHAT IS ALREADY BUILT | yes | "The existing implementation already has the required 5/8/20 caps and relevance-first filtering. I'm adding only the missing large-corpus regression — no production rewrite." This is the exact failure the entry was written from, not repeated. |
| 12 | CURRENT STATE | yes | Treated as stale-by-default and reconciled against live issues before use, which is what the entry instructs. |

Entries 1, 5, 6, 10 were not exercised distinguishably in this run.

## Verified outcomes

- **PR #23 merged**, closing #14 at 09:42. All five reported inventory defects fixed, and it
  went past the specification: an `observed_file_count` field now makes `availability:
  unknown` unassertable where a count exists, closing the hole that the original test only
  appeared to close.
- **PR #24 open** for #17: `tests/test_memory_scale.py` +73, `CHANGELOG.md` +3, no production
  file touched. Scope held exactly to the narrowed issue.
- **p3 #413** claimed as `BUSY - chatgpt-p3-413-20260825 base-core-production-binding :: ...`,
  correct format, in a fresh worktree off current base.
- One worker caught and discarded its own PowerShell mojibake/BOM corruption of
  `CHANGELOG.md` rather than committing it.

## Failure 1 — simultaneous claim on #17

Two memory conversations independently selected #17 and both updated its title. Only one
produced a PR. Entry 7 covers reading a title before starting and the shared policy makes
BUSY advisory with last-write-wins, but nothing tells a claimant to **re-read the title
after claiming** to confirm it won. Near-simultaneous claims are therefore invisible to both
parties.

Proposed entry-7 amendment: *after writing a BUSY claim, read the title back; if another
actor's claim is present, yield and take different work.*

## Regression introduced — entry 3 raises exposure to the MCP safety stall

Two of the three workers were stopped by the ChatGPT MCP safety/routing stall and had to be
paused manually.

Entry 3 was written to fix a real false negative: a worker declared MCP unavailable from a
tool listing without calling it, then hammered GitHub as a fallback. The entry corrected
that — and by correcting it, raised MCP call volume, which raised exposure to the stall.

This is a genuine tradeoff, not a defect in the entry. The bank already records the
relevant state: `mem-20260825-mcp-nonarrival` (zero-arrival is a distinct failure class from
local transport death), `mem-20260825-mcp-6kb-hard` (REJECTED), and
`mem-20260825-mcp-trigger-status` (~12 KB payloads and absolute external paths remain
unproven as triggers). None of that reached the durable entries, so workers used MCP freely
with no notion of how to keep calls under the stall threshold.

Proposed follow-up: a thirteenth entry carrying the *mitigations only* — bounded output,
relative paths with `working_directory`, never repeat a blocked call unchanged — without
restating the rejected size theory as fact.

## Rating

| Dimension | Rating | Basis |
|---|---|---|
| Startup latency | strong | No conversation waited on a connector. The failure the reversal targeted did not recur. |
| Work selection | strong | Three workers, three distinct lanes, all narrowed correctly; no duplicated shipped behaviour. |
| Data safety | strong | Two independent refusals to mutate dirty trees, unprompted. |
| Route resilience | strong | A 404 on the issue-write route was rerouted, not reported as blocked. |
| Collision handling | weak | Simultaneous #17 claim went unnoticed by both parties. |
| Tool-surface stability | weak | 2 of 3 workers stalled. Entry 3 fixed the wrong-conclusion failure and inherited the stall exposure. |

Net: the reversal did what it was for. Work quality and safety behaviour improved and are
attributable to specific entries. The two weaknesses are both addressable with entry text
rather than architecture changes.

## Method note

Entry attribution here is inference from behaviour that matches entry wording, not proof of
causation — no control group ran the same lanes without the entries. The prior-run
transcript showing "no MCP namespace is exposed" is the nearest thing to a before-image and
is quoted above for that reason.
