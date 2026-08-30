# Pending memory append — MCP schema discovery does not prove callability

Observed: 2026-08-27 11:18:24 EEST
Target canonical store: `memory/memory-bank.jsonl`
Reason for pending file: GitHub-only safe fallback. The current bank is larger than the connector can return without truncation, so replacing/reconstructing it would risk dropping unseen entries. `memory/README.md` explicitly requires an append-only timestamped file under `memory/reports/` in this case.

## Observation

In one WebGPT conversation, MCP0 discovery and MCP0 invocation were directly observed as separate states:

1. Connector/resource discovery returned the MCP0 namespace and all seven schemas: `view_image`, `start_process`, `read_output`, `kill_process`, `busy_list`, `busy_claim`, `busy_release`.
2. A direct `MCP0.busy_list` invocation then returned `Resource not found`.
3. MCP0 discovery was refreshed and again returned the same seven schemas.
4. A subsequent direct MCP0 invocation was rejected as `MCP0 tool has been disabled`.

This proves only the conversation-surface distinction: successful schema/resource discovery does **not** prove that a direct MCP0 call is currently callable. It does **not** by itself prove MCP0 backend failure, account-configuration failure, or the cause of the callability loss.

Related evidence: `organicoverlords/regression-research#155`, which already records an earlier instance of tools remaining discoverable while calls failed.

## Canonical candidate

```json
{"id":"mem-20260827-mcp-discovery-not-callability","timestamp":"2026-08-27T11:18:24+03:00","kind":"lesson","scope":"mcp","tags":["schema-discovery","callability","connector-binding","routing"],"title":"MCP schema discovery does not prove callability","text":"Treat MCP schema/resource discovery and direct tool callability as separate observed states. In a 2026-08-27 WebGPT test, MCP0 rediscovery repeatedly exposed all seven tool schemas while direct invocation failed first with `Resource not found` and then with `MCP0 tool has been disabled`. This proves that successful discovery alone must not be reported as having working MCP access; it does not establish backend failure or the cause of callability loss.","state":"PROVEN","evidence":["github:organicoverlords/regression-research#155","memory-report:memory/reports/2026-08-27_111824_EEST_mcp-schema-discovery-not-callability.md"],"supersedes":[]}
```
