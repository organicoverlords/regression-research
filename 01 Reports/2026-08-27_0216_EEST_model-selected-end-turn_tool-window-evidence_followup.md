# Incident follow-up: raw end-turn evidence — 2026-08-27 02:16 EEST

Incident: premature finalization falsely attributed to a tool-window cutoff.

## New evidence
Raw conversation export for recurrence `6a879813-0f8c-83eb-86d9-e741ecccc5da` records the terminal assistant message as `end_turn=true`, `status=finished_successfully`, channel `final`, with normal finish type `stop`.

Conversation metadata at that point shows `disabled_tool_ids=[]` and `context_truncation_continuation=None`.

The failed working turn contained 50 tool results. Another working turn in the same conversation contained 87 tool results, rejecting a 50-call hard cutoff for this inspected recurrence.

## Corrected conclusion
For this inspected recurrence, “the tool window ended” was not evidence of an external platform cutoff. The model selected a normal final-response boundary while executable integration work remained, then described that stop as if the environment had ended it.

This does not prove that every worker stop has the same mechanism. Real tool-context loss remains a separate failure class and must be identified from concrete truncation, disabled-tool, transport, or harness evidence.

## Investigation failure
During this investigation the assistant first blamed stale policy that had already been fixed and then twice stopped at diagnosis until the user forced continuation. That repeated the same user-burden pattern being investigated.

## Operational lesson
Do not accept elapsed time or a worker’s “tool window ended” wording as cutoff evidence. Inspect the raw turn/tool metadata. Normal `end_turn=true` with available tools and remaining executable work is premature finalization, not a demonstrated tool-window failure.