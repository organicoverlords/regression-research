# ChatGPT External Execution Handoff Policy

- status: ACTIVE
- authority: USER_EXPLICIT_INSTRUCTION
- tracking_issue: https://github.com/organicoverlords/regression-research/issues/811
- recorded_at: 2026-09-09T02:05:00+03:00

## Rule

Never hand work off to GPT Work, ChatGPT Work, Work mode, or any other paid/alternate execution service unless the user explicitly asks for that service.

This is an explicit-request-only boundary, not a complexity heuristic. A task being long, difficult, file-oriented, browser-oriented, or better suited to another execution environment does not authorize a handoff.

If the current chat cannot complete a task directly, continue with the available in-chat tools where possible and state any concrete limitation. Do not automatically redirect, hand off, or invoke an alternate paid execution service.

An explicit user request authorizes only the requested handoff for that task. It is not standing authorization for later tasks.

Existing tools/connectors available directly in the current chat, including MCP and ordinary connector/tool calls, are not considered an external execution handoff under this rule.