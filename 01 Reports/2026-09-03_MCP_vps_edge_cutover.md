# MCP VPS edge cutover — 2026-09-03

Status: current topology record and recovery runbook. Live runtime evidence outranks this report.

## Why the ingress changed

The production ChatGPT MCP path was moved away from Tailscale Funnel after a reproducible request-arrival failure class matched Tailscale issue #20949 (`tailscale/tailscale`): Funnel can intermittently drop the third request in an MCP-style handshake on Windows. The machine was running Tailscale 1.102.3, and current upstream did not contain a relevant Serve/Funnel fix at cutover time.

This was isolated as an ingress problem, not an MCP process-contract failure: local clone health, OAuth metadata, direct public probes, and process calls were independently successful while some ChatGPT calls failed before backend arrival.

## Current production path

`ChatGPT MCPv3 -> https://5-61-91-127.sslip.io/mcp -> Caddy on VPS 5.61.91.127 -> persistent reverse SSH -> Windows 127.0.0.1:3011`

The Windows clone remains loopback-only. The VPS reverse listener is also bound to VPS loopback `127.0.0.1:3011`; it is not exposed as a public TCP service.

Public OAuth/resource identity is rooted at `https://5-61-91-127.sslip.io/`.

Tailscale remains installed for private networking/diagnostics but Funnel is non-production fallback ingress and must be freshly revalidated before reliance.
## Verified cutover evidence

1. MCP repository PR #45 merged non-`.ts.net` HTTPS public-origin support.
2. Fresh OAuth registration/authorization/token exchange succeeded through the VPS without any Tailscale identity header.
3. Public MCP initialize, tools/list, start_process and read_output succeeded through Caddy + reverse SSH.
4. The temporary-tunnel path passed 100/100 consecutive `initialize -> initialized -> start_process` sequences.
5. After handoff to the scheduled persistent tunnel, the final path again passed 100/100 consecutive sequences.
6. Live MCPv3 traffic reached backend 3011 with `via_funnel=false`; repeated start_process/read_output calls returned HTTP 200 with no observed early-close/abort/request-error event in the monitored window.
7. The MCP process contract and multi-client clone test passed. The broader npm suite still hit the pre-existing unrelated `test-supervisor-continuity` health timeout after the earlier focused tests passed; do not misreport the full suite as green.

## Edge services

Windows persistent tunnel owner:
`%LOCALAPPDATA%\McpVpsEdge\start-tunnel.ps1` via scheduled task `McpVpsEdgeTunnel`.

VPS services:
- Caddy HTTPS on public TCP 80/443.
- UFW active: inbound allow 22/tcp, 80/tcp, 443/tcp; default deny other inbound.
- fail2ban active for SSH.
- `mcp-edge-health.timer` records a one-minute safe health snapshot.
- `mcp-artifact-prune.timer` removes artifact staging directories older than 24 hours.
Public safe health snapshot:
`https://5-61-91-127.sslip.io/edge-status`

Artifact staging helper:
`%LOCALAPPDATA%\McpVpsEdge\publish-artifact.ps1`

It uploads through SSH into an unguessable per-upload directory, verifies SHA-256 after upload, serves the artifact through HTTPS under `/artifact/<random>/...`, and returns a 24-hour TTL. Directory browsing is not enabled. A self-test downloaded identical bytes and matched SHA-256 end to end.

## Recovery boundary

If the VPS edge fails, first distinguish edge failure from local MCP failure using `/edge-status`, direct clone health, the scheduled tunnel state, and backend transport logs. Do not rewrite OAuth stores, process receipts, tool schemas, clone ports, or backend generations merely because a client-visible request did not arrive.

The edge is transport, not ownership or scheduling authority. BusyCoordinator remains separate collision/ownership control.

The public `sslip.io` hostname is an operational DNS convenience bound to the VPS IPv4. A dedicated domain can replace it later without changing the loopback/tunnel architecture; update `MCP_PUBLIC_ORIGIN`, Caddy, and the ChatGPT app identity together and re-run the full OAuth/process proof.

## 2026-09-05 monitoring migration checkpoint

The deployed edge observer now distinguishes automatic-primary health from recovery availability. `/usr/local/bin/mcp-edge-health`, run by `mcp-edge-health.service` from `mcp-edge-health.timer` once per minute, writes `/var/lib/mcp-edge/status.json`. Windows `WireGuardTunnel$mcp-wireguard` owns the automatic primary transport; scheduled task `McpVpsEdgeTunnel` owns the independent SSH recovery lanes.

Observer semantics from the deployed health script:
- `primary_healthy` is true only when the WireGuard primary backend returns HTTP 200 and `wireguard_peer_fresh=true`.
- `healthy` additionally requires OAuth metadata HTTP 200 and `caddy=active`; SSH fallback status cannot make `healthy` or `primary_healthy` true.
- WireGuard freshness is exposed as `wireguard_interface`, `wireguard_handshake_age_seconds`, and `wireguard_peer_fresh`; the deployed freshness threshold is 0-180 seconds.
- `recovery_available`, `fallback_healthy_count`, and `fallback_3101_http` through `fallback_3104_http` describe explicit recovery capacity only. Caddy does not automatically select those SSH listeners.

This checkpoint updates the topology semantics documented above: the automatic VPS-to-PC path is WireGuard `10.203.0.2:3011`; reverse-SSH listeners `3101-3104` remain independent explicit recovery lanes. The observer is visibility only and does not authorize or perform failover.
