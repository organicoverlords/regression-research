# MCP security audit — 2026-09-09

Status: production MCP is live and functional. No production serving mutation was made during this audit.

## Reroute symptom update
User reports that after the visible reroute/safety-buffering update appears, MCP/tool calls continue for only about one minute and then stop. This is preserved separately in `02 Evidence/mcp-security-routing-events.jsonl`. Treat the later tool-plane silence as unresolved; do not infer MCP backend failure without correlated transport/Responses evidence.

## High priority
- Production trust-boundary ACLs are too broad. `CodexSandboxUsers` has inherited Modify access to `ChatGPTMcpClean/.env`, `minimal-connectors/clone-a/oauth.json`, `minimal-connectors/shared-process-receipts`, and `minimal-connectors/launch-production.ps1`.
- `CodexSandboxUsers` currently contains enabled local accounts `CodexSandboxOffline` and `CodexSandboxOnline`.
- The production scheduled task runs `minimal-connectors/launch-production.ps1` as user `Lauri` (Limited run level). A lower-trust sandbox identity which can alter this script or OAuth state can cross the intended trust boundary on a later launch or tamper with bearer-token records/receipts.
- Do not blindly remove ACLs until the ChatGPT desktop/sandbox dependency is mapped. Preferred design: protected production runtime/state owned by Lauri/SYSTEM/Admins only; keep any developer/sandbox-writable checkout separate from the scheduled production artifact.

## Dependency findings
- Live production installs `@modelcontextprotocol/sdk 1.24.3`. Current npm audit reports a high advisory for cross-client server/transport reuse and the older SDK ReDoS advisory. This deployment creates a fresh `McpServer` and `StreamableHTTPServerTransport` per stateless request and closes both, so the cross-client reuse pattern is not present. No vulnerable `UriTemplate`/exploded resource-template usage was found, so the ReDoS path is not currently exposed. Upgrade to a patched current SDK (npm audit currently offers 1.30.0) after off-path compatibility proof.
- Live production installs `qs 6.15.3`; npm audit reports moderate DoS advisories patched in 6.16.0. The inspected OAuth handlers use `express.urlencoded({extended:false})` and the app uses JSON for MCP, so the advisory-specific `qs` parsing patterns were not found on the main serving path. Still upgrade during the dependency refresh.

## Network / auth controls that passed
- Node backend binds only `127.0.0.1:3011`.
- Windows portproxy is exactly `10.203.0.2:3011 -> 127.0.0.1:3011`.
- `10.203.0.2` is the `mcp-wireguard` interface.
- Firewall rule `MCP-WireGuard-3011` allows TCP 3011 only from remote `10.203.0.1` to local `10.203.0.2`.
- Fresh unauthenticated `/mcp` returned 401; a bad Host header returned 403.
- OAuth uses 32-byte random tokens, stores SHA-256 token digests, 1-hour access TTL, 7-day refresh TTL, resource/scope checks, and atomic durable-store writes.
- Live OAuth store keys are SHA-256-shaped; no plaintext bearer-token keys were observed.
- Production process profile exposes only `start_process`, `read_output`, and `kill_process`.
- Production mutation preflight is fail-closed; it also produced false-positive blocks on some read-only compound inspection commands, so that behavior must be kept distinct from upstream safety-buffering/reroute incidents.

## Other hardening findings
- A local Caddy test instance listens on all interfaces at TCP 8443 and Windows firewall rule `MCP Caddy 8443 TCP Public` allows any remote address on Public profiles. Its upstream is a loopback MCP instance and bearer auth still applies to `/mcp`, but this is an unnecessary extra attack surface if the home-test endpoint is no longer needed.
- Public VPS `/health` and `/edge-status` are unauthenticated and expose operational metadata (backend generation/PID/request counts/live process count; WireGuard health/handshake age/fallback state/disk usage). This is low-value information disclosure and can be reduced or protected.
- `/artifact/*` is intentionally public-by-link, but publisher uses a cryptographically random 24-byte URL-safe slug and artifacts are pruned after about 24 hours; current edge status reported zero artifact sets. Treat URLs as bearer secrets.
- VPS management helpers `provision_edge_extras.py`, `publish_artifact.py`, and `verify_edge.py` connect as root with `known_hosts=None`, disabling SSH server host-key verification. Replace with pinned/verified host keys. The local ED25519 private key itself has a tight ACL (Lauri/SYSTEM/Administrators only).
- Shared process receipts contain raw command/stdout/stderr and retain up to 7 days. Current hot receipt directory held ~2,727 receipts / ~20.8 MB during this audit. Their sandbox-writable ACL should be part of the state hardening plan.

## Recommended order
1. Design and test ACL separation for production state/runtime without breaking ChatGPT desktop sandbox integration.
2. Pin SSH host verification for all root VPS management helpers.
3. Upgrade MCP SDK / `qs` off-path, run full tests, then use the guarded replacement path.
4. Remove or restrict the 8443 home-test listener/firewall rule if it is obsolete.
5. Reduce/authenticate public health/status metadata; keep artifact bearer-link behavior only if still required.

No runtime/edge/firewall/OAuth state was changed by this audit.
