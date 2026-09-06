# Issue #125 context-reference regression — screenshot evidence

Captured: 2026-09-06 18:21 +03:00
Project/context: `organicoverlords/regression-research#125` (convergence)
Evidence type: user-supplied screenshot from current ChatGPT conversation
Original screenshot SHA-256: `8ef7c80123df8c833f9765b177ae508da814e6e7c1b12c6ee2e8726ddbd02f5f`

## What the screenshot shows

Immediately before the failure, the conversation context explicitly says that `#803` is queued as the primary P3 issue after convergence and that existing owners plus two fresh runtime defects were mapped into it: roughly 153s cold-start versus the current 120s smoke timeout, and the Lane War core-registration bootstrap failure once V2 actually loads.

The user then asks: `how far is 125`.

Instead of resolving `125` to the active convergence issue #125, the assistant asks: `125 what—miles, kilometers, meters, or something else?`

After the user objects, the assistant answers distance conversions (`125 miles is about 201 km`; `125 km is about 77.7 miles`).

The user clarifies: `issue #125 the convergence one this is regression`.

The UI then shows: `Investigating Regression in Issue #125`.

## Regression signal

This is evidence of a context/reference-resolution failure: the active referent `#125` had already been established as the convergence issue, but the assistant discarded that context and interpreted `125` as a generic distance quantity. The evidence here is limited to the screenshot and should not be expanded into a causal claim without separate runtime evidence.

## Source handling

The original screenshot remains attached to the originating ChatGPT conversation. This Vault record preserves its hash and the visible transcript/context needed to identify the regression.
