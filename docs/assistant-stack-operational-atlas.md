# Assistant Stack Operational Atlas

> Generated derived view. Current user instruction and named live/source authorities outrank it.

## Operating invariant

For stack/infra work, consume the compact Atlas first and deep-lookup every relevant component before reasoning, answering, redesigning, repairing, or mutating. Fetch status from the named live route. If identity, dependency role, supervisor, self-heal, blast radius, or independent recovery is unknown, disruptive action is blocked.

## Feature discovery

Use `find <query>` when you know the need but not the component. Search this derived index before proposing new stack machinery.

| Feature | Owner components | Entrypoints | Boundary |
| --- | --- | --- | --- |
| `orchestration.operator` | agent_rules | C:\Users\Lauri\.agents\RULES.md; python tools\stack_atlas.py lookup agent_rules | Navigation to the designated main-chat/operator behavior owner only. The orchestrator is a role governed by canonical agent_rules, not a daemon or separate runtime/control-plane component; live project/runtime evidence and BusyCoordinator remain their own authorities. |
| `production.change_gate` | agent_rules, busy_coordinator, vps_edge_ingress, mcp_front_door | python tools\stack_atlas.py production-change-gate <component> --actor <actor> --busy-scope <exact-scope>; PASS requires --independent-rollback-verified --offpath-proof-verified plus either --routine-scoped-advance for an already-established reversible serving advance or --explicit-user-authorization for a scope-widening/destructive/topology change | Read-only preflight for shared production/control-plane mutation. A routine already-scoped reversible serving advance does not require redundant per-cutover user approval; arbitrary new, scope-widening, destructive, credential/permission, scheduler/fleet, or topology/control-plane mutation still requires explicit user authorization. |
| `mcp.edge_monitoring` | vps_edge_ingress | https://5-61-91-127.sslip.io/edge-status; python tools\stack_atlas.py lookup vps_edge_ingress; %LOCALAPPDATA%\McpVpsEdge\provision_edge_extras.py | Observer semantics only: healthy/primary_healthy describe the automatic WireGuard primary path, while SSH 3101-3104 contribute only recovery_available/fallback health. WireGuard freshness is explicit in wireguard_handshake_age_seconds and wireguard_peer_fresh. Observation never authorizes automatic SSH failover or serving-path mutation. |
| `cleanup.convergence` | agent_rules, local_git, busy_coordinator | python C:\Users\Lauri\Desktop\vault\tools\cleanup_converger.py --apply --operator-ack; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\operator-cleanup-convergence.md | Operator-only bounded convergence. One invocation loops internally to a stable boundary; it may remove only clean branch-anchored inactive secondary P3/Vault worktrees, and may reclaim only Git-ignored standard Unreal Binaries/Intermediate/DerivedDataCache from inactive preserved secondary P3 lanes. Recent MCP-CWD, external process targets, and Git-locked lanes veto cache cleanup; tracked Content/Saved/proof/evidence/source are excluded. No force removal, branch deletion, fetch, reset/rebase, dirty/unanchored deletion, permission change, or process kill. Recurring workers must not use it to administer themselves or sibling lanes. |
| `work.intake` | agent_rules, github, local_git, busy_coordinator | bounded matching issue/PR search in the owning repo; continue the matching issue or create one when none exists; relevant live git status/HEAD + attributed dirty state; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd inspect <exact-scope>; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd claim <actor> <exact-scope>; before yielding: commit/branch/PR coherent work or record exact remaining dirty paths/checkpoint on the issue | Ordered navigation to the existing .agents issue-first contract: inspect/claim occurs immediately before shared mutation. The GitHub issue is the shared convergence record, not a queue, priority, capacity, or admission system. Busy is exact mutation collision control only. No new workflow authority is created. |
| `mcp.current_topology` | mcp_minimal_clone | C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-current-topology.json; python tools\stack_atlas.py lookup mcp_minimal_clone | Current GPT1 serving authority: https://91-159-12-133.sslip.io/mcp -> local HTTPS Caddy -> 127.0.0.1:3022. The old 5-61-91-127.sslip.io/VPS/WireGuard/reverse-SSH/Tailscale path is not the GPT1 serving, authorization, or recovery path. mcp-recovery-state.json is the current local-only recovery contract; legacy recovery snapshots are evidence-only. |
| `mcp.chatgpt_plugin_surface` | mcp_minimal_clone | python tools\stack_atlas.py lookup mcp_minimal_clone; %LOCALAPPDATA%\ChatGPTMcpClean\config\process-tool-contract.json; %LOCALAPPDATA%\ChatGPTMcpV4HomeDirectStable\src\lib\process-library-upload.ts; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-current-topology.json | The GPT1 ChatGPT connector exposes exactly start_process, read_output, and kill_process. CHATGPT_LIBRARY_UPLOAD image/file handling is process-result metadata/resource output through ui://process/library-upload-v2.html and does not create another tool. busy_*, view_image, and visual-proof actions are excluded. More than three discovered actions indicates stale/wrong client connector metadata before it indicates a server topology defect. |
| `mcp.recovery_state` | agent_rules, mcp_minimal_clone | C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-recovery-state.json; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-current-topology.json; python tools\stack_atlas.py bootstrap-glance; C:\Users\Lauri\.agents\RULES.md | Current local-only GPT1 recovery contract. Restore only https://91-159-12-133.sslip.io/mcp -> local Caddy -> 127.0.0.1:3022, using clone-a 127.0.0.1:3011 only as independent local control. Legacy VPS/WireGuard/reverse-SSH/Tailscale snapshots are historical evidence and are never automatic or preferred recovery targets. |
| `mcp.regression_recovery` | agent_rules, mcp_minimal_clone, busy_coordinator | C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-recovery-state.json; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-current-topology.json; python tools\stack_atlas.py production-change-gate mcp_minimal_clone --actor <actor> --busy-scope <exact-home-direct-3022-scope> --routine-scoped-advance --independent-rollback-verified --offpath-proof-verified | Restore-first means restore the current local GPT1 topology and three-tool behavior, not an obsolete historical transport. Preserve active work and use clone-a 127.0.0.1:3011 as independent control when 3022 requires repair. The legacy 5-61-91-127.sslip.io/VPS/WireGuard/reverse-SSH/Tailscale designs are not recovery targets. Returning to one of them is a topology/control-plane redesign and requires separate explicit user authorization. |
| `mcp.security_reroute_log` | agent_rules, mcp_minimal_clone, vps_edge_ingress, memory_bank | C:\Users\Lauri\Desktop\vault\02 Evidence\mcp-security-routing-events.jsonl; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-recovery-state.json; C:\Users\Lauri\.agents\RULES.md | When the user explicitly asks for platform-reroute/security analysis or incident tracking, a user-reported reroute must be logged with report/event time semantics, preceding actions/changes, serving identifiers, and bounded live evidence before related MCP/edge mutation; otherwise treat platform security events as external and do not persist them. Never infer an unknown occurrence time or use server-only arrivals as a complete denominator for client-side reroutes. |
| `vault.overview` | memory_bank | python tools\memory_bank.py overview; python tools\memory_bank.py digest; python tools\stack_atlas.py find <natural-language-query> | Default bounded Vault orientation: aggregate durable/historical memory evidence into useful themes and recent items without treating Vault as current repo/runtime/scheduler truth. Use targeted context/timeline only after the overview identifies a relevant thread. |
| `vault.history` | memory_bank | memory_bank.py search; memory_bank.py search --history; memory_bank.py context; memory_bank.py timeline; memory_bank.py recent-titles | History/evidence only; use targeted indexed reads, never recursive Vault scans or current-state inference. |
| `project.current_truth` | agent_rules, north_star, local_git, github | shared .agents RULES.md + AGENTS.md; organicoverlords/agents@main docs/repos/<repo>/ product direction; git status/HEAD + relevant branch/commit history; exact GitHub issue/PR/check/runtime evidence | Current project truth comes from the smallest relevant live authority, not Atlas, memory, reports, or dashboards. |
| `project.tiny3d_asset_library` | local_git, visual_proof | C:\Users\Lauri\Desktop\Tiny3D_LIBRARY; C:\Users\Lauri\Desktop\Tiny3D_LIBRARY\.tiny3d\library\unified-asset-inventory-v1.json; C:\Users\Lauri\Desktop\Tiny3D_LIBRARY\.tiny3d\library\showroom-v2-catalog-v1.json; $env:PYTHONPATH='C:\Users\Lauri\Desktop\tiny3d\src'; python -m tiny3d library search <query> --workspace 'C:\Users\Lauri\Desktop\Tiny3D_LIBRARY'; $env:PYTHONPATH='C:\Users\Lauri\Desktop\tiny3d\src'; python -m tiny3d library show <asset-id> --workspace 'C:\Users\Lauri\Desktop\Tiny3D_LIBRARY'; python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup tiny3d_library --query <asset-or-name> | Navigation only; Tiny3D repo/library data remain product authority. Use the canonical production workspace, bounded library search/show, and receipt-declared proof paths. Do not recursively scan, fetch LFS, unzip, regenerate previews, re-encode media, or hunt producer paths merely to inspect evidence. Producer/runtime PASS and independent visual review are separate states. |
| `project.p3_visual_evidence` | visual_proof, local_git | G:\Oma Drive\P3 Visual Evidence\p3\index-v1.json; $i=Get-Content 'G:\Oma Drive\P3 Visual Evidence\p3\index-v1.json' -Raw | ConvertFrom-Json; $i.entries | Where-Object { $_.search_text -match '<query>' } | Select-Object -First 10 | Navigation only; the durable P3 root index remains the producer/operator lookup source for screenshots/videos. Query the single index, select one exact run/media identity, and preserve its original bytes/hash. If those pixels are not already exposed in the current session and the selected original image is reachable through the normal machine route, the default chat-visible retrieval path is the GPT1 process-result metadata bridge: emit CHATGPT_LIBRARY_UPLOAD=<absolute path> from start_process/read_output, then inspect the exposed pixels with native vision. The metadata/resource transport is not visual acceptance and does not add an MCP action. Google Drive/Library, open_visual_proof/view_image, base64, custom HTTP, re-encoding, archive expansion, or regeneration are not preferred merely to expose an image when the metadata bridge can carry the same original bytes. Use another faithful project-owned retrieval path only when the metadata bridge cannot carry or reach the exact media. Independent visual review must be reported exactly as indexed, including NOT_RECORDED and REJECTED. |
| `project.shared_visual_library_integration` | memory_bank, visual_proof, local_git | python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py context <current-task>; python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup tiny3d_library --query <asset-or-name>; G:\Oma Drive\P3 Visual Evidence\p3\index-v1.json; default chat visual route: normal MCP process result -> CHATGPT_LIBRARY_UPLOAD=<absolute original image path> -> ui://process/library-upload-v2.html -> native vision; historical/non-canonical review lineage only: C:\LowVRAMProofs; historical/non-canonical model-review transport only: organicoverlords/p3#1936 / PR #1244; historical/non-canonical MCP Apps transport only: organicoverlords/chatgpt-mcp-clean#158 / PR #159 | Cross-project navigation only; source libraries/indexes remain proof authority and this feature does not create another registry. After resolving one exact original image identity from P3, Tiny3D, or any other project-owned source, every worker/project uses the normal GPT1 process-result metadata bridge as the default chat-visible retrieval path when the pixels are not already exposed: emit CHATGPT_LIBRARY_UPLOAD=<absolute path> from start_process/read_output, consume the resource/metadata in chat, then inspect the exposed pixels with native vision. The bridge is transport only, not acceptance and not a fourth MCP action. Do not prefer Drive/Library, open_visual_proof/view_image, base64, custom HTTP, Git/LFS, re-encoding, C:\LowVRAMProofs, or a second proof store merely to expose an image when the metadata route can carry the exact original bytes. Use the smallest faithful project-owned fallback only when the metadata bridge cannot reach or support the exact media. |
| `project.p3_unreal_navigation` | local_git, github | C:\Users\Lauri\Documents\Unreal Projects\p3; C:\Users\Lauri\Documents\Unreal Projects\p3\scripts\v2\verification\p3_bridge_guard.py; C:\Users\Lauri\Documents\Unreal Projects\p3\scripts\Test-P3WorkerEditorPreflight.ps1 | Navigation only. P3 product direction lives in organicoverlords/agents@main under docs/repos/p3; current P3 repo/main, repo-owned machine contracts, and live editor/runtime evidence remain implementation/runtime authority. Atlas must not become P3 product state. Validate UE_MCP_Bridge endpoint identity through the repo-owned live guard/preflight rather than trusting Saved/UE_MCP_Bridge/port.json alone; a configured UnrealMCPBridge port is not liveness or ownership proof. |
| `coordination.ownership` | busy_coordinator | C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd inspect <scope>; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd claim; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd heartbeat; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd release; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd recover; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd snapshot | Exact mutation collision/ownership only; never infer backlog, liveness, priority, capacity, or progress. |
| `coordination.checkpoint_context` | busy_coordinator | C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd inspect <scope>; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd claim --checkpoint; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd heartbeat --checkpoint | Live exact-scope ownership context only; never retained after release/recovery/expiry and never backlog, priority, handoff scheduling, liveness, or reassignment. Durable continuation belongs in the project issue/PR. |
| `worker.reports` | worker_reports | C:\Users\Lauri\Desktop\vault\worker-reports\current\<automation-id>.md; C:\Users\Lauri\Desktop\vault\worker-reports\history\_reports\*.json | Self-report/navigation surface; visual proof pointers are PENDING_REVIEW until independent reviewed.json exists; verify important liveness/progress claims against repo/runtime/CI/artifact evidence. |
| `worker.swarm_topology` | swarm_topology | C:\Users\Lauri\Desktop\vault\04 Operating Contracts\chatgpt-swarm-topology.json; python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup swarm_topology; python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>; python C:\Users\Lauri\Desktop\vault\tools\worker_recovery_guard.py <actor-worker-id> <target-worker-id>; python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance | Two ChatGPT subscription partitions contain five recurring workers each. The scheduler provides recurrence only. Routine health recovery is distributed: each recurring worker checks same-partition siblings from local reports/start receipts and may perform one guard-authorized idempotent re-enable; a supervising/manual ChatGPT session may perform the same bounded recovery. Operator handoff is an administrative fallback/control surface, not routine supervision, and the user is not the worker supervisor. Current activity/liveness remains live MCP/runtime evidence; recovery never crosses subscription partitions. |
| `execution.linux_omen_node` | linux_omen_node | python tools\stack_atlas.py lookup linux_omen_node; python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py route --work-id <stable-task-id> --kind <work-kind>; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\linux-omen-execution-node.md; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\swarm-routing-cohort.md | Default execution node under the shared swarm routing cohort for substantive work that is not LowVRAM or genuinely Windows-only. Windows remains MCP/control transport and takes ordinary execution only after fresh cohort evidence that OMEN is saturated/unavailable for that work class; the VPS may take supported portable-light overflow. OMEN is not an MCP endpoint, worker scheduler, repository queue, product authority, or public route; preserve user data and do not expose TCP 22 publicly. |
| `execution.transport` | vps_edge_ingress, mcp_minimal_clone, mcp_front_door | preferred MCPv3 binding when healthy and exposed; Remote Desktop Commander approved standby break-glass fallback whenever preferred MCPv3 is unavailable; fallback-only/not primary, not forbidden; retry failed routes only on changed state or new evidence | Routing precedence is governed by shared RULES.md. Transport only; tool availability does not confer ownership, scheduling, or product authority. MCPv3 health does not retire, obsolete, or authorize deletion of the Commander fallback; preserve its recovery path unless current user/live authority explicitly changes that contract. |

## Components

### `busy_coordinator`

- Role: `coordination_authority`
- Capabilities: coordination
- Canonical sources: C:\Users\Lauri\AppData\Local\BusyCoordinator\coordinator-contract.json; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy.py; C:\Users\Lauri\AppData\Local\ChatGPTMcpClean\.state\busy-claims.json
- Live status: C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd --help; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd snapshot; C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd inspect <scope>
- Independent recovery: C:\Users\Lauri\AppData\Local\BusyCoordinator\busy-python.cmd recover
- Resources: C:\Users\Lauri\AppData\Local\ChatGPTMcpClean\.state\busy-claims.json
- Dependents: chatgpt_session; execution_workers
- Runbook: C:\Users\Lauri\AppData\Local\BusyCoordinator\coordinator-contract.json; AGENTS.md
- Supervisor: none; CLI/service contract owns durable store semantics
- Self-heal: not_applicable

### `mcp_front_door`

- Role: `process_transport_front_door`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: %LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1; chatgpt-mcp-clean/src/front-door.ts
- Live status: root front-door health plus exact tool contract/semantic call; root / on 3003 is a separate legacy/fallback surface; canonical GPT1 bypasses it through local HTTPS Caddy -> 127.0.0.1:3022. VPS/WireGuard/reverse-SSH paths remain separate infrastructure and are not GPT1 recovery targets; ordered static-array clone fallback is bounded experiment/fallback infrastructure, not proof of production clone continuity
- Independent recovery: inactive backend generation for root + atomic front-door switch; do not use root recovery to rewrite direct clone handlers
- Resources: front-door port; active-backend.json; process-routes.json
- Dependents: chatgpt_process_transport
- Runbook: %LOCALAPPDATA%\ChatGPTMcpClean\AGENTS.md; %LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1
- Supervisor: ChatGPTMcpClean keepalive FrontDoor role
- Self-heal: supervisor_managed_but_not_permission_to_disrupt

### `mcp_backend`

- Role: `replaceable_process_transport_backend`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: %LOCALAPPDATA%\ChatGPTMcpClean\start.ps1; %LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1
- Live status: backend health; exact tools/list schema; semantic process call; durable process contract: read_output max 32000; start_process default wait 750 ms; live cap 5 per caller; no rolling launch/token bucket
- Independent recovery: other backend generation behind stable front door
- Resources: backend port; transport.jsonl
- Dependents: mcp_front_door
- Runbook: %LOCALAPPDATA%\ChatGPTMcpClean\AGENTS.md; %LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1
- Supervisor: ChatGPTMcpClean keepalive Backend role
- Self-heal: supervisor_managed

### `mcp_minimal_clone`

- Role: `generation_pinned_process_transport_clone`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-current-topology.json; %LOCALAPPDATA%\ChatGPTMcpV4HomeDirectStable\scripts\home-direct-supervisor.ps1; %LOCALAPPDATA%\ChatGPTMcpV4HomeDirectStable\config\home-direct.Caddyfile; %LOCALAPPDATA%\ChatGPTMcpClean\config\process-tool-contract.json; %LOCALAPPDATA%\ChatGPTMcpV4HomeDirectStable\src\index.ts; %LOCALAPPDATA%\ChatGPTMcpV4HomeDirectStable\src\lib\process-library-upload.ts; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-recovery-state.json
- Live status: canonical GPT1 connector: https://91-159-12-133.sslip.io/mcp; serving path: ChatGPT/GPT1 -> local HTTPS Caddy -> 127.0.0.1:3022; OAuth authorization endpoint: https://91-159-12-133.sslip.io/authorize with local-edge owner authorization; worker-visible contract is exactly start_process, read_output, kill_process; image delivery remains process-result metadata/resource output and does not add an action; default visual retrieval for all workers/projects is CHATGPT_LIBRARY_UPLOAD metadata on the normal process route, followed by native pixel inspection; 5-61-91-127.sslip.io, VPS Caddy, WireGuard, reverse SSH, and Tailscale owner authorization are not in the GPT1 path; mcp-recovery-state.json is the current local-only recovery contract; the obsolete Sept 6 VPS/WireGuard/reverse-SSH snapshot exists only under 02 Evidence and is non-operational
- Independent recovery: clone-a at 127.0.0.1:3011 is the independent local control/recovery route for the home-direct 3022 service; mcp-recovery-state.json restores only the current local 91-159-12-133.sslip.io -> 3022 topology; the legacy VPS/WireGuard/reverse-SSH snapshot is evidence-only and cannot be selected as recovery; client-visible stale connector metadata does not authorize VPS/WireGuard/Tailscale repair or backend/OAuth churn; authentication repair must preserve the three-tool process profile and local 91-159-12-133.sslip.io -> 3022 serving topology
- Resources: 91-159-12-133.sslip.io HTTPS; local Caddy; 127.0.0.1:3022; oauth.json; transport.jsonl; shared-process-receipts; process-control; clone-a 127.0.0.1:3011 independent control; process library upload metadata/resource handler
- Dependents: chatgpt_process_transport
- Runbook: C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-current-topology.json; %LOCALAPPDATA%\ChatGPTMcpClean\AGENTS.md; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\mcp-recovery-state.json
- Supervisor: McpV4HomeDirect3022 scheduled task -> pinned home-direct stable runtime
- Self-heal: generation_specific

### `vps_edge_ingress`

- Role: `public_mcp_edge_and_observer`
- Capabilities: source_read, runtime_validate, artifact_transfer
- Canonical sources: %LOCALAPPDATA%\McpVpsEdge\mcp-wireguard.conf; %LOCALAPPDATA%\McpVpsEdge\start-tunnel.ps1; %LOCALAPPDATA%\McpVpsEdge\provision_edge_extras.py; %LOCALAPPDATA%\McpVpsEdge\publish-artifact.ps1; 5.61.91.127:/etc/caddy/Caddyfile
- Live status: separate MCPv3/legacy edge observer only; never use this component as GPT1 serving or recovery authority; https://5-61-91-127.sslip.io/edge-status is the deployed observer snapshot for that separate edge; primary_healthy is the automatic WireGuard primary only: primary_backend_http=200 plus wireguard_peer_fresh=true; SSH recovery lanes never contribute to primary_healthy or healthy; WireGuard freshness fields are wireguard_interface, wireguard_handshake_age_seconds, and wireguard_peer_fresh; the deployed observer treats handshake age 0-180 seconds as fresh; recovery_available and fallback_healthy_count describe explicit-recovery SSH lanes 3101-3104 only; fallback_3101_http through fallback_3104_http represent recovery availability, and Caddy does not select them automatically; https://5-61-91-127.sslip.io/.well-known/oauth-protected-resource/mcp; Windows WireGuardTunnel$mcp-wireguard service owns the 10.203.0.2/30 primary; Caddy automatic upstream is only 10.203.0.2:3011 over WireGuard; Windows scheduled task McpVpsEdgeTunnel owns SSH fallback recovery; VPS /usr/local/bin/mcp-edge-health via mcp-edge-health.service and mcp-edge-health.timer owns one-minute observation
- Independent recovery: local clone can be tested directly without edge; edge failure must not authorize backend/OAuth/receipt churn; if WireGuard primary fails, 3101-3104 may be selected only by an explicit authorized recovery action; Caddy must not automatically reroute to them; Tailscale may be used only as an explicitly revalidated non-production fallback
- Resources: VPS 5.61.91.127; public TCP 80/443; WireGuard UDP 51820; WireGuard 10.203.0.1/30 <-> 10.203.0.2/30; SSH TCP 22 fallback transport; VPS loopback 3101-3104 reverse listeners; /usr/local/bin/mcp-edge-health; /etc/systemd/system/mcp-edge-health.service; /etc/systemd/system/mcp-edge-health.timer; /srv/mcp-artifacts; /var/lib/mcp-edge/status.json
- Dependents: mcp_minimal_clone; file_transfer; chatgpt_process_transport
- Runbook: 01 Reports/2026-09-03_MCP_vps_edge_cutover.md
- Supervisor: Caddy/systemd on VPS plus Windows WireGuard tunnel service primary and McpVpsEdgeTunnel task for SSH fallbacks
- Self-heal: WireGuard service is the automatic primary path; VPS mcp-edge-health.timer observes health; native SSH 3101-3104 remain explicit recovery only; Caddy active health polling is disabled

### `tailscale_ingress`

- Role: `secondary_network_ingress_fallback`
- Capabilities: source_read, runtime_validate
- Canonical sources: C:\Program Files\Tailscale\tailscale.exe; %LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1
- Live status: secondary ingress for separate legacy/MCPv3 paths; never use as GPT1 serving/auth/recovery authority; MCP_PUBLIC_ORIGIN host; tailscale funnel status --json; stable front door 127.0.0.1:3003; any deliberate GPT1 reactivation is a topology redesign requiring explicit authorization
- Independent recovery: production MCPv3/VPS remains independent; the stable front door can be tested locally without Tailscale ingress
- Resources: Funnel config; HTTPS listener; stable front-door proxy
- Dependents: mcp_front_door
- Runbook: %LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1
- Supervisor: Tailscale service; Funnel configuration owner is ChatGPTMcpClean keepalive.ps1
- Self-heal: service_specific; route edits require explicit verification

### `linux_omen_node`

- Role: `primary_lan_execution_node`
- Capabilities: source_read, repository_mutate, runtime_validate, artifact_transfer, build_compute
- Canonical sources: C:\Users\Lauri\Desktop\vault\04 Operating Contracts\linux-omen-execution-node.md; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\swarm-routing-cohort.md
- Live status: bounded SSH probe through the documented Windows MCP -> LAN SSH route; mDNS aatuska-OMEN-by-HP-Laptop-15-dc0xxx.local must resolve to the intended host and host-key verification must pass; current disk/RAM/GPU state must be re-read before heavy UE work; historical capability snapshots are not liveness proof; sudo -n /usr/local/sbin/omen-agent-admin verify-storage validates /mnt/ue and /boot/efi without exposing a general root shell
- Independent recovery: local laptop console remains independent of SSH; existing Windows MCP/VPS/WireGuard serving topology is independent and must not be changed to recover this preferred execution node
- Resources: HP OMEN by HP Laptop 15-dc0xxx; Linux user aatuska; mDNS aatuska-OMEN-by-HP-Laptop-15-dc0xxx.local; C:\Users\Lauri\.ssh\chatgpt-linux-aatuska-ed25519 (private key path only; never read/report contents); LAN SSH TCP 22; Intel i7-8750H / 15 GiB RAM / GeForce GTX 1070 Mobile; NVMe UE_FAST /dev/nvme0n1p5 ext4 UUID a6c05af1-0ede-4327-9fec-0411ac6628ee mounted at /mnt/ue; /usr/local/sbin/omen-agent-admin fixed-action storage helper (status, verify-storage, mount-ue, restart-ready)
- Dependents: chatgpt_session; execution_workers
- Runbook: C:\Users\Lauri\Desktop\vault\04 Operating Contracts\linux-omen-execution-node.md; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\swarm-routing-cohort.md; python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py status --refresh-probe
- Supervisor: user-owned Linux Mint laptop; sshd on laptop; Windows MCP is transport only
- Self-heal: machine admission is owned by the shared swarm routing cohort; repository lanes supervise their own execution; do not add a second scheduler/control plane on OMEN

### `file_transfer`

- Role: `artifact_transfer_bridge`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: current conversation file attachments; ChatGPT files/library connector when exposed; generated sandbox artifacts; %LOCALAPPDATA%\McpVpsEdge\publish-artifact.ps1
- Live status: source path exists; destination path exists; byte size matches; SHA-256 matches end to end; VPS artifact URL downloads identical bytes and expires after 24 hours
- Independent recovery: use another exposed transfer route only after preserving the same source bytes and hash
- Resources: artifact bytes; source path/ref; destination path/ref; size; SHA-256
- Dependents: chatgpt_session; execution_workers; visual_proof
- Runbook: %LOCALAPPDATA%\McpVpsEdge\publish-artifact.ps1
- Supervisor: surface-specific; no single transfer authority
- Self-heal: route_specific

### `visual_proof`

- Role: `acceptance:user_visible_evidence`
- Capabilities: source_read, runtime_validate
- Canonical sources: project-owned durable proof bundle/library; repo-local proof/acceptance contract; independent review receipt when one exists
- Live status: durable original media bytes and hashes; capture/result receipt; independent review state; user-visible acceptance target
- Independent recovery: classify why the previous proof failed and change a load-bearing condition before another expensive retry
- Resources: durable capture/media bytes; manifest/receipt; review verdict; acceptance requirement
- Dependents: project runtime; worker_reports
- Runbook: C:\Users\Lauri\.agents\AGENTS.md
- Supervisor: project-specific proof workflow
- Self-heal: not_applicable

### `github_runner`

- Role: `ci_execution_worker`
- Capabilities: runtime_validate
- Canonical sources: C:\Users\Lauri\.agents\Start-GitHubRunnerHidden.ps1
- Live status: GitHub runner registration + exact workflow run
- Independent recovery: other online compatible runners
- Resources: runner work directory
- Dependents: github_actions
- Runbook: C:\Users\Lauri\.agents\Start-GitHubRunnerHidden.ps1
- Supervisor: runner-specific hidden launcher
- Self-heal: runner-specific; do not infer fleet health from one process

### `local_git`

- Role: `local_source_truth`
- Capabilities: source_read, repository_mutate
- Canonical sources: per-repo filesystem/.git/worktrees
- Live status: git status; HEAD; recent git log --all history; local/remote branch refs; worktree list
- Independent recovery: preserve dirty/foreign state; use isolated worktree
- Resources: working tree; .git/worktrees
- Dependents: chatgpt_session; execution_workers
- Runbook: C:\Users\Lauri\.agents\RULES.md
- Supervisor: none
- Self-heal: not_applicable

### `github`

- Role: `remote_publication_and_workflow_evidence`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: organicoverlords/*
- Live status: GitHub API/connector exact repo, PR, issue, check, workflow state
- Independent recovery: local Git remains local source truth; publication waits for GitHub
- Resources: remote refs; issues; PRs; workflow runs
- Dependents: chatgpt_session; execution_workers
- Runbook: C:\Users\Lauri\.agents\RULES.md
- Supervisor: external service
- Self-heal: external

### `agent_rules`

- Role: `authority:agent-rules`
- Capabilities: source_read, repository_mutate
- Canonical sources: C:\Users\Lauri\.agents\RULES.md; C:\Users\Lauri\.agents\AGENTS.md; organicoverlords/agents@main
- Live status: read exact agents/main commit plus RULES.md and AGENTS.md; reconcile local/remote ref when mutation matters
- Independent recovery: current explicit user instruction and live repo/runtime evidence remain higher authority if the rules repo is temporarily unavailable
- Resources: RULES.md; AGENTS.md; main
- Dependents: chatgpt_session; execution_workers; repo_rule_pointer
- Runbook: C:\Users\Lauri\.agents\RULES.md
- Supervisor: none
- Self-heal: not_applicable

### `repo_rule_pointer`

- Role: `navigation:rule-pointer`
- Capabilities: source_read
- Canonical sources: pointer-only AGENTS.md/CLAUDE.md/equivalent
- Live status: verify pointer names shared .agents RULES.md and AGENTS.md and contains no copied policy body
- Independent recovery: read agent_rules directly; a missing/stale pointer never creates a second policy authority
- Resources: pointer files only
- Dependents: chatgpt_session; execution_workers
- Runbook: C:\Users\Lauri\.agents\RULES.md
- Supervisor: none
- Self-heal: not_applicable

### `north_star`

- Role: `direction:project`
- Capabilities: source_read
- Canonical sources: organicoverlords/agents@main docs/repos/<repo>/ North Star/equivalent
- Live status: read current Agents-repo product direction; derive obvious unmet product outcomes into actionable work and prefer visible progress
- Independent recovery: current user direction outranks stale prose
- Resources: docs/repos/<repo>/ North Star/equivalent
- Dependents: chatgpt_session; execution_workers
- Runbook: organicoverlords/agents@main docs/repos/<repo>/
- Supervisor: organicoverlords/agents
- Self-heal: not_applicable

### `stack_atlas`

- Role: `derived:stack-atlas-navigation`
- Capabilities: source_read, runtime_validate
- Canonical sources: organicoverlords/agents@main docs/repos/regression-research/STACK_ATLAS_NORTH_STAR.md; C:\\Users\\Lauri\\Desktop\\vault\\tools\\stack_atlas.py; C:\\Users\\Lauri\\Desktop\\vault\\docs\\assistant-stack-operational-atlas.md
- Live status: python C:\\Users\\Lauri\\Desktop\\vault\\tools\\stack_atlas.py bootstrap-glance; python C:\\Users\\Lauri\\Desktop\\vault\\tools\\stack_atlas.py lookup stack_atlas
- Independent recovery: read canonical agent rules, project direction, and named live/source authorities directly; Atlas unavailability is not a permission gate
- Resources: Stack Atlas North Star; derived component map; feature index; generated operational manual
- Dependents: chatgpt_session; execution_workers
- Runbook: organicoverlords/agents@main docs/repos/regression-research/STACK_ATLAS_NORTH_STAR.md
- Supervisor: none; derived map generated from named authorities
- Self-heal: not_applicable

### `chatgpt_memory`

- Role: `context:disabled-product-memory`
- Capabilities: memory_read
- Canonical sources: ChatGPT Memory disabled by current account configuration
- Live status: disabled; not a continuity source and never current-state authority
- Independent recovery: current conversation; targeted Vault history
- Resources: none
- Dependents: none
- Runbook: none
- Supervisor: ChatGPT
- Self-heal: product_managed

### `memory_bank`

- Role: `context:bounded-history`
- Capabilities: memory_read, memory_write
- Canonical sources: tools/memory_bank.py; memory/memory-bank.jsonl; origin/memory/live
- Live status: memory_bank.py validate / bounded read; writes reconcile through dedicated origin/memory/live; protected main/master/dev/develop are forbidden publication targets
- Independent recovery: continue without optional history enrichment
- Resources: memory-bank.jsonl; memory/live
- Dependents: chatgpt_session; execution_workers
- Runbook: memory/README.md
- Supervisor: none
- Self-heal: not_applicable

### `worker_reports`

- Role: `projection:worker-self-report`
- Capabilities: source_read
- Canonical sources: C:\Users\Lauri\Desktop\vault\worker-reports\current\<automation-id>.md; C:\Users\Lauri\Desktop\vault\worker-reports\history\_reports\*.json
- Live status: read current/<automation-id>.md snapshots directly for recent worker output; use immutable worker-reports\history\_reports metadata only for past-run chronology; when visual_proof_run is present inspect that local run under C:\P3Proofs plus reviewed.json; reconcile important progress/liveness claims with repo/runtime/CI/artifact evidence
- Independent recovery: read canonical repo/runtime/CI/artifact evidence directly
- Resources: worker-reports/current/<automation-id>.md; worker-reports/history/_reports/*.json
- Dependents: chatgpt_session
- Runbook: C:\Users\Lauri\Desktop\vault\worker-reports
- Supervisor: none
- Self-heal: not_applicable

### `swarm_topology`

- Role: `contract:chatgpt-worker-swarm-topology`
- Capabilities: source_read
- Canonical sources: C:\Users\Lauri\Desktop\vault\04 Operating Contracts\chatgpt-swarm-topology.json; C:\Users\Lauri\.agents\RULES.md; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\fresh-worker-generation-launch.md
- Live status: python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance; python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>
- Independent recovery: python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>; python C:\Users\Lauri\Desktop\vault\tools\worker_recovery_guard.py <actor-worker-id> <target-worker-id>; perform one targeted is_enabled=true write only when the guard authorizes the exact same-partition sibling; never self-administer or cross partitions
- Resources: S1 five recurring slots; S2 five recurring slots; manual/on-demand worker population
- Dependents: chatgpt_session; execution_workers; chatgpt_automations
- Runbook: C:\Users\Lauri\Desktop\vault\04 Operating Contracts\chatgpt-swarm-topology.json; C:\Users\Lauri\Desktop\vault\04 Operating Contracts\fresh-worker-generation-launch.md
- Supervisor: distributed same-partition recurring workers; supervising/manual ChatGPT session may perform the same guarded recovery; operator handoff is administrative fallback only
- Self-heal: bounded_same_partition_peer_recovery

### `chatgpt_session`

- Role: `session:user-facing`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: current conversation; targeted Vault history; agent_rules; Atlas; current authorities
- Live status: current task + relevant live-source refresh
- Independent recovery: current conversation; targeted Vault history; Atlas on stack work
- Resources: current task context
- Dependents: user
- Runbook: C:\Users\Lauri\.agents\RULES.md
- Supervisor: current ChatGPT session
- Self-heal: session_specific

### `execution_workers`

- Role: `executor:bounded`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: fresh-worker launch contract; agent_rules
- Live status: independent execution/activity evidence
- Independent recovery: python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>; python C:\Users\Lauri\Desktop\vault\tools\worker_recovery_guard.py <actor-worker-id> <target-worker-id>; preserve task/checkpoint and use another proven execution route for execution-path failures
- Resources: claimed scope; worktree; execution route
- Dependents: chatgpt_session
- Runbook: 04 Operating Contracts/fresh-worker-generation-launch.md
- Supervisor: distributed peer supervision for recurring workers; supervising/manual ChatGPT session may assist; BusyCoordinator is exact mutation collision control only
- Self-heal: same_partition_sibling_recovery_for_recurring_workers

### `chatgpt_automations`

- Role: `scheduler:recurrence`
- Capabilities: schedule
- Canonical sources: ChatGPT Automations state
- Live status: current automation enabled/schedule state only; not worker liveness, supervision, or recovery authority
- Independent recovery: same-partition recurring siblings or a supervising/manual ChatGPT session use fleet-watch plus worker_recovery_guard and may issue one targeted is_enabled=true write; scheduler listing is not the discovery path; present-turn work continues without recurrence
- Resources: timed recurrence and enabled state only
- Dependents: execution_workers
- Runbook: 04 Operating Contracts/fresh-worker-generation-launch.md
- Supervisor: platform recurrence service only; it does not supervise worker health or own swarm recovery
- Self-heal: not_swarm_supervision

### `github_actions`

- Role: `evidence:ci`
- Capabilities: runtime_validate
- Canonical sources: exact GitHub Actions run
- Live status: exact workflow run/check status
- Independent recovery: local proof may supplement, never impersonate exact CI
- Resources: workflow runs; checks
- Dependents: chatgpt_session; execution_workers
- Runbook: repo workflow files
- Supervisor: GitHub Actions
- Self-heal: external

## Process identity and blast radius

OS PIDs are ephemeral lookup keys only. `blast-radius --pid <pid>` resolves stable identity from executable/command line, ancestry, supervisor/config/resource evidence, then reports affected control paths and a destructive verdict.

MCP/VPS process identity is derived from executable, command line, ancestry, supervisor, and resource evidence; never infer safety from a tool name alone.
