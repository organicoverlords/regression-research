# Issue #122 — repaired MCP rule activation: local negative evidence

This note closes one bounded forensic question: whether the local machine and downloaded Aug 25 corpus retain a **direct witness** of which ChatGPT persistence surface made the repaired MCP-availability rule effective in fresh chats. They do not. This is a negative-result artifact, not evidence that the repaired rule was never applied.

## What is directly known

- At **12:26:21 EEST**, the bootstrap rewrite replaces `chatgpt-custom-instructions.md`. The merged provenance evidence in `02 Evidence/issue122/2026-08-25_1226-1237_rule-provenance.md` proves that this pre-repair state **did not contain** the MCP missing-tool safeguard.
- At **12:30:19**, direct ChatGPT exhibits that exact failure by inferring MCP absence from the visible surface.
- **Between 12:30:19 and 12:37:49**, an external-agent repair restores the MCP availability guard to custom instructions and adds durable-memory entry `A TOOL IS AVAILABLE UNTIL I HAVE TRIED IT`. The exact repair minute is not preserved.
- At **12:37:49**, the revised operating-memory text is visibly supplied in ChatGPT.
- The next genuinely fresh work chats begin at **12:40:38**, **12:41:10**, and **12:41:20** and immediately discover MCP0 as their first execution surface.
- The executable 12:30 interruption-specific replay is merged in PR #151.

## Local searches that produced no activation witness

### Browser navigation history

A copied read-only query of Chromium `History` databases for **12:15–12:50 EEST on Aug 25** found zero ChatGPT/OpenAI navigation rows in:

- Chrome `Default`: **0**
- Chrome `Profile 1`: **0**
- Edge `Default`: **0**

This is weak negative evidence because ChatGPT Settings/Personalization can be a modal/state transition inside an already-open SPA and need not create a history navigation.

### Persistent browser/app storage

A literal search for the **post-12:30 repaired custom-instructions state's** distinctive sentence `MCP0 is still your route to the machine` returned **0 hits** in the present local copies of:

- Chrome Default `Local Storage`, `Session Storage`, and `IndexedDB`;
- Edge Default `Local Storage`, `Session Storage`, and `IndexedDB`;
- `%LOCALAPPDATA%\ConnectedDevicesPlatform`;
- `%LOCALAPPDATA%\OpenAI`.

The normal `%LOCALAPPDATA%\Microsoft\Windows\Clipboard` and `%LOCALAPPDATA%\Microsoft\Clipboard` history directories do not exist on this machine, so there is no ordinary local clipboard-history store to inspect.

A recursive non-ChatPort Downloads text sweep was deliberately stopped after it became disproportionately expensive and had produced no result. No conclusion relies on that aborted sweep. No top-level Downloads archive whose filename indicated ChatGPT/export/conversation data was present.

### Raw conversation window

Searching the deduplicated Aug 25 raw corpus from **12:20–12:45 EEST** for `custom instructions`, `personal instructions`, `paste`, `pasted`, `applied`, `settings`, `instruction box`, and the local instruction filename yields no ChatGPT-side message that records the repaired custom-instructions text being applied in Web Settings. The 12:28:18 message only reports the earlier local bootstrap rewrite; the later external-agent provenance proves the MCP safeguard was restored after the 12:30 failure.

There is no fresh work conversation between the **post-12:30 repair interval** and the **12:37:49** `Agent operating rules` conversation that can isolate the repaired custom-instructions surface from the durable-memory/rule-message surface. The 12:37 export contains only four nodes: root, the large user rule message, `my name is Joonas`, and `Understood, Joonas.` There is no exported memory-write/tool node in that chat.

### First-turn context metadata in the good chats

The three fresh good chats have **0 `conversation_context_citation_metadata` citations in their first turns**. Their first tool actions are:

- 12:40:38 memory chat: MCP0 schema discovery at **+0.879 s**;
- 12:41:10 P3 chat: MCP0 BUSY schema discovery at **+1.221 s**;
- 12:41:20 independent memory chat: MCP0 + GitHub schema discovery at **+7.2 s**.

Those conversations later retrieve the 12:22 `NO BOOTSTRAP / This memory is the bootstrap` text through PCA around 12:50 after an explicit memory-refresh request. That later retrieval cannot explain why their first turns were already executing through MCP0.

## Conclusion

The exact **ChatGPT persistence/application event for the repaired MCP rule is not locally recoverable from the surviving evidence inspected**. The strongest defensible statement is therefore:

- 12:26 bootstrap rewrite without the MCP safeguard: confirmed by primary provenance;
- 12:30 direct failure matching that missing safeguard: confirmed;
- post-12:30 repair restoring the safeguard to custom instructions and adding durable-memory entry 3 before 12:37:49: confirmed;
- 12:37 revised rule visibly supplied in ChatGPT: confirmed;
- fresh-chat MCP0 discovery by 12:40:38: confirmed;
- direct proof that Web Personal Instructions, Saved Memory, or another specific hidden surface caused that first-turn behavior: **not found**;
- first-turn PCA retrieval from the visible 12:37 chat: not evidenced;
- another unexported injected-context mechanism: remains possible.

If the repaired custom-instructions text was the causal delivery mechanism, its effective application is bounded **after the post-12:30 repair and no later than the first fresh success at 12:40:38**. If durable memory or another surface caused the change, the same behavioral upper bound holds but the delivery event is different. Further local browser/cache/clipboard archaeology should not be repeated without a new source class or new artifact.
