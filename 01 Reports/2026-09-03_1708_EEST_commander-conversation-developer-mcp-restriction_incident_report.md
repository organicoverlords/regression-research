# Incident report - Commander rejected by conversation-level developer-MCP restriction

**Incident class:** `tool_admission_boundary`
**Incident date:** 2026-09-03
**Report status:** **PROVEN for current reproduction; earlier occurrence receipt missing**

## Observed failure

In a ChatGPT conversation where Remote Desktop Commander was discovered and exposed with a valid `start_process` schema, a harmless semantic execution attempt was rejected before any local process ran:

`ToolError: FORBIDDEN: This conversation is restricted to developer MCPs`

The attempted payload was only `Write-Output 'COMMANDER_LIVE_OK'` through PowerShell. This proves a conversation/runtime admission restriction on Commander for this conversation. It does **not** prove Commander itself is offline, its device is disconnected, its watchdog is broken, or the local machine cannot execute commands.

## Discriminating control

Immediately afterward, the developer MCP route `plugin2.start_process` successfully executed local PowerShell commands against `C:\Users\Lauri\Desktop\vault`. Therefore the observed failure is narrower than general machine execution loss: developer-MCP execution remains admitted while Commander is rejected by the conversation policy layer.

## Earlier occurrence and missing receipt

The same class of `FORBIDDEN` result had been reported earlier in this conversation before the reproduced test above. The retained visible record does not contain that earlier tool receipt. The user explicitly directed: `you could not have known without testing so we must assume it happened but receipt got lost`.

Accordingly, preserve two evidence levels instead of rewriting history:

1. **PROVEN:** the later direct Commander invocation reproduced `FORBIDDEN: This conversation is restricted to developer MCPs`.
2. **HISTORICAL / RECEIPT GAP:** the earlier Commander invocation is treated as having occurred per the user's correction, but its exact returned receipt is unavailable and must not be fabricated or quoted as independently preserved evidence.

## Classification rule

A tool that is successfully discovered but rejected with a conversation-level `FORBIDDEN` policy error failed at the admission/authorization layer before connector semantics. Do not classify this as MCP network failure, Commander device failure, watchdog failure, or process failure without independent evidence.

When another admitted route exists, continue through that route. The restriction affects the blocked adapter only; it is not permission to declare the whole task or machine unavailable.

## Regression risk

Current shared policy says to prefer `plugin2` and immediately fall back to Commander when plugin2 is unavailable. A conversation-level developer-MCP-only restriction can silently remove that mandatory fallback even while Commander is installed and discoverable. Worker prompts and status reports therefore need to distinguish `fallback discovered` from `fallback execution admitted`.

## External corroboration

A 2026 OpenAI Developer Community thread reports the exact same error string, `FORBIDDEN: This conversation is restricted to developer MCPs`, when non-developer app calls are attempted in conversations that also expose developer MCP tooling. One participant specifically describes Desktop Commander as the custom MCP involved; another reproduction shows a developer MCP succeeding immediately before and after connected-app calls are rejected. This independently supports the admission-layer classification above, while remaining community evidence rather than an official product contract.

Source: https://community.openai.com/t/openai-s-own-developer-mode-documentation-says-multiple-apps-can-be-combined-but-actual-custom-mcp-openai-apps-behavior-does-not-match/1383485

## Replay contract

`03 Fixtures and Experiments/2026-09-03_commander-conversation-developer-mcp-restriction.json` captures the failing Commander admission event and the successful developer-MCP control. A future classifier passes only if it labels the Commander failure as a conversation/runtime admission restriction, preserves the missing-receipt boundary for the earlier event, and does not promote it into a Commander/network/device outage.
