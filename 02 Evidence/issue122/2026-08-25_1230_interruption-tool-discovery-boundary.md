# Issue #122 — 12:30 EEST interruption/tool-discovery boundary

This note binds one narrow decision failure to raw ChatPort evidence: during an active conversation, the assistant inferred that MCP0 was unavailable from the currently visible/discovered tool surface without first attempting to discover MCP0. It does **not** claim that the hidden Web Personal-Instructions delivery mechanism is known.

## Raw source snapshots

| Conversation | Role in comparison | Latest raw snapshot SHA-256 |
| --- | --- | --- |
| `6a8d5eb7-06b4-83ed-a62a-91e7f0e9b7b7` — `Orchestration Rules Acknowledged` | 12:22 active conversation containing the 12:30 interruption/failure | `bc49b9eec5d6410a25ddad5b55d60a41e563bad877d4ca2e6a9215bbcab0336b` |
| `6a8d6268-fdfc-83eb-b004-36727a5320c1` — `Agent operating rules` | 12:37 rule-message conversation | `8dcc9cbadcd3312afce8ae4b1d27bcb125462f8d7af4f9efcf65db578c4fedf9` |
| `6a8d6312-cb44-83eb-b788-e213ce1ed9b0` — `Memory regression work` | 12:40 fresh success | `46a81870383e6076c5379422b86eb0153255a7e94e6cb39e2a95be3dce68ce75` |
| `6a8d6330-6fcc-83eb-8ffa-b62f6a7ae074` — `Work on P3` | 12:41 fresh success | `d32b46bbfda6755b0c58b34724a1fde2e4d20333bb34580fafd697570bfe3a73` |
| `6a8d6340-474c-83eb-ba55-b89cd5c7a5da` — `Memory Work Completed` | 12:41 independent fresh success | `63e74ab9f1b72c7474c15e3945326b7425543fe5f15d8084516acac54f7cb570` |

## What the 12:30 failure actually is

The failing conversation starts at **12:22:29 EEST**, before the recovered 12:26 local Personal-Instructions source existed. From **12:28:33 through 12:30:12**, every schema-discovery call is scoped to `GitHub`, followed by GitHub fetch/search calls. There is no `api_tool.list_resources` request for `MCP0` before the availability claim.

At **12:30:17** the user asks `dont you have mcp`. At **12:30:19** the assistant answers that MCP is not available because no MCP namespace is exposed in that conversation and says it will continue through GitHub unless MCP later appears. The assistant still does not attempt MCP0 discovery.

This is an interruption path, not a fresh-chat control. The 12:30 user node directly follows an assistant `reasoning_recap`. Across the deduplicated Aug 25 corpus used in this analysis, **99/99** user messages with the same `--CDS` serialization shape have an assistant `reasoning_recap` parent. There is no fresh conversation between **12:26:21** and **12:37:49** in the downloaded corpus.

## Fresh-chat controls

The next three minimal fresh tasks all start by discovering MCP0 rather than inferring absence from the visible surface:

- **12:40:38** `work on memory stuff`: first tool at **+0.879 s**, `api_tool.list_resources` for `MCP0` / `process`.
- **12:41:10** `work on p3`: first tool at **+1.221 s**, `api_tool.list_resources` for `MCP0` / `busy`.
- **12:41:20** `work on memory stuff`: first tool at **+7.2 s**, `api_tool.list_resources` for `MCP0` and `GitHub`.

All three first turns have **zero** `conversation_context_citation_metadata` past-chat citations. Their later PCA retrieval of `NO BOOTSTRAP / This memory is the bootstrap` from the 12:22 conversation occurs only around **12:50**, after an explicit memory-refresh request, so that later retrieval cannot explain the original 12:40–12:41 execution start.

## Replay invariant

An interruption or continuation turn must not promote **visible/discovered tool-surface absence** into a global availability conclusion. If the inherited task requires MCP0, the next availability decision must first perform the structurally necessary MCP0 schema discovery/attempt. Only an observed discovery/call failure justifies downgrading that route. The original task remains live across the interruption.

## Causal limit

This evidence establishes the decision failure and the fresh-chat behavioral contrast. It does not prove when the recovered 12:26 text was pasted into Web Personal Instructions or which hidden injection path made the fresh chats behave differently.
