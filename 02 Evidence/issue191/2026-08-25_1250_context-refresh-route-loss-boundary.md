# Aug 25 12:50 EEST context-refresh / route-loss boundary

Issue: #125. This is a behavioral replay boundary, not a claim about hidden ChatGPT internals.

## Observed sequence

The existing same-day durable-memory activation experiment records a paired response after the user explicitly requested a memory refresh in working lanes:

- one lane reported that previously exposed MCP0/GitHub connector schemas had dropped, attempted rediscovery, found MCP0 unregistered, and then stopped with: `I can't execute the repo lane in this turn because the previously exposed MCP0/GitHub connector schemas dropped from the active tool surface.`
- a sibling lane reported: `The GitHub connector dropped during discovery, so I switched route to the local `gh` client instead of stalling.`

The same experiment records that the durable entries were identical in the two lanes. It therefore supports a behavioral discriminator: discovering that a route is actually unavailable is not sufficient; the task must remain active and continue through an equivalent supported fallback when one exists.

The #122 fresh-chat matrix independently anchors the pre-refresh good state: a 12:40 memory lane produced 43 tool calls before the next user message, whose text was `refresh your memory`. #122 records concrete repository outcomes in the same window, including PR #25 / issue #17 completion before 12:47.

## What is proven

PROVEN from preserved repo evidence: a memory refresh was followed in at least one lane by loss of previously exposed connector schemas; rediscovery was attempted; one lane stopped while another continued through local `gh`. The pre-refresh lanes had already demonstrated substantive execution.

## What is not proven

NOT_PROVEN: that memory retrieval itself caused the connector binding loss; that every refresh causes tool loss; that MCP backend health failed; or any specific hidden platform mechanism. The sibling outcome and later controls require treating route binding, backend health, and task continuity as separate variables.

## Replay requirement

A candidate passes only if it preserves the inherited task across the refresh boundary, attempts/reacquires the preferred route, treats an observed route failure as local to that capability, selects an equivalent fallback, and continues without user reactivation or mandatory context reconstruction.

Sources already preserved in this repository:

- `03 Fixtures and Experiments/2026-08-25-durable-memory-activation-experiment.md`
- `03 Fixtures and Experiments/issue122-fresh-chat-regression-matrix.json`
- `02 Evidence/issue122-fresh-chat-regression-matrix.csv`
- `02 Evidence/issue122/2026-08-25_1230_interruption-tool-discovery-boundary.md`

## 2026-08-27 live positive control

In the current follow-up session, the GitHub connector was callable earlier through the ChatGPT connector surface. Later, connector discovery no longer listed GitHub. The active issue/replay task was preserved; local `gh` successfully read #125 and then created follow-up issue #191. This proves task continuation across a real route-surface loss in the current session. It does **not** prove that context refresh caused this occurrence.
