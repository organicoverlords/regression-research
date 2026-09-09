# ChatGPT Render Lite: browser RAM extension owner and navigation regression

Date: 2026-09-09 EEST
Status: FIXED_IN_SOURCE_RELOAD_REQUIRED
Keywords: Firefox, Brave, RAM plugin, RAM extension, ChatGPT Render Lite, render-lite, tab RAM, long conversation, chatgpt.com root navigation, conversation blank, aggressive pretrim

## Exact component

The Firefox/Brave RAM-saving plugin is **ChatGPT Render Lite**.

Canonical source repository: `https://github.com/organicoverlords/chatgpt-render-lite` (private)

Current source/install identities on KONE:

- Brave unpacked extension ID: `koodadgggieepgbmonhiijikfeijbfjf`
- Brave source / canonical repository checkout: `C:\Users\Lauri\Desktop\chatgpt-render-lite`
- Firefox development add-on ID: `chatgpt-render-lite@local`
- Firefox temporary-addon source mirror: `C:\Users\Lauri\Desktop\chatgpt-render-lite-firefox`
- Firefox canonical build inside the repository: `firefox-build/`

Do not diagnose this component as the MCP/ChatGPT plugin. Do not start with browser-wide Brave/Firefox repair. Locate this repository and its extension runtime first.

## User-visible regression

Reported symptom: while using a ChatGPT conversation, the tab could blank/navigate to plain `https://chatgpt.com/`; browser Back returned to the conversation.

The regression boundary was ChatGPT Render Lite v0.6.0's optional **Aggressive RAM pre-trim** mode. That mode injected page-world scripts at `document_start`, monkey-patched `window.fetch`, intercepted ChatGPT conversation GET responses, and returned a locally rewritten conversation graph with old nodes removed before React rendered it.

This was qualitatively different from the normal Render Lite RAM path. The normal path only marks cold DOM turns as rendering-sleep candidates and preserves ChatGPT's application state.

## Live evidence captured 2026-09-09

Brave extension-local storage for `koodadgggieepgbmonhiijikfeijbfjf` contains a configuration transition from:

`aggressivePretrim=false, pretrimTurns=6`

to:

`aggressivePretrim=true, pretrimTurns=6`

While that mode was active, Render Lite's own stored runtime telemetry recorded conversation/root transitions matching the symptom. Examples:

- `2026-09-09T12:16:04+03:00` -> `https://chatgpt.com/c/6aa123c4-680c-83eb-93b5-01b63de3f4aa`
- `2026-09-09T12:16:08+03:00` -> `https://chatgpt.com/`
- `2026-09-09T12:16:16+03:00` -> a conversation URL
- `2026-09-09T12:16:23+03:00` -> `https://chatgpt.com/`

Later runtime records also show `pretrimRemoved=2`, proving that response trimming was actually exercised.

The exact internal ChatGPT router decision is not directly observable from extension storage. The supported diagnosis is therefore: the response-rewriting pre-trim path is the regression boundary and the only Render Lite path that modified ChatGPT application data; its activation coincided with the reported root-route jumps.

## Durable repair

A new private GitHub repository was created to end the unversioned-Desktop-source failure mode:

- baseline commit `dc119e5` ÔÇö preserves the original v0.6.0 Chromium/Brave and Firefox builds for audit/history;
- fix commit `d8e01e1` ÔÇö v0.6.1 removes the conversation-response pre-trim runtime.

v0.6.1 changes:

- removes `page-pretrim.js`, `pretrim-core.js`, and `pretrim-config-bridge.js` from active source;
- removes all MAIN-world and `document_start` extension scripts;
- removes the Aggressive RAM pre-trim popup controls;
- strips legacy stored `aggressivePretrim` and `pretrimTurns` config keys in the background migration;
- preserves the ordinary DOM/render-sleep RAM optimization;
- moves the weekly send counter to DOM-observed new user-message IDs rather than ChatGPT API interception;
- keeps a source regression asserting the unsafe runtime surface is absent.

Static validation passed for Chromium/Brave and Firefox. Firefox source mirror hashes match the repository's `firefox-build/` for manifest/background/content/popup runtime files.

Canonical human-facing documentation and safety boundary live in `organicoverlords/agents@main`:

`docs/repos/chatgpt-render-lite/README.md`

Agents commit: `76137f5`.

## Safety invariant

**ChatGPT Render Lite may reduce RAM by suppressing layout/paint work for cold DOM, but it must never intercept, truncate, synthesize, or rewrite ChatGPT conversation API responses.**

It must also never navigate to the ChatGPT root, change browser history, or use automatic reload/navigation as a RAM-management mechanism.

A future RAM optimization that needs ChatGPT response rewriting is a design regression, not an optimization variant.

## Current activation note

The source trees are fixed, but already-injected browser extension code in currently open tabs does not become v0.6.1 merely because files changed on disk. Reload the unpacked extension / development add-on and reload affected ChatGPT tabs before claiming the running browser session is fixed.

Do not edit Brave LevelDB or Firefox profile state directly while the browsers are running just to force this migration; the v0.6.1 background migration owns removal of the legacy unsafe config after extension reload.

## Prior lesson reconciled

The 2026-08-21 Brave/ChatPort scope-regression report already established that a custom plugin problem should be traced to the plugin/update owner before widening into browser-level repair. This incident reinforces that lesson with a concrete canonical owner and repository.
