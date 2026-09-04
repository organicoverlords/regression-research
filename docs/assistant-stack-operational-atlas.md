# Assistant Stack Operational Atlas

> Generated derived view. Current user instruction and named live/source authorities outrank it.

## Operating invariant

Atlas is a fast map for stack/infra only: locate the smallest relevant stack owner, entrypoint, dependency, or blast radius, then leave Atlas and work from that live owner. Do not use Atlas to navigate ordinary P3, Tiny3D, LowVRAM, or other product-repository work. Atlas does not plan work, establish product truth, or require deep lookups before ordinary reasoning.

## Capability routing

| Capability | Ordered adapter roles | Fallback |
| --- | --- | --- |
| `coordination` | live_ownership | `no_second_authority` |
| `source_read` | source_native_read -> verified_local_read -> public_read | `ordered_supported_fallback` |
| `repository_mutate` | repo_native_write -> verified_local_repo_write | `ordered_supported_fallback` |
| `runtime_validate` | local_runtime_validation -> equivalent_ci_validation | `ordered_supported_fallback` |
| `connected_account_action` | source_native_account_adapter | `none` |
| `artifact_create` | artifact_native_adapter | `none` |
| `schedule` | scheduler_adapter | `none` |
| `memory_read` | side_effect_free_memory_read | `none` |
| `memory_write` | audited_memory_write | `none` |

## Feature discovery

Use `find <query>` when you know the need but not the component. Search this derived index before proposing new stack machinery.

| Feature | Owner components | Entrypoints | Boundary |
| --- | --- | --- | --- |
| `vault.history` | memory_bank | memory_bank.py search; memory_bank.py context; memory_bank.py history; memory_bank.py timeline; memory_bank.py orient; memory_bank.py recent-titles; memory_bank.py changes | History/evidence only; use targeted indexed reads, never recursive Vault scans or current-state inference. |
| `project.current_truth` | agent_rules, north_star, local_git, github | shared .agents RULES.md + AGENTS.md; repo NORTH_STAR/equivalent; git status/HEAD + relevant branch/commit history; exact GitHub issue/PR/check/runtime evidence | Current project truth comes from the smallest relevant live authority, not Atlas, memory, reports, or dashboards. |
| `coordination.ownership` | busy_coordinator | busy-python.cmd inspect <scope>; claim; heartbeat; release; recover; snapshot | Exact mutation collision/ownership only; never infer backlog, liveness, priority, capacity, or progress. |
| `coordination.checkpoint_context` | busy_coordinator | busy-python.cmd inspect <scope>; claim --checkpoint; heartbeat --checkpoint; release --checkpoint | Exact-scope context only; never backlog, priority, handoff scheduling, liveness, or reassignment. Pending delivery work belongs in the project issue/PR. |
| `worker.reports` | worker_reports | C:\Users\Lauri\Desktop\vault\worker-reports\current\<automation-id>.md; C:\Users\Lauri\Desktop\vault\worker-reports\history\_reports\*.json | Self-report/navigation surface; visual proof pointers are PENDING_REVIEW until independent reviewed.json exists; verify important liveness/progress claims against repo/runtime/CI/artifact evidence. |
| `execution.transport` | vps_edge_ingress, mcp_front_door | production MCPv3/VPS process contract; plugin2 when available | Transport only; tool availability does not confer ownership, scheduling, or product authority. |

## Components

### `stack_atlas`

- Role: `navigation:stack-map`
- Capabilities: source_read
- Canonical sources: C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py; C:\Users\Lauri\Desktop\vault\docs\assistant-stack-operational-atlas.md
- Live status: lookup/find for stack component location and dependency map; blast-radius for disruptive process impact
- Independent recovery: use the named stack owner directly; Atlas unavailability never blocks already-located work
- Resources: stack component map; dependency map; entrypoints; blast-radius metadata
- Dependents: chatgpt_session; execution_workers
- Runbook: C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py
- Supervisor: none
- Self-heal: not_applicable

### `busy_coordinator`

- Role: `coordination_authority`
- Capabilities: coordination
- Canonical sources: %LOCALAPPDATA%\BusyCoordinator\busy-python.cmd; %LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json
- Live status: %LOCALAPPDATA%\BusyCoordinator\busy-python.cmd snapshot; inspect <scope>
- Independent recovery: %LOCALAPPDATA%\BusyCoordinator\busy-python.cmd recover
- Resources: %LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json
- Dependents: chatgpt_session; execution_workers
- Runbook: AGENTS.md; %LOCALAPPDATA%\BusyCoordinator\coordinator-contract.json
- Supervisor: none; CLI/service contract owns durable store semantics
- Self-heal: not_applicable

### `mcp_front_door`

- Role: `process_transport_front_door`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: %LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1; chatgpt-mcp-clean/src/front-door.ts
- Live status: root front-door health plus exact tool contract/semantic call; root / may remain on 3003; current MCPv3 production ingress bypasses it through the VPS Caddy + reverse-SSH edge to clone 3011; ordered static-array clone fallback is bounded experiment/fallback infrastructure, not proof of production clone continuity
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
- Canonical sources: %LOCALAPPDATA%\ChatGPTMcpClean\scripts\start-minimal-clone.ps1; %LOCALAPPDATA%\McpVpsEdge\start-tunnel.ps1; %LOCALAPPDATA%\ChatGPTMcpClean\scripts\set-direct-clone-funnel.ps1
- Live status: clone health; exact tool contract; process receipt/control route; direct public clone path plus OAuth authorization-server, protected-resource, and OpenID metadata handlers; 2026-09-03 production: https://5-61-91-127.sslip.io/mcp -> Caddy VPS -> persistent reverse SSH -> clone 3011; final scheduled path passed 100/100 initialize/initialized/start_process and live MCPv3 calls
- Independent recovery: VPS scheduled reverse tunnel reconnect is the current public-ingress recovery path; Tailscale Funnel is non-production fallback/diagnostic ingress only; preserve public clone identity/OAuth/shared receipts and all three clone metadata handlers; never leave a stale-regression generation in ordered fallback; client-visible no-arrival failure does not authorize backend/OAuth/receipt/port churn
- Resources: clone port; oauth.json; transport.jsonl; shared-process-receipts; process-control; VPS Caddy/reverse-SSH route; legacy Tailscale /clone-* handler; clone OAuth/OpenID metadata handlers
- Dependents: chatgpt_process_transport
- Runbook: %LOCALAPPDATA%\ChatGPTMcpClean\AGENTS.md; C:/Users/Lauri/Desktop/vault/01 Reports/2026-09-02_1458_EEST_MCP_runtime_source_reconciliation.md; C:/Users/Lauri/Desktop/vault/01 Reports/2026-09-02_1941_EEST_MCP_direct_clone_topology_recurrence_study.md; C:/Users/Lauri/Desktop/vault/01 Reports/2026-09-03_MCP_vps_edge_cutover.md
- Supervisor: instance launcher / owning generation
- Self-heal: generation_specific

### `vps_edge_ingress`

- Role: `public_mcp_edge_and_observer`
- Capabilities: source_read, runtime_validate, artifact_transfer
- Canonical sources: %LOCALAPPDATA%\McpVpsEdge\start-tunnel.ps1; %LOCALAPPDATA%\McpVpsEdge\vps_mcp_reverse_tunnel.py; %LOCALAPPDATA%\McpVpsEdge\publish-artifact.ps1; 5.61.91.127:/etc/caddy/Caddyfile
- Live status: https://5-61-91-127.sslip.io/edge-status; https://5-61-91-127.sslip.io/.well-known/oauth-protected-resource/mcp; Windows scheduled task McpVpsEdgeTunnel; VPS mcp-edge-health.timer
- Independent recovery: local clone can be tested directly without edge; edge failure must not authorize backend/OAuth/receipt churn; Tailscale may be used only as an explicitly revalidated non-production fallback
- Resources: VPS 5.61.91.127; public TCP 80/443; SSH TCP 22; VPS loopback 3011 reverse listener; /srv/mcp-artifacts; /var/lib/mcp-edge/status.json
- Dependents: mcp_minimal_clone; file_transfer; chatgpt_process_transport
- Runbook: 01 Reports/2026-09-03_MCP_vps_edge_cutover.md
- Supervisor: Caddy/systemd on VPS plus Windows McpVpsEdgeTunnel scheduled task
- Self-heal: reverse tunnel reconnect loop + systemd-managed Caddy/health timers

### `tailscale_ingress`

- Role: `legacy_network_ingress_fallback`
- Capabilities: source_read, runtime_validate
- Canonical sources: C:\Program Files\Tailscale\tailscale.exe; %LOCALAPPDATA%\ChatGPTMcpClean\scripts\set-direct-clone-funnel.ps1
- Live status: non-production after 2026-09-03 VPS cutover; tailscale status; tailscale serve status --json; if fallback is attempted, require a fresh full MCP handshake before relying on it
- Independent recovery: local backend/clone can be tested directly without public ingress; ingress failure must not authorize backend churn
- Resources: Serve/Funnel config; HTTPS listener; /clone-* route handlers; OAuth/OpenID metadata route handlers
- Dependents: mcp_minimal_clone
- Runbook: %LOCALAPPDATA%\ChatGPTMcpClean\scripts\set-direct-clone-funnel.ps1
- Supervisor: Tailscale service
- Self-heal: service_specific; route edits require explicit verification

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
- Canonical sources: C:\P3Proofs; repo-local proof/acceptance contract; reviewed.json when independent review exists
- Live status: exact proof run directory; capture manifest; reviewed.json; user-visible acceptance target
- Independent recovery: classify why the previous proof failed and change a load-bearing condition before another expensive retry
- Resources: capture; manifest; review verdict; acceptance requirement
- Dependents: p3; worker_reports
- Runbook: C:\Users\Lauri\.agents\contexts\p3.md
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
- Canonical sources: repo NORTH_STAR/equivalent
- Live status: read current direction doc; derive obvious unmet product outcomes into actionable work and prefer visible progress
- Independent recovery: current user direction outranks stale prose
- Resources: NORTH_STAR/equivalent
- Dependents: chatgpt_session; execution_workers
- Runbook: repo NORTH_STAR/equivalent
- Supervisor: repo-local
- Self-heal: not_applicable

### `chatgpt_memory`

- Role: `context:chatgpt-continuity`
- Capabilities: memory_read
- Canonical sources: current conversation; ChatGPT Memory
- Live status: current conversation and delivered ChatGPT Memory
- Independent recovery: current conversation; targeted Vault history when useful
- Resources: ChatGPT Memory
- Dependents: chatgpt_session
- Runbook: 04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt
- Supervisor: ChatGPT
- Self-heal: product_managed

### `memory_bank`

- Role: `context:bounded-history`
- Capabilities: memory_read, memory_write
- Canonical sources: tools/memory_bank.py; memory/memory-bank.jsonl; origin/memory/live
- Live status: memory_bank.py validate / bounded read; writes reconcile through dedicated origin/memory/live; protected main/master/dev/develop are forbidden publication targets
- Independent recovery: continue without optional history enrichment
- Resources: memory-bank.jsonl; behavior-authority-registry.json; memory/live
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

### `chatgpt_session`

- Role: `session:user-facing`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: current conversation; ChatGPT Memory; agent_rules; Atlas; current authorities
- Live status: current task + relevant live-source refresh
- Independent recovery: current conversation/ChatGPT Memory; Atlas on stack work; Vault history optional
- Resources: current task context
- Dependents: user
- Runbook: 04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt
- Supervisor: current ChatGPT session
- Self-heal: session_specific

### `execution_workers`

- Role: `executor:bounded`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: fresh-worker launch contract; agent_rules
- Live status: independent execution/activity evidence
- Independent recovery: preserve task/checkpoint; use another proven execution route
- Resources: claimed scope; worktree; execution route
- Dependents: chatgpt_session
- Runbook: 04 Operating Contracts/fresh-worker-generation-launch.md
- Supervisor: ChatGPT + BusyCoordinator ownership
- Self-heal: worker_specific

### `chatgpt_automations`

- Role: `scheduler:recurrence`
- Capabilities: schedule
- Canonical sources: ChatGPT Automations state
- Live status: current automation list/run state
- Independent recovery: present-turn work continues without scheduler
- Resources: timed recurrence only
- Dependents: execution_workers
- Runbook: 04 Operating Contracts/fresh-worker-generation-launch.md
- Supervisor: ChatGPT scheduler
- Self-heal: service_specific

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
