# Tool-context continuity incident 2 — 2026-08-26

Event time: **2026-08-26 18:44 EEST (+03:00)**

Related memory: this is a **separate second incident** to be associated with the latest local tool-context/context-drop memory when the canonical local bank is reachable again. The GitHub mirror may be behind that local memory, so this report intentionally does not rewrite `memory/memory-bank.jsonl` from stale GitHub state.

## What happened

While continuing the machine-wide cleanup/reconciliation work in regression-research #76/#85, ChatGPT still held the task/execution objective. The local execution surface changed underneath the active work: an MCP0 call reported the tool unavailable/disabled, and the Remote Desktop Commander fallback then timed out. GitHub remained available, so execution continued through GitHub rather than treating the task as finished.

The user asked whether ChatGPT had dropped the working context. ChatGPT first answered that the working context was still active, then clarified that the user meant **tool context**. ChatGPT initially attributed the loss too strongly to the local tool surface. When challenged — “are you 100% sure you did not drop it instead” — ChatGPT corrected the claim: there was no observed deliberate drop/close action, but the available evidence does **not** prove whether the platform/tool surface failed independently or whether assistant-side execution/context lifecycle behavior contributed to the tool-context loss.

## Evidence classification

- **PROVEN:** the cleanup/reconciliation task objective remained active and work continued through GitHub.
- **PROVEN:** MCP0 became unavailable/disabled at the point of retry; Desktop Commander fallback subsequently timed out.
- **PROVEN:** no explicit tool-context close/drop action was intentionally issued in the observable tool sequence.
- **NOT_PROVEN:** root cause of the tool-context loss. External connector/platform failure is plausible, but assistant-side context/tool lifecycle loss cannot be ruled out from the available evidence.
- **REJECTED:** the earlier categorical wording that the local MCP connection/tool surface simply “failed underneath” the task as if that cause were certain.

## Durable lesson

When a tool surface disappears during otherwise persistent execution, do not equate “no deliberate close action observed” with proof that the assistant did not contribute to the drop. Preserve causal uncertainty until primary lifecycle/server evidence distinguishes external tool failure from assistant/context lifecycle loss. Continue the task through a valid fallback when possible.

## Durability note

This report exists because the canonical local vault may contain newer memory entries than GitHub `main`. A stale GitHub mirror must never be used to replace the append-only bank. Reconcile this report into the latest related local tool-context memory as Incident 2 once the local vault is reachable, then push the resulting canonical memory commit to GitHub before handoff.
