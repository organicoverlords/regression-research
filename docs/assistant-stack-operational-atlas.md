# Assistant Stack Operational Atlas

> Generated derived view. Current user instruction and named live/source authorities outrank it.

## Operating invariant

For stack/infra work, consume the compact Atlas first and deep-lookup every relevant component before reasoning, answering, redesigning, repairing, or mutating. Fetch status from the named live route. If identity, dependency role, supervisor, self-heal, blast radius, or independent recovery is unknown, disruptive action is blocked.

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

## Product flow

`LowVRAM -> Tiny3D -> P3`

Product-stage ownership comes from the current product repo architecture contracts. Historical migration issues, old handoffs, and progress-board projections may explain lineage but cannot redefine the active boundary.

## Components

### `busy_coordinator`

- Role: `coordination_authority`
- Capabilities: coordination
- Canonical sources: %LOCALAPPDATA%\BusyCoordinator\busy-python.cmd; %LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json
- Live status: %LOCALAPPDATA%\BusyCoordinator\busy-python.cmd snapshot; inspect <scope>
- Independent recovery: %LOCALAPPDATA%\BusyCoordinator\busy-python.cmd recover
- Resources: %LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json
- Dependents: chatgpt_orchestrator; execution_workers
- Runbook: AGENTS.md; tools/busy_authority.py
- Supervisor: none; CLI/service contract owns durable store semantics
- Self-heal: not_applicable

### `mcp_front_door`

- Role: `process_transport_front_door`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: %LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1; chatgpt-mcp-clean/src/front-door.ts
- Live status: front-door health plus exact tool contract/semantic call; ordered static-array fallback + backend connection reuse; verify the live route before disruption
- Independent recovery: inactive backend generation + atomic front-door switch
- Resources: front-door port; active-backend.json; process-routes.json
- Dependents: chatgpt_process_transport
- Runbook: chatgpt-mcp-clean/AGENTS.md; chatgpt-mcp-clean/keepalive.ps1
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
- Runbook: chatgpt-mcp-clean/AGENTS.md; chatgpt-mcp-clean/keepalive.ps1
- Supervisor: ChatGPTMcpClean keepalive Backend role
- Self-heal: supervisor_managed

### `mcp_minimal_clone`

- Role: `generation_pinned_process_transport_clone`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: chatgpt-mcp-clean/scripts/start-minimal-clone.ps1
- Live status: clone health; exact tool contract; process receipt/control route; 2026-09-02 reconciliation checkpoint: clone-a fallback must contain only generations compatible with merged master process contract; verify route + generation + authenticated smoke
- Independent recovery: sibling clone or stable front door when proven compatible; preserve public clone identity/OAuth/shared receipts and never leave a stale-regression generation in ordered fallback
- Resources: clone port; oauth.json; transport.jsonl; shared-process-receipts; process-control
- Dependents: chatgpt_process_transport
- Runbook: chatgpt-mcp-clean/AGENTS.md; C:/Users/Lauri/Desktop/vault/01 Reports/2026-09-02_1458_EEST_MCP_runtime_source_reconciliation.md
- Supervisor: instance launcher / owning generation
- Self-heal: generation_specific

### `desktop_commander_watchdog`

- Role: `machine_transport_supervisor`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: %LOCALAPPDATA%\DesktopCommanderFallback\watchdog.ps1
- Live status: watchdog process; device/relay connection; semantic execution call
- Independent recovery: MCP process route only when independently proven available and sufficient
- Resources: Commander fallback install; relay session
- Dependents: desktop_commander_remote
- Runbook: %LOCALAPPDATA%\DesktopCommanderFallback\watchdog.ps1
- Supervisor: host startup / watchdog process
- Self-heal: owns Commander child recovery

### `desktop_commander_remote`

- Role: `machine_transport_relay_client`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: %LOCALAPPDATA%\DesktopCommanderFallback\app\...\desktop-commander\dist\index.js
- Live status: device online is insufficient; require Commander semantic operation
- Independent recovery: must prove another machine execution route before disruption
- Resources: hosted relay/device session
- Dependents: desktop_commander_local; chatgpt_machine_execution; execution_workers
- Runbook: %LOCALAPPDATA%\DesktopCommanderFallback\watchdog.ps1
- Supervisor: desktop_commander_watchdog
- Self-heal: watchdog_expected_but_not_safe-to-kill-proof

### `desktop_commander_local`

- Role: `machine_transport_execution_child`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: %LOCALAPPDATA%\DesktopCommanderFallback\app\...\desktop-commander\dist\index.js
- Live status: Commander semantic file/process operation
- Independent recovery: prove another machine execution route before disruption
- Resources: machine files; spawned process handles
- Dependents: chatgpt_machine_execution; execution_workers
- Runbook: %LOCALAPPDATA%\DesktopCommanderFallback\watchdog.ps1
- Supervisor: desktop_commander_remote
- Self-heal: parent/watchdog_may_recreate; never assume without proof

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

### `vault_history`

- Role: `context:history-notebook`
- Capabilities: memory_read, memory_write
- Canonical sources: C:\Users\Lauri\Desktop\vault\memory; tools/memory_bank.py
- Live status: targeted Vault search/context/history/timeline/recent-titles when needed; do not recursively scan the Vault filesystem for ordinary recall
- Independent recovery: continue without Vault; current conversation/memory and live sources remain available
- Resources: memory-bank.jsonl; behavior-authority-registry.json
- Dependents: chatgpt_orchestrator; execution_workers
- Runbook: memory/README.md
- Supervisor: none
- Self-heal: not_applicable

### `local_git`

- Role: `local_source_truth`
- Capabilities: source_read, repository_mutate
- Canonical sources: per-repo filesystem/.git/worktrees
- Live status: git status; HEAD; origin/main; worktree list
- Independent recovery: preserve dirty/foreign state; use isolated worktree
- Resources: working tree; .git/worktrees
- Dependents: chatgpt_orchestrator; execution_workers
- Runbook: repo AGENTS.md
- Supervisor: none
- Self-heal: not_applicable

### `github`

- Role: `remote_publication_and_workflow_evidence`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: organicoverlords/*
- Live status: GitHub API/connector exact repo, PR, issue, check, workflow state
- Independent recovery: local Git remains local source truth; publication waits for GitHub
- Resources: remote refs; issues; PRs; workflow runs
- Dependents: chatgpt_orchestrator; execution_workers
- Runbook: repo AGENTS.md
- Supervisor: external service
- Self-heal: external

### `dev_progress_board`

- Role: `derived_progress_projection`
- Capabilities: source_read
- Canonical sources: C:\Users\Lauri\Desktop\DevProgressBoard
- Live status: board process/feed age; never treat projection as authority
- Independent recovery: read canonical repo/coordinator/runtime sources directly
- Resources: operator-live.json; board state
- Dependents: human_orientation; chatgpt_orientation
- Runbook: C:\Users\Lauri\Desktop\DevProgressBoard
- Supervisor: Board-Watchdog.ps1 / feed scripts
- Self-heal: projection-specific

### `shared_policy`

- Role: `authority:cross-project`
- Capabilities: source_read
- Canonical sources: C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md
- Live status: read current shared policy
- Independent recovery: current instruction + repo rules remain authoritative
- Resources: generated policy blocks
- Dependents: chatgpt_orchestrator; execution_workers
- Runbook: C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md
- Supervisor: none
- Self-heal: not_applicable

### `repo_agents`

- Role: `authority:repo-local`
- Capabilities: source_read, repository_mutate
- Canonical sources: admitted worktree AGENTS.md
- Live status: read admitted-worktree AGENTS.md
- Independent recovery: block repo mutation until readable
- Resources: AGENTS.md
- Dependents: chatgpt_orchestrator; execution_workers
- Runbook: repo AGENTS.md
- Supervisor: repo-local
- Self-heal: not_applicable

### `north_star`

- Role: `direction:project`
- Capabilities: source_read
- Canonical sources: repo NORTH_STAR/equivalent
- Live status: read current direction doc
- Independent recovery: current user direction outranks stale prose
- Resources: NORTH_STAR/equivalent
- Dependents: chatgpt_orchestrator; execution_workers
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
- Dependents: chatgpt_orchestrator
- Runbook: 04 Operating Contracts/fresh-chat-startup-orientation.md
- Supervisor: ChatGPT
- Self-heal: product_managed

### `memory_bank`

- Role: `context:bounded-history`
- Capabilities: memory_read, memory_write
- Canonical sources: tools/memory_bank.py; memory/memory-bank.jsonl
- Live status: memory_bank.py validate / bounded read
- Independent recovery: continue without optional history enrichment
- Resources: memory-bank.jsonl; behavior-authority-registry.json
- Dependents: chatgpt_orchestrator; execution_workers
- Runbook: memory/README.md
- Supervisor: none
- Self-heal: not_applicable

### `chatgpt_orchestrator`

- Role: `orchestrator:user-facing`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: current conversation; ChatGPT Memory; Atlas; current authorities
- Live status: current task + relevant live-source refresh
- Independent recovery: current conversation/ChatGPT Memory; Atlas on stack work; Vault history optional
- Resources: current task context
- Dependents: user
- Runbook: 04 Operating Contracts/fresh-chat-startup-orientation.md
- Supervisor: current ChatGPT session
- Self-heal: session_specific

### `execution_workers`

- Role: `executor:bounded`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: fresh-worker launch contract; repo AGENTS.md
- Live status: independent execution/activity evidence
- Independent recovery: preserve task/checkpoint; use another proven execution route
- Resources: claimed scope; worktree; execution route
- Dependents: chatgpt_orchestrator
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
- Dependents: chatgpt_orchestrator; execution_workers
- Runbook: repo workflow files
- Supervisor: GitHub Actions
- Self-heal: external

### `operator_live`

- Role: `projection:near-live`
- Capabilities: source_read
- Canonical sources: C:\Users\Lauri\Desktop\DevProgressBoard\state\operator-live.json
- Live status: projection timestamp/age; reconcile canonical sources
- Independent recovery: read coordinator/Git/CI/runtime directly
- Resources: operator-live.json
- Dependents: chatgpt_orientation
- Runbook: C:\Users\Lauri\Desktop\DevProgressBoard
- Supervisor: DevProgressBoard feeds
- Self-heal: projection_specific

### `lowvram`

- Role: `generator:image_to_3d`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: C:\Users\Lauri\Desktop\lowvram3d-repo; C:\Users\Lauri\Desktop\lowvram3d-repo\README.md; C:\Users\Lauri\Desktop\lowvram3d-repo\docs\NORTH_STAR.md; C:\Users\Lauri\Desktop\lowvram3d-repo\docs\PIPELINE_CONTRACT.md
- Live status: read current LowVRAM repo architecture before historical migration/issues; inspect current generator filesystem/Git/runtime as applicable
- Independent recovery: preserve valid generated geometry; downstream failures stay downstream rather than moving rigging/animation ownership back into LowVRAM
- Resources: source recovery; image-to-3D generation; geometry; textures; provenance; producer visual QA
- Dependents: tiny3d
- Runbook: C:\Users\Lauri\Desktop\lowvram3d-repo\AGENTS.md; C:\Users\Lauri\Desktop\lowvram3d-repo\README.md; C:\Users\Lauri\Desktop\lowvram3d-repo\docs\NORTH_STAR.md
- Supervisor: project-specific
- Self-heal: project-specific

### `asset_library`

- Role: `storage:tiny3d_asset_library`
- Capabilities: source_read
- Canonical sources: C:\Users\Lauri\Desktop\Tiny3D_LIBRARY; C:\Users\Lauri\Desktop\tiny3d\README.md
- Live status: Tiny3D owns catalogue/library semantics; inspect current library contents only when asset state matters
- Independent recovery: rebuild derived Tiny3D index state from preserved content-addressed assets; do not invent a separate product authority
- Resources: C:\Users\Lauri\Desktop\Tiny3D_LIBRARY; .tiny3d/library/index-v1.json
- Dependents: tiny3d
- Runbook: C:\Users\Lauri\Desktop\tiny3d\README.md
- Supervisor: Tiny3D
- Self-heal: product-specific

### `tinylab`

- Role: `legacy_name:not_active_product_authority`
- Capabilities: source_read
- Canonical sources: C:\Users\Lauri\Desktop\TinyLab; C:\Users\Lauri\Desktop\tiny3d\README.md
- Live status: historical compatibility/name only; current Tiny3D README/North Star define the active post-generation product
- Independent recovery: resolve current post-generation behavior through Tiny3D; use TinyLab only for historical compatibility/provenance when needed
- Resources: historical tinylab.* schema identifiers and legacy workspace
- Dependents: none
- Runbook: C:\Users\Lauri\Desktop\tiny3d\README.md
- Supervisor: none
- Self-heal: not_applicable

### `tiny3d`

- Role: `product:post_generation_asset_compiler`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: C:\Users\Lauri\Desktop\tiny3d; C:\Users\Lauri\Desktop\tiny3d\README.md; C:\Users\Lauri\Desktop\tiny3d\docs\TINY3D_NORTH_STAR.md
- Live status: read current Tiny3D repo architecture before historical migration/issues; inspect current compiler/library Git/runtime evidence as applicable
- Independent recovery: consume immutable generator outputs; downstream preparation failures do not move ownership back into LowVRAM
- Resources: compilation; rigging/skinning; animation/deformation preparation; validation/adapters; packaging/lifecycle evidence; catalogue/library
- Dependents: p3
- Runbook: C:\Users\Lauri\Desktop\tiny3d\AGENTS.md; C:\Users\Lauri\Desktop\tiny3d\README.md; C:\Users\Lauri\Desktop\tiny3d\docs\TINY3D_NORTH_STAR.md
- Supervisor: project-specific
- Self-heal: project-specific

### `p3`

- Role: `consumer:game_runtime_acceptance`
- Capabilities: source_read, repository_mutate, runtime_validate
- Canonical sources: C:\Users\Lauri\Documents\Unreal Projects\p3
- Live status: inspect current P3 repo/runtime evidence for Unreal materialization and gameplay acceptance
- Independent recovery: Tiny3D structural/compiler evidence never substitutes for returned P3 runtime proof
- Resources: Unreal/game materialization; runtime acceptance; gameplay/visual proof
- Dependents: none
- Runbook: C:\Users\Lauri\Documents\Unreal Projects\p3\AGENTS.md
- Supervisor: project-specific
- Self-heal: project-specific

## Process identity and blast radius

OS PIDs are ephemeral lookup keys only. `blast-radius --pid <pid>` resolves stable identity from executable/command line, ancestry, supervisor/config/resource evidence, then reports affected control paths and a destructive verdict.

Commander and MCP are separate declared process trees. Never infer independence from tool names: observed shared-resource coupling is additional evidence and must be included in blast-radius analysis.
