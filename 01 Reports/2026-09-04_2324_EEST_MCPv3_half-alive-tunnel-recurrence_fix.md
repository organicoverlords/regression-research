# MCPv3 half-alive reverse-tunnel recurrence and durable owner fix — 2026-09-04 23:24 EEST

## Incident

The user reported that MCPv3 was obviously stalling again and asked for the Codex MCP fix to be repaired rather than waiting for another escalation.

This recurrence was real. The accepted backend itself had not regressed: Windows PID `5604` was still serving local port 3011 from exact accepted source commit `1fb6b8f8461aa07263fe23a24da4e1be1dd9428e`, with `dist/server.js` SHA-256 `7C2FD4BE29B79146935CBC4A9AF8DFE9C431407D31F14CC6FCECD4255E2565A5`. Direct local `/health` was normally about 14–16 ms.

The degraded owner was the VPS reverse-SSH forwarding path. The VPS health observer repeatedly timed out on the forwarded backend while the listener remained present. Examples in `mcp-edge-health.service` between 23:05 and 23:16 EEST included repeated 5-second and 8-second curl timeouts. At 23:11 EEST `/edge-status` reported `healthy:false`, `backend_http:000`, `metadata_http:200`, `caddy:"active"`, and `tunnel_listener:"yes"`.

That is the half-alive class: SSH/listener liveness existed, but the actual forwarded HTTP data plane was intermittently stalled.

## Why the old path failed

The restored production tunnel source was the original 927-byte implementation, SHA-256 `03D2D3E905884573897C84D66C1E07EDF32F4F0E9AC07D4C841AA6DEE56A645D`. Its recovery loop waited for `conn.wait_closed()` and therefore reacted to SSH session closure, not to a remote forward whose listener/session stayed alive while forwarded traffic stalled.

Codex had previously built and off-path-tested a data-plane watchdog, but the deployment path restarted production directly, produced a public 502 interval, and was followed by the known ChatGPT-side direct-MCP namespace/binding regression. The watchdog was therefore rolled back together with that unsafe deployment. The recurrence here shows that rolling back the watchdog restored the original half-alive failure mode.

## Owner fix

The live owner `C:\Users\Lauri\AppData\Local\McpVpsEdge\vps_mcp_reverse_tunnel.py` was replaced with a health-discriminating implementation, SHA-256:

`5DA3FABA735C9DD97E97ED390F2E32A7461A47A894D161F1B5F5A7C4FD08F9BD`

Behavior:

1. Probe the local Windows backend `/health` directly.
2. If the backend itself is unhealthy, preserve the tunnel and report `BACKEND_PROBE_FAILED`; do not churn SSH for the wrong fault.
3. If the local backend is healthy, independently probe `/health` through the remote forwarded port on the VPS.
4. Reset the failure streak on recovery.
5. After three consecutive forwarded-health failures while the local backend remains healthy, abort only the failed SSH tunnel connection and reconnect it.
6. Emit timestamped `TUNNEL_PROBE_FAILED`, `TUNNEL_PROBE_RECOVERED`, `TUNNEL_RETRY`, and `TUNNEL_UP` evidence.

An owner-side regression test now lives at:

`C:\Users\Lauri\AppData\Local\McpVpsEdge\test_vps_mcp_reverse_tunnel.py`

It verifies:

- three forwarding failures with a healthy backend abort the half-alive tunnel;
- backend failure does not trigger tunnel churn;
- a successful forwarded probe resets the failure streak.

Focused result: **3/3 PASS**.

## Zero-gap deployment

The implementation fix was not deployed with the previous broken restart path.

1. Started an independent temporary reverse tunnel on VPS loopback `3012` to the unchanged local backend.
2. Verified 3012 from the VPS: 5/5 HTTP 200 responses with latency comparable to 3011.
3. Validated and reloaded Caddy from internal upstream `127.0.0.1:3011` to `127.0.0.1:3012`; public hostname/OAuth/backend identity did not change.
4. Ran 180 continuous public `/health` probes while replacing the live 3011 source and restarting only `McpVpsEdgeTunnel`.
5. Result across that restart: **180/180 PASS**, p95 **29.1 ms**, max **154.5 ms**, zero public failures.
6. Verified the new 3011 path directly from the VPS: 5/5 HTTP 200.
7. Validated and reloaded Caddy back to canonical `127.0.0.1:3011`.
8. Post-cutback public acceptance: **60/60 PASS**, median **20.9 ms**, max **223.3 ms**.
9. Forced a fresh VPS edge-health observation: `healthy:true`, `backend_http:200`, `metadata_http:200`, `caddy:"active"`, `tunnel_listener:"yes"`.
10. Stopped the temporary 3012 process, verified only 3011 remained listening, and removed task-created rollback/staging files.

## Current state

- Backend PID 5604 and accepted backend source remain unchanged.
- Caddy is back on canonical upstream `127.0.0.1:3011`.
- Only the canonical 3011 reverse listener remains on the VPS.
- Production tunnel runtime is the hardened health-discriminating implementation.
- Public health was clean after cutback and the VPS observer returned healthy.
- No OAuth or backend restart occurred.

## Remaining acceptance limit

This turn proves current live transport health and direct MCPv3 execution through the repaired path. Cross-turn ChatGPT-side namespace persistence is a separate historically observed client-side acceptance invariant. The zero-gap deployment intentionally avoided the public disconnect that previously preceded that regression, but a later turn is still the correct place to prove that the direct namespace remains exposed without rediscovery.

## Durable closure

`old path -> failure cause -> owner change -> supported path -> recurrence prevention`

`conn.wait_closed()`-only tunnel -> half-alive forward not represented by SSH session liveness -> live McpVpsEdge tunnel now distinguishes local backend health from forwarded data-plane health -> canonical 3011 tunnel self-recovers only the failed forwarding connection -> owner-side 3-test regression plus VPS observer evidence and zero-gap deployment procedure.
