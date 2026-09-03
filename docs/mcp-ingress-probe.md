# MCP ingress probe

`tools/mcp_ingress_probe.py` is the #394 red-capable feedback loop for separating public-ingress loss from backend/OAuth/schema failures.

Run the same public connector origin twice, once with normal connection reuse and once with fresh connections. Use `--repeat` for intermittent failures. When the owned backend transport log is supplied, the probe reads only bytes appended after the run starts and classifies each request as backend-arrived, pre-backend/edge drop, failure with uncorrelated concurrent backend activity, or edge-response-without-backend-telemetry. Only a matching backend request ID is treated as backend-arrival proof.

```powershell
python tools/mcp_ingress_probe.py --base-url https://HOST/clone-a --backend-log "$env:LOCALAPPDATA\ChatGPTMcpClean\minimal-connectors\clone-a\transport.jsonl" --repeat 10
python tools/mcp_ingress_probe.py --base-url https://HOST/clone-a --backend-log "$env:LOCALAPPDATA\ChatGPTMcpClean\minimal-connectors\clone-a\transport.jsonl" --repeat 10 --fresh-connection
```

The default sequence is `GET health`, unauthenticated `POST mcp` initialize, then `GET health` again on the same connection. A custom JSON request plan can replace it. This harness does not claim an OpenAI binding failure from a synthetic probe; it establishes only which network/backend boundary each probe crossed.

