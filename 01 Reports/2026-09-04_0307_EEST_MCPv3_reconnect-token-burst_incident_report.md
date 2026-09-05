# MCPv3 03:07 EEST reconnect and token-burst incident

**Date:** 2026-09-04
**Severity:** High
**Status:** Open - transport anomaly proven; initiating/root cause layer not yet proven

## Summary

At approximately 03:07:53 EEST, the production MCPv3 backend remained alive while several established MCP connections closed nearly simultaneously, a new connection set opened immediately, and multiple `/token` requests arrived within milliseconds. Existing process state survived and later reads could reassociate to prior process IDs.

The evidence does **not** prove the phrase "token-refresh collision" as a literal backend error. It does prove a tightly clustered authentication/reconnection event at the same time as the user-visible MCPv3 interruption.

## Primary live evidence

Production transport log:

`%LOCALAPPDATA%\ChatGPTMcpClean\minimal-connectors\clone-a\transport.jsonl`

Production OAuth state:

`%LOCALAPPDATA%\ChatGPTMcpClean\minimal-connectors\clone-a\oauth.json`

Production backend at investigation time:

- listener: `127.0.0.1:3011`
- server PID: `5604`
- process start: `2026-09-03 21:48:48.667 +03:00`
- process stayed alive across the 03:07 incident window

## Incident timeline

Times below are EEST unless otherwise noted. Log timestamps are UTC and were converted by adding +03:00.

1. **03:07:52.809** - existing MCP `read_output` request starts for caller `caller_a9cd46865b3f`.
2. **03:07:52.852** - existing process `3af0ff3c-b781-485d-9be6-b31cb28907ee` is read successfully; `running=false`, `reassociated=false`.
3. **03:07:52.858** - that `read_output` response finishes HTTP 200 in 49.258 ms.
4. **03:07:52.891** - `/token` request begins on connection `connection_6c7050c120a1`.
5. **03:07:52.933** - token request returns HTTP 200.
6. **03:07:52.999-03:07:53.923** - four established connections close nearly together. Their recorded lifetimes were approximately 7.2, 12.5, 18.7, and 7.7 minutes.
7. **03:07:53.923-03:07:53.985** - seven new TCP connections open to local port 3011 within about 62 ms.
8. **03:07:54.811-03:07:54.830** - five `/token` POST requests begin within about 19 ms. All recorded responses are HTTP 200.
9. **03:07:54.832** - production `clone-a\oauth.json` LastWriteTime is updated, effectively coincident with the token burst.
10. **03:07:55.885** - MCP `initialize` succeeds HTTP 200 on one of the new connections.
11. **03:07:55.909** - an existing process is read successfully after reconnection.
12. **03:07:56.147** - process `8ac3919e-8331-43f7-bac5-647c4ae4ba32`, originally owned by another caller identity, is read successfully with `reassociated=true`.
13. Subsequent `start_process` and `read_output` traffic continues successfully on backend PID 5604.

## What is proven

- The production MCPv3 backend did not restart during this event.
- The production 3011 transport was serving HTTP 200 immediately before and immediately after the event.
- Multiple established connections closed in a tight cluster.
- Seven replacement connections opened immediately afterward.
- Five `/token` requests occurred in a ~19 ms burst.
- The production OAuth state file changed at the same boundary.
- MCP initialization recovered within roughly three seconds.
- Process receipts/state survived the connection transition and at least one later read explicitly used `reassociated=true`.

## What is not proven

- A backend `invalid_grant` or `Invalid refresh token` response. None was found in the inspected production transport window.
- A 401/403 backend authentication failure in the incident window.
- That the backend itself emitted or recognized an error named "token-refresh collision".
- Whether the initiating event was ChatGPT/client connector behavior, upstream edge behavior, network/session teardown, OAuth client refresh behavior, or another layer upstream of the production backend.
- Whether all five token requests represented refresh-token grants; the transport log records path/status/timing but not secret-bearing request bodies.

## Additional anomaly: VPS reverse tunnel

`%LOCALAPPDATA%\McpVpsEdge\tunnel.log` contains repeated:

`TUNNEL_RETRY ChannelListenError: Failed to create remote TCP listener`

followed by later `TUNNEL_UP` records. However, that log has no per-line timestamps and its file LastWriteTime was from the prior evening. It cannot currently be tied to the 03:07 event and must not be presented as its cause.

At investigation time the public edge health endpoint reported healthy state, backend HTTP 200, metadata HTTP 200, Caddy active, and tunnel listener present.

## Debugging correction

The first investigation incorrectly searched stale/root transport surfaces and code paths before locating the live production 3011 transport log. That produced an incomplete conclusion.

For future MCPv3 incidents, start with Stack Atlas, resolve the current production owner, then inspect the exact production transport log around the user-visible timestamp before making a root-cause statement. Source inspection is secondary to the incident trail when runtime logs exist.

## Current diagnosis

Strongest defensible statement:

> At 03:07:52-03:07:56 EEST, production MCPv3 experienced a connection teardown/reconnect and authentication-token burst while backend PID 5604 remained alive. Existing process state survived and reassociated after reconnection. The initiating cause is not yet proven.

The user-visible phrase "token-refresh collision" is therefore **plausible shorthand for the observed refresh/reconnect cluster but is not a proven literal backend diagnosis**.

## Follow-up evidence needed on recurrence

1. Preserve the exact ChatGPT-side tool error and timestamp before retrying.
2. Correlate the caller/session/connection IDs against `clone-a\transport.jsonl` for the same second.
3. Record `/token` request count, status, and timing without logging credentials or request bodies.
4. Preserve edge/Caddy and tunnel events with timestamps for the same window.
5. Distinguish process survival/reassociation from transport/session survival.
6. Do not label the event a token-refresh collision unless a primary log or client error explicitly establishes that condition.
