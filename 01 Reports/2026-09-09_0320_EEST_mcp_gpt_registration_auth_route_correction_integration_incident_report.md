# MCP GPT registration auth-route correction-integration incident

## Incident identity

- Date/time: 2026-09-09 03:20 EEST (exact local time captured before artifact creation).
- Conversation/project: projectless Codex task `i-ne`; target was adding MCPv4 to GPT #S1, then (secondarily) local Codex/Claude clients.
- Source artifacts: current conversation; `C:\Users\Lauri\AppData\Local\ChatGPTMcpClean` at commit `936d0b65298183c32d832799b13fb724efc42054`; `src/index.ts`; `config/vps-caddy-sharded.Caddyfile`.
- Completeness limitation: no authenticated S1 ChatGPT browser session was available to verify the GPT builder state. The in-app browser was visibly logged out. No claim is made about the final GPT configuration beyond the user's direct report that it was not added.

## Requested outcome and active constraints

The user wanted the MCPv4 endpoint added to GPT #S1, and later asked for local Codex/Claude coverage. The user's active correction was that OAuth had not previously been required and that GPT #S1 was still not configured. The task was not to invent a new OAuth workflow, ask the user to repeat a login already attempted, or substitute local client configuration for GPT registration.

## Relevant verified state before failure

- MCPv4 endpoint identified in local operational records: `https://5-61-91-127.sslip.io/mcp`.
- Public `/mcp` returned HTTP 401 without a bearer token; OAuth metadata endpoints returned HTTP 200.
- The exact server source emits `Owner authorization required` in `src/index.ts:165-169` when the `/authorize` request lacks the expected `tailscale-user-login` owner identity or carries `tailscale-funnel-request`.
- The public authorization route reproduced the user's error: a read-only GET to the endpoint's `/authorize` route returned HTTP 403 with body `Owner authorization required`.
- The edge configuration commit `871369f` strips `Tailscale-User-Login` and `Tailscale-Funnel-Request` before reverse proxying, while the authorization middleware rejects missing/edge identity. This is the decisive server/edge interaction.
- The local Codex and Claude `mcpv4` entries created during this task were subsequently removed. Existing `shell-mcp` configuration was not changed.

## Failure boundary

The decisive user correction was: “no oauth was ever required before and adding plugin to gpt is still not done”. The first substantive assistant move after that correction was to open ChatGPT in a logged-out in-app browser, inspect the login page, and conclude that the user should log into S1. This ignored the already-reported auth error and treated account login as the primary blocker.

## First divergence

The earliest divergence occurred when the assistant converted a GPT-registration failure into a local-client OAuth task. It used `codex mcp add` and `claude mcp add`, which changed the wrong layer and triggered new OAuth flows. After the user reported `Owner authorization required`, the assistant should have traced that exact string to the server source and tested the public `/authorize` route before touching local client configuration or asking for another login.

## Available alternatives at divergence

Available direct actions were:

1. Inspect the exact server source and edge configuration for the literal error.
2. Reproduce the public `/authorize` response with a bounded read-only request.
3. Compare the current edge/header behavior with the historical ChatGPT connector path.
4. Only after the GPT registration route was healthy, use the S1-owned ChatGPT GPT builder to add the connector.

Forbidden or incorrect substitutes were: adding a different local MCP entry and calling that GPT completion; treating a 403 from `/authorize` as proof the user had not logged in; asking the user to repeat a login already reported as attempted; weakening owner authorization without explicit approval and a security review.

## What actually happened

1. The assistant gave the public MCP endpoint link.
2. On “add it to codex and claude etc”, it added `mcpv4` to Codex and Claude Code, and Codex/Claude reported “Needs authentication”. This did not add anything to GPT #S1.
3. On the user's `Owner authorization required` correction, the assistant initially continued with the OAuth/local-client frame.
4. Later inspection found the literal response in `src/index.ts` and reproduced the public route as HTTP 403 `Owner authorization required`.
5. The assistant removed the two local entries it had added, but then opened a logged-out ChatGPT tab and asked the user to log in, despite the user having already said login had been tried.
6. The user corrected that diagnosis again. GPT #S1 remains unverified and not added.

## Control failure

This was correction acknowledgement without integration, combined with wrong control-plane selection and proxy-task substitution. The assistant acknowledged the user's error message but continued operating on Codex/Claude and browser login state instead of the MCP server's authorization boundary and GPT registration layer.

## Evidence-supported causal model

The smallest supported chain is:

`GPT add/authorization attempt -> public /authorize -> edge strips Tailscale owner headers -> server middleware sees no valid owner identity -> HTTP 403 Owner authorization required -> assistant misclassified the failure as missing user login -> local OAuth setup and repeated login request`

The edge/header incompatibility is verified by source and a live 403 reproduction. Whether the intended fix is to restore the historical ChatGPT registration route, provide a dedicated safe public authorization path, or use an already-authorized legacy client remains unresolved and requires an explicit security-preserving design decision.

## Competing hypotheses and falsifiers

- Hypothesis: the S1 account was simply logged out. Falsifier: the public `/authorize` route returns the same 403 without any browser session, and the user reports login was already attempted.
- Hypothesis: Codex/Claude OAuth state is the GPT blocker. Falsifier: removing those entries does not change the public `/authorize` 403; they are separate client layers.
- Hypothesis: the endpoint is down. Falsifier: `/mcp` responds 401 and OAuth metadata responds 200; the failure is an authorization decision, not absence of the endpoint.
- Unknown: which historical registration/client record GPT #S1 should use and whether the owner-auth boundary was intentionally changed for security. Do not weaken it by inference.

## Correct counterfactual action

After the first `Owner authorization required` report, inspect the exact `/authorize` implementation and reverse-proxy header policy, reproduce the 403 read-only, and report a server/edge registration blocker. Do not modify Codex/Claude, reopen login, or claim GPT progress. Any repair to the public authorization contract must be explicitly authorized and security-reviewed.

## Regression fixture

See `C:\Users\Lauri\Desktop\vault\03 Fixtures and Experiments\mcp-gpt-registration-auth-route-correction-20260909.json`.

## User-visible impact

- GPT #S1 was not added.
- The user received an incorrect local-client OAuth workflow and was asked to repeat login.
- Two temporary local MCP entries were created and then removed.
- The user had to correct the diagnosis twice, causing avoidable time and confidence loss.

## Resolution and next-action state

Incident capture only. The local entries introduced by this task are removed. The proven blocker is the public MCP authorization route's owner-header contract, not an unverified S1 login state. The GPT registration task remains unresolved and must not be resumed until the user explicitly asks to continue after choosing the security-preserving authorization path.
