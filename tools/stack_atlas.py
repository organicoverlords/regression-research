from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from concurrent.futures import ThreadPoolExecutor

try:
    from .capability_routing import load_policy, validate_policy
except ImportError:
    from capability_routing import load_policy, validate_policy

ROOT = Path(__file__).resolve().parents[1]
BUSY_STORE = r"%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json"
MCP_ROOT = r"%LOCALAPPDATA%\ChatGPTMcpClean"
VPS_EDGE_ROOT = r"%LOCALAPPDATA%\McpVpsEdge"
AGENT_RULES_ROOT = r"C:\Users\Lauri\.agents"
AGENT_RULES_REMOTE = "organicoverlords/agents@main"
ATLAS_LIBRARY_PATH = "/Agent Bootstrap/stack-atlas.json"
CAPABILITY_POLICY_PATH = ROOT / "tests" / "fixtures" / "capability-routing-policy.json"
COMPONENT_ALIASES = {
    "chatgpt": "chatgpt_session",
    "webgpt": "chatgpt_session",
    "mcp": "mcp_front_door",
    "plugin2": "mcp_front_door",
    "mcpv3": "vps_edge_ingress",
    "coordinator": "busy_coordinator",
    "busy": "busy_coordinator",
    "tailscale": "tailscale_ingress",
    "funnel": "tailscale_ingress",
    "vps": "vps_edge_ingress",
    "edge": "vps_edge_ingress",
    "vps edge": "vps_edge_ingress",
    "mcp edge": "vps_edge_ingress",
    "transfer": "file_transfer",
    "file transfer": "file_transfer",
    "visual proof": "visual_proof",
    "proof": "visual_proof",
    "worker": "execution_workers",
    "workers": "execution_workers",
    "rules": "agent_rules",
    "agent rules": "agent_rules",
    "policy": "agent_rules",
    "repo rules": "repo_rule_pointer",
    "ci": "github_actions",
    "atlas": "stack_atlas",
    "stack atlas": "stack_atlas",
    "stack-atlas": "stack_atlas",
}

ATLAS_CONTRACT = {
    "authority": "DERIVED_OPERATIONAL_VIEW_NOT_AUTHORITY",
    "scope": "STACK_INFRA_MAP_ONLY; product repositories such as P3, Tiny3D, and LowVRAM are outside Atlas",
    "stack_work_gate": "for stack/infra work only, use Atlas as a fast map to locate the smallest relevant stack owner, dependencies, entrypoints, and blast radius; once located, leave Atlas and use the live owner",
    "pid_semantics": "PID is an ephemeral live lookup key only; stable identity comes from executable/command line/ancestry/supervisor/config/resources",
    "destructive_gate": "unknown component identity, dependency role, supervisor, self-heal, blast radius, or independent recovery means BLOCK destructive action",
    "live_status": "fetch from the named live authority at use time; Atlas never promotes cached status to current truth",
}
COMPONENTS: dict[str, dict[str, Any]] = {
    "stack_atlas": {
        "role": "navigation:stack-map",
        "capabilities": ["source_read"],
        "canonical_sources": [str(ROOT / "tools" / "stack_atlas.py"), str(ROOT / "docs" / "assistant-stack-operational-atlas.md")],
        "live_status": ["lookup/find for stack component location and dependency map; blast-radius for disruptive process impact"],
        "supervisor": "none",
        "self_heal": "not_applicable",
        "independent_recovery": ["use the named stack owner directly; Atlas unavailability never blocks already-located work"],
        "resources": ["stack component map", "dependency map", "entrypoints", "blast-radius metadata"],
        "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": [str(ROOT / "tools" / "stack_atlas.py")],
    },
    "busy_coordinator": {
        "role": "coordination_authority",
        "capabilities": ["coordination"],
        "canonical_sources": [r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd", BUSY_STORE],
        "live_status": [r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd snapshot", "inspect <scope>"],
        "supervisor": "none; CLI/service contract owns durable store semantics",
        "self_heal": "not_applicable",
        "independent_recovery": [r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd recover"],
        "resources": [BUSY_STORE],
        "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": ["AGENTS.md", r"%LOCALAPPDATA%\BusyCoordinator\coordinator-contract.json"],
    },
    "mcp_front_door": {
        "role": "process_transport_front_door",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": [r"%LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1", "chatgpt-mcp-clean/src/front-door.ts"],
        "live_status": [
            "root front-door health plus exact tool contract/semantic call",
            "root / may remain on 3003; current MCPv3 production ingress bypasses it through the VPS Caddy + reverse-SSH edge to clone 3011",
            "ordered static-array clone fallback is bounded experiment/fallback infrastructure, not proof of production clone continuity",
        ],
        "supervisor": "ChatGPTMcpClean keepalive FrontDoor role",
        "self_heal": "supervisor_managed_but_not_permission_to_disrupt",
        "independent_recovery": ["inactive backend generation for root + atomic front-door switch; do not use root recovery to rewrite direct clone handlers"],
        "resources": ["front-door port", "active-backend.json", "process-routes.json"],
        "dependents": ["chatgpt_process_transport"],
        "runbook": [MCP_ROOT + r"\AGENTS.md", MCP_ROOT + r"\keepalive.ps1"],
    },
    "mcp_backend": {
        "role": "replaceable_process_transport_backend",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": [r"%LOCALAPPDATA%\ChatGPTMcpClean\start.ps1", r"%LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1"],
        "live_status": [
            "backend health",
            "exact tools/list schema",
            "semantic process call",
            "durable process contract: read_output max 32000; start_process default wait 750 ms; live cap 5 per caller; no rolling launch/token bucket",
        ],
        "supervisor": "ChatGPTMcpClean keepalive Backend role",
        "self_heal": "supervisor_managed",
        "independent_recovery": ["other backend generation behind stable front door"],
        "resources": ["backend port", "transport.jsonl"],
        "dependents": ["mcp_front_door"],
        "runbook": [MCP_ROOT + r"\AGENTS.md", MCP_ROOT + r"\keepalive.ps1"],
    },
    "mcp_minimal_clone": {
        "role": "generation_pinned_process_transport_clone",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": [MCP_ROOT + r"\scripts\start-minimal-clone.ps1", VPS_EDGE_ROOT + r"\start-tunnel.ps1", MCP_ROOT + r"\scripts\set-direct-clone-funnel.ps1"],
        "live_status": [
            "clone health",
            "exact tool contract",
            "process receipt/control route",
            "direct public clone path plus OAuth authorization-server, protected-resource, and OpenID metadata handlers",
            "2026-09-03 production: https://5-61-91-127.sslip.io/mcp -> Caddy VPS -> persistent reverse SSH -> clone 3011; final scheduled path passed 100/100 initialize/initialized/start_process and live MCPv3 calls",
        ],
        "supervisor": "instance launcher / owning generation",
        "self_heal": "generation_specific",
        "independent_recovery": [
            "VPS scheduled reverse tunnel reconnect is the current public-ingress recovery path; Tailscale Funnel is non-production fallback/diagnostic ingress only",
            "preserve public clone identity/OAuth/shared receipts and all three clone metadata handlers; never leave a stale-regression generation in ordered fallback",
            "client-visible no-arrival failure does not authorize backend/OAuth/receipt/port churn",
        ],
        "resources": ["clone port", "oauth.json", "transport.jsonl", "shared-process-receipts", "process-control", "VPS Caddy/reverse-SSH route", "legacy Tailscale /clone-* handler", "clone OAuth/OpenID metadata handlers"],
        "dependents": ["chatgpt_process_transport"],
        "runbook": [
            MCP_ROOT + r"\AGENTS.md",
            "C:/Users/Lauri/Desktop/vault/01 Reports/2026-09-02_1458_EEST_MCP_runtime_source_reconciliation.md",
            "C:/Users/Lauri/Desktop/vault/01 Reports/2026-09-02_1941_EEST_MCP_direct_clone_topology_recurrence_study.md",
            "C:/Users/Lauri/Desktop/vault/01 Reports/2026-09-03_MCP_vps_edge_cutover.md",
        ],
    },
    "vps_edge_ingress": {
        "role": "public_mcp_edge_and_observer",
        "capabilities": ["source_read", "runtime_validate", "artifact_transfer"],
        "canonical_sources": [VPS_EDGE_ROOT + r"\start-tunnel.ps1", VPS_EDGE_ROOT + r"\vps_mcp_reverse_tunnel.py", VPS_EDGE_ROOT + r"\publish-artifact.ps1", "5.61.91.127:/etc/caddy/Caddyfile"],
        "live_status": ["https://5-61-91-127.sslip.io/edge-status", "https://5-61-91-127.sslip.io/.well-known/oauth-protected-resource/mcp", "Windows scheduled task McpVpsEdgeTunnel", "VPS mcp-edge-health.timer"],
        "supervisor": "Caddy/systemd on VPS plus Windows McpVpsEdgeTunnel scheduled task",
        "self_heal": "reverse tunnel reconnect loop + systemd-managed Caddy/health timers",
        "independent_recovery": ["local clone can be tested directly without edge; edge failure must not authorize backend/OAuth/receipt churn", "Tailscale may be used only as an explicitly revalidated non-production fallback"],
        "resources": ["VPS 5.61.91.127", "public TCP 80/443", "SSH TCP 22", "VPS loopback 3011 reverse listener", "/srv/mcp-artifacts", "/var/lib/mcp-edge/status.json"],
        "dependents": ["mcp_minimal_clone", "file_transfer", "chatgpt_process_transport"],
        "runbook": ["01 Reports/2026-09-03_MCP_vps_edge_cutover.md"],
    },
    "tailscale_ingress": {
        "role": "legacy_network_ingress_fallback",
        "capabilities": ["source_read", "runtime_validate"],
        "canonical_sources": [r"C:\Program Files\Tailscale\tailscale.exe", MCP_ROOT + r"\scripts\set-direct-clone-funnel.ps1"],
        "live_status": ["non-production after 2026-09-03 VPS cutover", "tailscale status", "tailscale serve status --json", "if fallback is attempted, require a fresh full MCP handshake before relying on it"],
        "supervisor": "Tailscale service",
        "self_heal": "service_specific; route edits require explicit verification",
        "independent_recovery": ["local backend/clone can be tested directly without public ingress; ingress failure must not authorize backend churn"],
        "resources": ["Serve/Funnel config", "HTTPS listener", "/clone-* route handlers", "OAuth/OpenID metadata route handlers"],
        "dependents": ["mcp_minimal_clone"],
        "runbook": [MCP_ROOT + r"\scripts\set-direct-clone-funnel.ps1"],
    },
    "file_transfer": {
        "role": "artifact_transfer_bridge",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["current conversation file attachments", "ChatGPT files/library connector when exposed", "generated sandbox artifacts", VPS_EDGE_ROOT + r"\publish-artifact.ps1"],
        "live_status": ["source path exists", "destination path exists", "byte size matches", "SHA-256 matches end to end", "VPS artifact URL downloads identical bytes and expires after 24 hours"],
        "supervisor": "surface-specific; no single transfer authority",
        "self_heal": "route_specific",
        "independent_recovery": ["use another exposed transfer route only after preserving the same source bytes and hash"],
        "resources": ["artifact bytes", "source path/ref", "destination path/ref", "size", "SHA-256"],
        "dependents": ["chatgpt_session", "execution_workers", "visual_proof"],
        "runbook": [VPS_EDGE_ROOT + r"\publish-artifact.ps1"],
    },
    "visual_proof": {
        "role": "acceptance:user_visible_evidence",
        "capabilities": ["source_read", "runtime_validate"],
        "canonical_sources": [r"C:\P3Proofs", "repo-local proof/acceptance contract", "reviewed.json when independent review exists"],
        "live_status": ["exact proof run directory", "capture manifest", "reviewed.json", "user-visible acceptance target"],
        "supervisor": "project-specific proof workflow",
        "self_heal": "not_applicable",
        "independent_recovery": ["classify why the previous proof failed and change a load-bearing condition before another expensive retry"],
        "resources": ["capture", "manifest", "review verdict", "acceptance requirement"],
        "dependents": ["p3", "worker_reports"],
        "runbook": [AGENT_RULES_ROOT + r"\contexts\p3.md"],
    },
    "github_runner": {
        "role": "ci_execution_worker",
        "capabilities": ["runtime_validate"],
        "canonical_sources": [r"C:\Users\Lauri\.agents\Start-GitHubRunnerHidden.ps1"],
        "live_status": ["GitHub runner registration + exact workflow run"],
        "supervisor": "runner-specific hidden launcher",
        "self_heal": "runner-specific; do not infer fleet health from one process",
        "independent_recovery": ["other online compatible runners"],
        "resources": ["runner work directory"],
        "dependents": ["github_actions"],
        "runbook": [r"C:\Users\Lauri\.agents\Start-GitHubRunnerHidden.ps1"],
    },
    "local_git": {
        "role": "local_source_truth",
        "capabilities": ["source_read", "repository_mutate"],
        "canonical_sources": ["per-repo filesystem/.git/worktrees"],
        "live_status": ["git status", "HEAD", "recent git log --all history", "local/remote branch refs", "worktree list"],
        "supervisor": "none",
        "self_heal": "not_applicable",
        "independent_recovery": ["preserve dirty/foreign state; use isolated worktree"],
        "resources": ["working tree", ".git/worktrees"],
        "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": [AGENT_RULES_ROOT + r"\RULES.md"],
    },
    "github": {
        "role": "remote_publication_and_workflow_evidence",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["organicoverlords/*"],
        "live_status": ["GitHub API/connector exact repo, PR, issue, check, workflow state"],
        "supervisor": "external service",
        "self_heal": "external",
        "independent_recovery": ["local Git remains local source truth; publication waits for GitHub"],
        "resources": ["remote refs", "issues", "PRs", "workflow runs"],
        "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": [AGENT_RULES_ROOT + r"\RULES.md"],
    },
}

COMPONENTS.update({
    "agent_rules": {
        "role": "authority:agent-rules", "capabilities": ["source_read", "repository_mutate"],
        "canonical_sources": [AGENT_RULES_ROOT + r"\RULES.md", AGENT_RULES_ROOT + r"\AGENTS.md", AGENT_RULES_REMOTE],
        "live_status": ["read exact agents/main commit plus RULES.md and AGENTS.md; reconcile local/remote ref when mutation matters"],
        "supervisor": "none", "self_heal": "not_applicable",
        "independent_recovery": ["current explicit user instruction and live repo/runtime evidence remain higher authority if the rules repo is temporarily unavailable"],
        "resources": ["RULES.md", "AGENTS.md", "main"],
        "dependents": ["chatgpt_session", "execution_workers", "repo_rule_pointer"],
        "runbook": [AGENT_RULES_ROOT + r"\RULES.md"],
    },
    "repo_rule_pointer": {
        "role": "navigation:rule-pointer", "capabilities": ["source_read"],
        "canonical_sources": ["pointer-only AGENTS.md/CLAUDE.md/equivalent"],
        "live_status": ["verify pointer names shared .agents RULES.md and AGENTS.md and contains no copied policy body"],
        "supervisor": "none", "self_heal": "not_applicable",
        "independent_recovery": ["read agent_rules directly; a missing/stale pointer never creates a second policy authority"],
        "resources": ["pointer files only"],
        "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": [AGENT_RULES_ROOT + r"\RULES.md"],
    },
    "north_star": {
        "role": "direction:project", "capabilities": ["source_read"], "canonical_sources": ["repo NORTH_STAR/equivalent"],
        "live_status": ["read current direction doc; derive obvious unmet product outcomes into actionable work and prefer visible progress"], "supervisor": "repo-local", "self_heal": "not_applicable",
        "independent_recovery": ["current user direction outranks stale prose"], "resources": ["NORTH_STAR/equivalent"],
        "dependents": ["chatgpt_session", "execution_workers"], "runbook": ["repo NORTH_STAR/equivalent"],
    },
    "chatgpt_memory": {
        "role": "context:chatgpt-continuity", "capabilities": ["memory_read"],
        "canonical_sources": ["current conversation", "ChatGPT Memory"],
        "live_status": ["current conversation and delivered ChatGPT Memory"], "supervisor": "ChatGPT",
        "self_heal": "product_managed", "independent_recovery": ["current conversation; targeted Vault history when useful"],
        "resources": ["ChatGPT Memory"], "dependents": ["chatgpt_session"],
        "runbook": ["04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt"],
    },
    "memory_bank": {
        "role": "context:bounded-history", "capabilities": ["memory_read", "memory_write"],
        "canonical_sources": ["tools/memory_bank.py", "memory/memory-bank.jsonl", "origin/memory/live"],
        "live_status": ["memory_bank.py validate / bounded read", "writes reconcile through dedicated origin/memory/live; protected main/master/dev/develop are forbidden publication targets"],
        "supervisor": "none", "self_heal": "not_applicable", "independent_recovery": ["continue without optional history enrichment"],
        "resources": ["memory-bank.jsonl", "behavior-authority-registry.json", "memory/live"], "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": ["memory/README.md"],
    },
    "worker_reports": {
        "role": "projection:worker-self-report", "capabilities": ["source_read"],
        "canonical_sources": [r"C:\Users\Lauri\Desktop\vault\worker-reports\current\<automation-id>.md", r"C:\Users\Lauri\Desktop\vault\worker-reports\history\_reports\*.json"],
        "live_status": [r"read current/<automation-id>.md snapshots directly for recent worker output; use immutable worker-reports\history\_reports metadata only for past-run chronology; when visual_proof_run is present inspect that local run under C:\P3Proofs plus reviewed.json; reconcile important progress/liveness claims with repo/runtime/CI/artifact evidence"],
        "supervisor": "none", "self_heal": "not_applicable",
        "independent_recovery": ["read canonical repo/runtime/CI/artifact evidence directly"],
        "resources": ["worker-reports/current/<automation-id>.md", "worker-reports/history/_reports/*.json"], "dependents": ["chatgpt_session"],
        "runbook": [r"C:\Users\Lauri\Desktop\vault\worker-reports"],
    },
    "chatgpt_session": {
        "role": "session:user-facing", "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["current conversation", "ChatGPT Memory", "agent_rules", "Atlas", "current authorities"], "live_status": ["current task + relevant live-source refresh"],
        "supervisor": "current ChatGPT session", "self_heal": "session_specific", "independent_recovery": ["current conversation/ChatGPT Memory; Atlas on stack work; Vault history optional"],
        "resources": ["current task context"], "dependents": ["user"], "runbook": ["04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt"],
    },
    "execution_workers": {
        "role": "executor:bounded", "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["fresh-worker launch contract", "agent_rules"], "live_status": ["independent execution/activity evidence"],
        "supervisor": "ChatGPT + BusyCoordinator ownership", "self_heal": "worker_specific",
        "independent_recovery": ["preserve task/checkpoint; use another proven execution route"],
        "resources": ["claimed scope", "worktree", "execution route"], "dependents": ["chatgpt_session"],
        "runbook": ["04 Operating Contracts/fresh-worker-generation-launch.md"],
    },
    "chatgpt_automations": {
        "role": "scheduler:recurrence", "capabilities": ["schedule"], "canonical_sources": ["ChatGPT Automations state"],
        "live_status": ["current automation list/run state"], "supervisor": "ChatGPT scheduler", "self_heal": "service_specific",
        "independent_recovery": ["present-turn work continues without scheduler"], "resources": ["timed recurrence only"],
        "dependents": ["execution_workers"], "runbook": ["04 Operating Contracts/fresh-worker-generation-launch.md"],
    },
    "github_actions": {
        "role": "evidence:ci", "capabilities": ["runtime_validate"], "canonical_sources": ["exact GitHub Actions run"],
        "live_status": ["exact workflow run/check status"], "supervisor": "GitHub Actions", "self_heal": "external",
        "independent_recovery": ["local proof may supplement, never impersonate exact CI"], "resources": ["workflow runs", "checks"],
        "dependents": ["chatgpt_session", "execution_workers"], "runbook": ["repo workflow files"],
    },
})


FEATURE_INDEX: dict[str, dict[str, Any]] = {
    "vault.history": {
        "owner_components": ["memory_bank"],
        "triggers": ["vault", "history", "timeline", "chronology", "incident", "past decision", "context", "recent titles", "changes"],
        "entrypoints": ["memory_bank.py search", "memory_bank.py context", "memory_bank.py history", "memory_bank.py timeline", "memory_bank.py orient", "memory_bank.py recent-titles", "memory_bank.py changes"],
        "boundary": "History/evidence only; use targeted indexed reads, never recursive Vault scans or current-state inference.",
    },
    "project.current_truth": {
        "owner_components": ["agent_rules", "north_star", "local_git", "github"],
        "triggers": ["current truth", "project state", "repo state", "direction", "north star", "git", "github", "runtime"],
        "entrypoints": ["shared .agents RULES.md + AGENTS.md", "repo NORTH_STAR/equivalent", "git status/HEAD + relevant branch/commit history", "exact GitHub issue/PR/check/runtime evidence"],
        "boundary": "Current project truth comes from the smallest relevant live authority, not Atlas, memory, reports, or dashboards.",
    },
    "coordination.ownership": {
        "owner_components": ["busy_coordinator"],
        "triggers": ["busy", "ownership", "claim", "collision", "mutation scope", "release", "recover"],
        "entrypoints": ["busy-python.cmd inspect <scope>", "claim", "heartbeat", "release", "recover", "snapshot"],
        "boundary": "Exact mutation collision/ownership only; never infer backlog, liveness, priority, capacity, or progress.",
    },
    "coordination.checkpoint_context": {
        "owner_components": ["busy_coordinator"],
        "triggers": ["checkpoint", "resume", "scope context", "where did this scope leave off"],
        "entrypoints": ["busy-python.cmd inspect <scope>", "claim --checkpoint", "heartbeat --checkpoint", "release --checkpoint"],
        "boundary": "Exact-scope context only; never backlog, priority, handoff scheduling, liveness, or reassignment. Pending delivery work belongs in the project issue/PR.",
    },
    "worker.reports": {
        "owner_components": ["worker_reports"],
        "triggers": ["worker report", "worker status", "worker progress", "worker utilization", "stop reason", "tool drop", "liveness", "cedar", "alder", "juniper"],
        "entrypoints": [r"C:\Users\Lauri\Desktop\vault\worker-reports\current\<automation-id>.md", r"C:\Users\Lauri\Desktop\vault\worker-reports\history\_reports\*.json"],
        "boundary": "Self-report/navigation surface; visual proof pointers are PENDING_REVIEW until independent reviewed.json exists; verify important liveness/progress claims against repo/runtime/CI/artifact evidence.",
    },
    "execution.transport": {
        "owner_components": ["vps_edge_ingress", "mcp_front_door"],
        "triggers": ["process execution", "shell", "file access", "mcp", "mcpv3", "vps", "plugin2", "tool route"],
        "entrypoints": ["production MCPv3/VPS process contract", "plugin2 when available"],
        "boundary": "Transport only; tool availability does not confer ownership, scheduling, or product authority.",
    },
}

def _expand_env(value: str) -> str:
    return os.path.expandvars(value)


def build_bootstrap_atlas() -> dict[str, Any]:
    """Cheap mandatory pointer to the canonical generated Atlas."""
    validate_policy(load_policy())
    return {
        "schema": "atlas.v1",
        "must": "Map only: locate stack/infra owners and routes, then leave Atlas and read the live owner. Product repos stay outside Atlas.",
        "rules": r"C:\Users\Lauri\.agents\RULES.md",
        "vault": r"C:\Users\Lauri\Desktop\vault",
        "history_command": r"python -m tools.memory_bank orient --recent-events 20 --repo-events 3",
        "worker_reports": r"C:\Users\Lauri\Desktop\vault\worker-reports",
        "worker_metrics": r"C:\Users\Lauri\Desktop\vault\worker-reports\metrics.json",
        "mcp_activity_command": r"python C:\Users\Lauri\Desktop\vault\tools\connector_reliability.py --last-hours 1",
        "local_fallback": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py",
        "find": "find <query>",
        "lookup": "lookup <id-or-alias>",
        "blast": "blast-radius --pid <pid>",
    }



BOOTSTRAP_OBSERVATION_PATH = Path(os.path.expandvars(r"%LOCALAPPDATA%\ChatGPTMcpClean\.state\bootstrap-observations.jsonl"))


def _bootstrap_disk_trend(current_free_gb: float) -> dict[str, Any]:
    """Observed disk deltas for display only; never scheduling or authority state."""
    now = datetime.now(timezone.utc)
    observations: list[dict[str, Any]] = []
    try:
        if BOOTSTRAP_OBSERVATION_PATH.exists():
            from collections import deque
            with BOOTSTRAP_OBSERVATION_PATH.open("r", encoding="utf-8-sig") as handle:
                for raw in deque(handle, maxlen=256):
                    try:
                        item = json.loads(raw)
                        at = datetime.fromisoformat(str(item.get("at") or "").replace("Z", "+00:00")).astimezone(timezone.utc)
                        observations.append({"at": at, "free_gb": float(item["free_gb"])})
                    except Exception:
                        continue
    except OSError:
        observations = []

    previous = None
    candidates_24h = []
    for item in observations:
        age_hours = (now - item["at"]).total_seconds() / 3600
        if age_hours >= (1 / 60) and (previous is None or item["at"] > previous["at"]):
            previous = item
        if 12 <= age_hours <= 36:
            candidates_24h.append((abs(age_hours - 24), age_hours, item))

    def view(item: dict[str, Any], age_hours: float) -> dict[str, Any]:
        delta = current_free_gb - item["free_gb"]
        return {"age_hours": round(age_hours, 2), "previous_free_gb": round(item["free_gb"], 1), "delta_free_gb": round(delta, 1), "lost_gb": round(max(0.0, -delta), 1)}

    result: dict[str, Any] = {"previous": None, "approx_24h": None}
    if previous is not None:
        result["previous"] = view(previous, (now - previous["at"]).total_seconds() / 3600)
    if candidates_24h:
        _, age_hours, item = min(candidates_24h, key=lambda x: x[0])
        result["approx_24h"] = view(item, age_hours)

    try:
        if not observations or (now - observations[-1]["at"]).total_seconds() >= 300:
            BOOTSTRAP_OBSERVATION_PATH.parent.mkdir(parents=True, exist_ok=True)
            with BOOTSTRAP_OBSERVATION_PATH.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({"at": now.isoformat(), "free_gb": round(current_free_gb, 2)}, separators=(",", ":")) + "\n")
    except OSError:
        pass
    return result


def _bootstrap_session_workspace(cwd: str | None) -> str | None:
    if not cwd:
        return None
    low = cwd.replace("/", "\\").casefold()
    if "tiny3d" in low: return "Tiny3D"
    if "lowvram" in low: return "LowVRAM"
    if "\\.agents" in low: return "Agents"
    if "\\vault" in low: return "Vault"
    if "unreal projects\\p3" in low or "p3-" in low or "-p3-" in low or "user-v2" in low or "v2-" in low or "-v2" in low or "meteor" in low: return "P3"
    if "chatgptmcpclean" in low or "mcp-" in low or "\\mcp" in low: return "MCP"
    return Path(cwd).name or cwd

def _bootstrap_pc_status() -> dict[str, Any]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    mem = MEMORYSTATUSEX(); mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
    physical_total = mem.ullTotalPhys / 2**30
    physical_free = mem.ullAvailPhys / 2**30
    commit_limit = mem.ullTotalPageFile / 2**30
    commit_used = (mem.ullTotalPageFile - mem.ullAvailPageFile) / 2**30
    commit_headroom = mem.ullAvailPageFile / 2**30
    commit_used_pct = (commit_used * 100 / commit_limit) if commit_limit else 0.0
    physical_free_pct = (physical_free * 100 / physical_total) if physical_total else 0.0
    if commit_headroom < 2 or commit_used_pct >= 95:
        memory_status = "COMMIT_CRITICAL"
    elif commit_headroom < 8 or commit_used_pct >= 88:
        memory_status = "COMMIT_WATCH"
    elif physical_free < 1.5:
        memory_status = "PHYSICAL_TIGHT_COMMIT_OK"
    else:
        memory_status = "OK"
    disk = shutil.disk_usage("C:\\")
    disk_free_gb = disk.free / 2**30
    disk_status = "LOW" if disk_free_gb < 25 else ("WATCH" if disk_free_gb < 100 else "OK")
    gpu = None
    try:
        proc = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"], text=True, capture_output=True, timeout=3)
        if proc.returncode == 0 and proc.stdout.strip():
            used, total, util = [float(x.strip()) for x in proc.stdout.splitlines()[0].split(",")]
            gpu = {"vram_used_mb": round(used), "vram_total_mb": round(total), "vram_free_mb": round(total-used), "utilization_pct": round(util)}
    except Exception:
        pass
    return {
        "memory": {
            "physical_total_gb": round(physical_total,1), "physical_free_gb": round(physical_free,1), "physical_free_pct": round(physical_free_pct,1),
            "commit_used_gb": round(commit_used,1), "commit_limit_gb": round(commit_limit,1), "commit_headroom_gb": round(commit_headroom,1), "commit_used_pct": round(commit_used_pct,1),
            "status": memory_status,
            "interpretation": "physical free RAM alone is not commit exhaustion; judge memory pressure from commit used/limit/headroom together",
        },
        "disk": {"drive": "C:", "total_gb": round(disk.total/2**30,1), "used_gb": round(disk.used/2**30,1), "free_gb": round(disk_free_gb,1), "used_pct": round(disk.used*100/disk.total,1), "status": disk_status, "reserve_25gb_ok": disk_free_gb >= 25, "trend": _bootstrap_disk_trend(disk_free_gb)},
        "gpu": gpu,
    }


def _bootstrap_worker_status() -> dict[str, Any]:
    history_root = ROOT / "worker-reports" / "history"
    if not history_root.exists():
        return {"available": False, "path": str(history_root)}
    try:
        from tools.worker_report_history import load_history_metadata
    except ImportError:
        from worker_report_history import load_history_metadata
    now = datetime.now(timezone.utc)
    records = load_history_metadata(history_root)
    latest_by_worker: dict[str, dict[str, Any]] = {}
    for item in records:
        worker_id = str(item.get("automation_id") or "").strip()
        if not worker_id:
            continue
        raw_finished = str(item.get("finished_at") or item.get("archived_at") or "")
        try:
            finished = datetime.fromisoformat(raw_finished.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            continue
        prev = latest_by_worker.get(worker_id)
        if prev is not None and finished <= prev["_finished_dt"]:
            continue
        duration = item.get("duration_minutes")
        target = item.get("target_run_minutes")
        if not isinstance(target, (int, float)) or target <= 0:
            target = 24.0
        utilization = item.get("target_utilization_pct")
        if not isinstance(utilization, (int, float)) and isinstance(duration, (int, float)):
            utilization = round(float(duration) * 100 / float(target), 1)
        util = float(utilization) if isinstance(utilization, (int, float)) else None
        if util is None:
            classification = "UNKNOWN"
        elif util < 25:
            classification = "SEVERELY_PREMATURE"
        elif util < 60:
            classification = "PREMATURE"
        elif util < 80:
            classification = "SHORT"
        else:
            classification = "ON_TARGET"
        age_minutes = max(0.0, (now - finished).total_seconds() / 60)
        latest_by_worker[worker_id] = {
            "_finished_dt": finished,
            "automation_id": worker_id,
            "display_label": item.get("display_label") or item.get("worker"),
            "finished_at": raw_finished,
            "age_minutes": round(age_minutes,1),
            "duration_minutes": round(float(duration),2) if isinstance(duration,(int,float)) else None,
            "target_minutes": round(float(target),2),
            "target_utilization_pct": round(util,1) if util is not None else None,
            "classification": classification,
        }
    latest = sorted(latest_by_worker.values(), key=lambda x: x["_finished_dt"], reverse=True)[:5]
    for item in latest:
        item.pop("_finished_dt", None)
    util_values = [x["target_utilization_pct"] for x in latest if isinstance(x.get("target_utilization_pct"),(int,float))]
    duration_values = [x["duration_minutes"] for x in latest if isinstance(x.get("duration_minutes"),(int,float))]
    attention = [
        {"worker": x.get("display_label"), "duration_minutes": x.get("duration_minutes"), "target_minutes": x.get("target_minutes"), "utilization_pct": x.get("target_utilization_pct"), "classification": x.get("classification"), "age_minutes": x.get("age_minutes")}
        for x in latest if x.get("classification") in {"SHORT","PREMATURE","SEVERELY_PREMATURE"}
    ]
    return {
        "available": True,
        "generated_at": now.isoformat(),
        "target_run_minutes": 24.0,
        "latest_per_worker": latest,
        "fleet": {
            "workers_seen": len(latest),
            "average_latest_duration_minutes": round(sum(duration_values)/len(duration_values),2) if duration_values else None,
            "average_latest_utilization_pct": round(sum(util_values)/len(util_values),1) if util_values else None,
            "on_target_count": sum(1 for x in latest if x.get("classification") == "ON_TARGET"),
            "short_or_worse_count": len(attention),
        },
        "attention": attention,
        "classification": {"ON_TARGET": ">=80%", "SHORT": "60-79%", "PREMATURE": "25-59%", "SEVERELY_PREMATURE": "<25%"},
    }


def _bootstrap_mcp_status() -> dict[str, Any]:
    from collections import deque
    root = Path(os.path.expandvars(r"%LOCALAPPDATA%\ChatGPTMcpClean\minimal-connectors"))
    logs = sorted(root.glob("clone-*/transport.jsonl"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    if not logs:
        return {"available": False, "status": "MISSING", "active_sessions": [], "active_session_count": 0}
    source = logs[0]
    rows = []
    try:
        with source.open("r", encoding="utf-8-sig") as handle:
            for raw in deque(handle, maxlen=400):
                try:
                    rows.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
    except OSError as exc:
        return {"available": False, "status": "ERROR", "active_sessions": [], "active_session_count": 0, "error": str(exc)}

    callers: dict[str, dict[str, Any]] = {}
    counts = {"starts": 0, "reads": 0, "exits": 0, "kills": 0, "nonzero_exits": 0}
    last_kill = None
    last_event_at = None
    for row in rows:
        event = row.get("event")
        at = row.get("at")
        if at and (last_event_at is None or at > last_event_at):
            last_event_at = at
        if event == "process_started": counts["starts"] += 1
        elif event == "process_read": counts["reads"] += 1
        elif event == "process_exit_observed":
            counts["exits"] += 1
            if row.get("exit_code") not in (None, 0): counts["nonzero_exits"] += 1
        elif event == "process_killed":
            counts["kills"] += 1
            last_kill = {k: row.get(k) for k in ("at", "caller_id", "owner_caller_id", "pid") if row.get(k) is not None}
        caller = row.get("caller_id") or row.get("owner_caller_id")
        if not caller:
            continue
        item = callers.setdefault(caller, {"caller_id": caller, "last_at": None, "process_starts": 0, "reads": 0, "cwds": []})
        if at and (item["last_at"] is None or at > item["last_at"]): item["last_at"] = at
        if event == "process_started":
            item["process_starts"] += 1
            cwd = row.get("cwd")
            if cwd and cwd not in item["cwds"]: item["cwds"].append(cwd)
        elif event == "process_read":
            item["reads"] += 1

    caller_list = [x for x in sorted(callers.values(), key=lambda x: x.get("last_at") or "", reverse=True) if x.get("process_starts") or x.get("reads")][:8]
    recent_ids = {item["caller_id"] for item in caller_list}
    busy_titles: dict[str, list[str]] = {cid: [] for cid in recent_ids}
    try:
        busy = Path(os.path.expandvars(r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd"))
        proc = subprocess.run([str(busy), "list"], text=True, capture_output=True, timeout=2)
        claims = json.loads(proc.stdout).get("claims", []) if proc.returncode == 0 and proc.stdout.strip() else []
        active = {str(c.get("actor") or ""): c for c in claims if c.get("actor")}
        remaining = set(active)
        receipts = root / "shared-process-receipts"
        for rp in sorted(receipts.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:120]:
            if not remaining:
                break
            try:
                receipt = json.loads(rp.read_text(encoding="utf-8-sig"))
            except Exception:
                continue
            caller = receipt.get("caller_id")
            if caller not in recent_ids:
                continue
            command = str(receipt.get("command") or "")
            for actor in list(remaining):
                if (f"claim '{actor}'" in command) or (f'claim "{actor}"' in command) or (f"claim {actor} " in command):
                    busy_titles[caller].append(actor)
                    remaining.discard(actor)
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    active_sessions = []
    for item in caller_list:
        cwds = item.pop("cwds", [])
        item["cwd"] = cwds[-1] if cwds else None
        item["workspace"] = _bootstrap_session_workspace(item["cwd"])
        item["busy_titles"] = busy_titles.get(item["caller_id"], [])
        try:
            last_dt = datetime.fromisoformat(str(item.get("last_at") or "").replace("Z", "+00:00")).astimezone(timezone.utc)
            item["activity_age_seconds"] = round(max(0.0, (now - last_dt).total_seconds()), 1)
        except ValueError:
            item["activity_age_seconds"] = None
        if item["activity_age_seconds"] is not None and item["activity_age_seconds"] <= 300:
            active_sessions.append(item)
    source_age = max(0.0, (now - datetime.fromtimestamp(source.stat().st_mtime, timezone.utc)).total_seconds())
    return {
        "available": True,
        "status": "LIVE" if source_age <= 60 else "STALE",
        "source_age_seconds": round(source_age,1),
        "active_session_count": len(active_sessions),
        "active_sessions": active_sessions,
        "activity_summary": {**counts, "sample_rows": len(rows), "last_event_at": last_event_at, "last_kill": last_kill},
    }


def _bootstrap_memory_titles() -> list[dict[str, Any]]:
    try:
        from tools.memory_bank import load_bank, recent_title_entries
    except ImportError:
        from memory_bank import load_bank, recent_title_entries
    return [{k: item.get(k) for k in ("id", "timestamp", "title")} for item in recent_title_entries(load_bank(), limit=20)]


def build_live_bootstrap_glance() -> dict[str, Any]:
    """Single compact factual session bootstrap."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        f_pc = pool.submit(_bootstrap_pc_status)
        f_workers = pool.submit(_bootstrap_worker_status)
        f_mcp = pool.submit(_bootstrap_mcp_status)
        f_memories = pool.submit(_bootstrap_memory_titles)
        pc, workers, mcp, memories = f_pc.result(), f_workers.result(), f_mcp.result(), f_memories.result()
    notable_conditions: list[str] = []
    disk = pc.get("disk", {})
    if disk.get("status") != "OK":
        notable_conditions.append(f"disk_{str(disk.get('status')).casefold()}_free_{disk.get('free_gb')}gb")
    trend = disk.get("trend", {}) if isinstance(disk, dict) else {}
    approx_24h = trend.get("approx_24h") if isinstance(trend, dict) else None
    previous = trend.get("previous") if isinstance(trend, dict) else None
    if isinstance(approx_24h, dict) and float(approx_24h.get("lost_gb") or 0) >= 5:
        notable_conditions.append(f"disk_lost_{approx_24h.get('lost_gb')}gb_over_{approx_24h.get('age_hours')}h")
    elif isinstance(previous, dict) and float(previous.get("lost_gb") or 0) >= 5:
        notable_conditions.append(f"disk_lost_{previous.get('lost_gb')}gb_over_{previous.get('age_hours')}h")
    memory_status = pc.get("memory", {}).get("status")
    if memory_status and memory_status != "OK":
        notable_conditions.append(f"memory_{str(memory_status).casefold()}_commit_headroom_{pc.get('memory', {}).get('commit_headroom_gb')}gb")
    for item in workers.get("attention", []) if isinstance(workers, dict) else []:
        notable_conditions.append(f"worker_{item.get('worker')}_{str(item.get('classification')).casefold()}_{item.get('duration_minutes')}m_of_{item.get('target_minutes')}m")
    return {
        "schema": "bootstrap.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paths": {
            "bootstrap": str(ROOT / "tools" / "stack_atlas.py"),
            "rules": r"C:\Users\Lauri\.agents\RULES.md",
            "agents": r"C:\Users\Lauri\.agents\AGENTS.md",
            "vault": str(ROOT),
            "worker_reports": str(ROOT / "worker-reports"),
            "p3": r"C:\Users\Lauri\Documents\Unreal Projects\p3",
            "tiny3d": r"C:\Users\Lauri\Desktop\tiny3d",
            "lowvram": r"C:\Users\Lauri\Desktop\lowvram3d-repo",
            "tiny3d_library": r"C:\Users\Lauri\Desktop\Tiny3D_LIBRARY",
            "mcp": r"%LOCALAPPDATA%\ChatGPTMcpClean",
        },
        "behavior": [
            "current user instruction is first authority",
            "use live repo/runtime/tool evidence for current truth",
            "for any stack/infra work, consult Atlas first to resolve owner/entrypoint/dependents/resources before mutation; then leave Atlas and use the live owner; ordinary P3/Tiny3D/LowVRAM product work bypasses Atlas",
            "Vault/memory is history/evidence; use targeted retrieval when past work matters",
            "worker reports/schedules are evidence, not liveness; use live MCP activity for liveness sanity",
            "BusyCoordinator is exact-scope collision control only: claim shared mutation scope immediately before risky mutation, but a claim never authorizes the change or proves it safe",
            "read shared RULES.md and AGENTS.md before mutation",
            "do not rebuild deleted/parallel systems before checking existing owners/history",
            "disk cleanup is fail-closed: generated product assets/proofs/lineage, user files, browser caches, dirty/unique work and foreign warm state are protected; old/process-free/output-looking is never enough to delete",
            "batch obvious reads; avoid repeated polling, rediscovery, and serial micro-probes",
        ],
        "commands": {
            "bootstrap": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance",
            "stack_owner": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup <id-or-alias>",
            "stack_find": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py find <query>",
            "process_blast_radius": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py blast-radius --pid <pid>",
            "memory_context": r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py context <query>",
            "memory_timeline": r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py timeline <query>",
            "mcp_hour": r"python C:\Users\Lauri\Desktop\vault\tools\connector_reliability.py --last-hours 1",
        },
        "pc": pc,
        "workers": workers,
        "mcp": mcp,
        "notable_conditions": notable_conditions,
        "recent_memory_titles": memories,
    }


def component_details(name: str) -> dict[str, Any]:
    requested = name
    name = COMPONENT_ALIASES.get(name.casefold(), name)
    if name in COMPONENTS:
        return {"id": name, "requested_as": requested, **COMPONENTS[name], "authority": ATLAS_CONTRACT["authority"]}
    raise KeyError(requested)


def find_features(query: str, limit: int = 5) -> list[dict[str, Any]]:
    normalized = query.strip().casefold()
    direct = COMPONENT_ALIASES.get(normalized, normalized)
    if direct in COMPONENTS:
        detail = component_details(query)
        return [{
            "id": direct,
            "owner_components": [direct],
            "entrypoints": list(detail.get("runbook") or detail.get("canonical_sources") or []),
            "boundary": "Stack component locator only; leave Atlas and inspect the live owner.",
            "authority": ATLAS_CONTRACT["authority"],
        }]
    terms = [term for term in re.split(r"[^a-z0-9]+", query.casefold()) if term]
    if not terms:
        return []
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for feature_id, spec in FEATURE_INDEX.items():
        semantic = " ".join([feature_id, *spec["owner_components"], *spec["triggers"]]).casefold()
        if not any(term in semantic for term in terms):
            continue
        detail = " ".join([*spec["entrypoints"], spec["boundary"]]).casefold()
        score = sum(3 for term in terms if term in semantic) + sum(1 for term in terms if term in detail)
        ranked.append((score, feature_id, {"id": feature_id, **spec, "authority": ATLAS_CONTRACT["authority"]}))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[: max(1, limit)]]


def _ancestry(pid: int, by_pid: dict[int, dict[str, Any]], limit: int = 16) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    seen: set[int] = set()
    current = by_pid.get(pid)
    while current and len(chain) < limit:
        current_pid = int(current.get("pid") or 0)
        if not current_pid or current_pid in seen:
            break
        seen.add(current_pid)
        chain.append(current)
        current = by_pid.get(int(current.get("ppid") or 0))
    return chain
def classify_process(process: dict[str, Any], by_pid: dict[int, dict[str, Any]]) -> dict[str, Any]:
    pid = int(process.get("pid") or 0)
    chain = _ancestry(pid, by_pid)
    ancestry_text = "\n".join(str(item.get("command_line") or "") for item in chain).casefold()
    command = str(process.get("command_line") or "").casefold()
    evidence: list[str] = []
    component: str | None = None

    if "mcpvpsedge" in ancestry_text or "vps_mcp_reverse_tunnel.py" in command:
        component = "vps_edge_ingress"
        evidence.append("McpVpsEdge reverse-tunnel process ancestry")
    elif "chatgptmcpclean" in ancestry_text and "front-door" in ancestry_text:
        component = "mcp_front_door"
        evidence.append("ChatGPTMcpClean front-door process ancestry")
    elif (
        ("chatgptmcpclean" in ancestry_text and "start-minimal-clone.ps1" in ancestry_text)
        or "launch-mcp-vps-origin.ps1" in ancestry_text
    ):
        component = "mcp_minimal_clone"
        evidence.append("serving minimal-clone launcher ancestry")
    elif "chatgptmcpclean" in ancestry_text:
        component = "mcp_backend"
        evidence.append("ChatGPTMcpClean backend/supervisor ancestry")
    elif "start-githubrunnerhidden.ps1" in ancestry_text or "actions-runner" in ancestry_text:
        component = "github_runner"
        evidence.append("GitHub runner launcher ancestry")
    elif "busycoordinator" in ancestry_text or "busy-python.cmd" in ancestry_text or "busy-rust.cmd" in ancestry_text:
        component = "busy_coordinator"
        evidence.append("BusyCoordinator command path")

    return {
        "pid": pid,
        "component": component,
        "evidence": evidence,
        "ancestry": [
            {
                "pid": int(item.get("pid") or 0),
                "ppid": int(item.get("ppid") or 0),
                "name": item.get("name"),
                "command_line": item.get("command_line"),
            }
            for item in chain
        ],
    }


def _children_map(processes: Iterable[dict[str, Any]]) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    for process in processes:
        out.setdefault(int(process.get("ppid") or 0), []).append(int(process.get("pid") or 0))
    return out
def _descendants(pid: int, children: dict[int, list[int]]) -> list[int]:
    found: list[int] = []
    stack = list(children.get(pid, []))
    seen: set[int] = set()
    while stack:
        child = stack.pop()
        if child in seen:
            continue
        seen.add(child)
        found.append(child)
        stack.extend(children.get(child, []))
    return found


def _destructive_verdict(component: str | None) -> tuple[str, str]:
    if component is None:
        return "BLOCK_UNKNOWN_TOPOLOGY", "resolve stable component identity and recovery before disruption"
    if component == "busy_coordinator":
        return "BLOCK_COORDINATION_AUTHORITY", "use BusyCoordinator contract/recovery; do not kill around its state store"
    if component == "vps_edge_ingress":
        return "BLOCK_ACTIVE_TRANSPORT", "generic process disruption is blocked; deliberate MCP restart/cutover follows the canonical MCP context owner"
    if component == "mcp_front_door":
        return "BLOCK_ACTIVE_TRANSPORT", "update an inactive backend and switch only after exact compatibility proof"
    if component in {"mcp_backend", "mcp_minimal_clone"}:
        return "RUNBOOK_REQUIRED_INACTIVE_GENERATION_ONLY", "prove target is inactive/replaceable and preserve last good generation"
    return "RUNBOOK_REQUIRED", "follow the component runbook and prove blast radius/recovery first"
def blast_radius(
    pid: int,
    processes: list[dict[str, Any]],
    *,
    ports: list[dict[str, Any]] | None = None,
    resource_observations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    by_pid = {int(item.get("pid") or 0): item for item in processes if int(item.get("pid") or 0)}
    target = by_pid.get(pid)
    if target is None:
        return {"pid": pid, "status": "NOT_FOUND", "destructive_verdict": "BLOCK_UNKNOWN_TOPOLOGY"}
    identity = classify_process(target, by_pid)
    component = identity["component"]
    details = component_details(component) if component else None
    children = _children_map(processes)
    descendant_ids = _descendants(pid, children)
    descendant_components = sorted({
        classified["component"]
        for child in descendant_ids
        if (classified := classify_process(by_pid[child], by_pid))["component"]
    })
    owned_ports = [item for item in (ports or []) if int(item.get("pid") or 0) == pid]
    resources = [item for item in (resource_observations or []) if int(item.get("pid") or 0) == pid]
    affected = {
        "mcp": bool(component and component.startswith("mcp_")) or any(str(item).startswith("mcp_") for item in descendant_components),
        "worker_execution": bool(details and "execution_workers" in details.get("dependents", [])),
        "busy_coordinator_access": component == "busy_coordinator" or any(
            "busy-claims.json" in str(item.get("path") or "").casefold() for item in resources
        ),
        "other_control_paths": sorted(set((details or {}).get("dependents", []))),
    }
    verdict, required_next = _destructive_verdict(component)
    unknowns: list[str] = []
    if component is None:
        unknowns.append("stable_component_identity")
    if details:
        for field in ("supervisor", "self_heal", "independent_recovery", "dependents"):
            if not details.get(field):
                unknowns.append(field)
    if unknowns:
        verdict = "BLOCK_UNKNOWN_TOPOLOGY"
        required_next = "resolve: " + ", ".join(unknowns)
    return {
        "pid": pid,
        "status": "RESOLVED" if component else "UNRESOLVED",
        "identity": identity,
        "component": details,
        "descendant_components": descendant_components,
        "ports": owned_ports,
        "resource_observations": resources,
        "affected": affected,
        "unknowns": unknowns,
        "destructive_verdict": verdict,
        "required_next": required_next,
        "authority": ATLAS_CONTRACT["authority"],
    }
LIVE_PROBE_TIMEOUT_SECONDS = 5


def _powershell_json(script: str) -> Any:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=LIVE_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Stack Atlas live probe timed out after {LIVE_PROBE_TIMEOUT_SECONDS}s"
        ) from exc
    text = result.stdout.strip()
    return json.loads(text) if text else []


def capture_windows_processes() -> list[dict[str, Any]]:
    raw = _powershell_json(
        "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Depth 3"
    )
    rows = raw if isinstance(raw, list) else [raw]
    return [
        {
            "pid": int(item.get("ProcessId") or 0),
            "ppid": int(item.get("ParentProcessId") or 0),
            "name": item.get("Name"),
            "executable": item.get("ExecutablePath"),
            "command_line": item.get("CommandLine"),
        }
        for item in rows if item
    ]
def capture_windows_ports() -> list[dict[str, Any]]:
    raw = _powershell_json(
        "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Select-Object OwningProcess,LocalAddress,LocalPort | ConvertTo-Json -Depth 3"
    )
    rows = raw if isinstance(raw, list) else [raw]
    return [
        {
            "pid": int(item.get("OwningProcess") or 0),
            "address": item.get("LocalAddress"),
            "port": int(item.get("LocalPort") or 0),
        }
        for item in rows if item
    ]


def load_snapshot(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return (
        list(data.get("processes") or []),
        list(data.get("ports") or []),
        list(data.get("resource_observations") or []),
    )


def full_inventory() -> dict[str, Any]:
    return {
        "schema": "stack-atlas.inventory.v1",
        "contract": ATLAS_CONTRACT,
        "capability_policy": validate_policy(load_policy()),
        "features": FEATURE_INDEX,
        "components": {name: component_details(name) for name in COMPONENTS},
    }
def render_library_atlas_bytes() -> bytes:
    artifact = {
        "artifact_schema_version": 1,
        "authority": "DERIVED_OPERATIONAL_VIEW_NOT_AUTHORITY",
        "library_path": ATLAS_LIBRARY_PATH,
        "source": {
            "stack_atlas_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper(),
            "capability_policy_sha256": hashlib.sha256(CAPABILITY_POLICY_PATH.read_bytes()).hexdigest().upper(),
        },
        "inventory": full_inventory(),
    }
    return (json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def atlas_publication_plan() -> dict[str, Any]:
    data = render_library_atlas_bytes()
    return {
        "status": "EXPECTED_LIBRARY_ARTIFACT",
        "library_path": ATLAS_LIBRARY_PATH,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest().upper(),
        "acceptance": "retrieve Library copy and require byte-exact match",
    }


def verify_library_atlas_copy(path: Path) -> dict[str, Any]:
    expected = render_library_atlas_bytes()
    actual = path.read_bytes()
    return {
        "status": "PROVEN" if actual == expected else "MISMATCH",
        "library_path": ATLAS_LIBRARY_PATH,
        "expected_bytes": len(expected),
        "actual_bytes": len(actual),
        "expected_sha256": hashlib.sha256(expected).hexdigest().upper(),
        "actual_sha256": hashlib.sha256(actual).hexdigest().upper(),
    }


def render_manual() -> str:
    inventory = full_inventory()
    lines = [
        "# Assistant Stack Operational Atlas",
        "",
        "> Generated derived view. Current user instruction and named live/source authorities outrank it.",
        "",
        "## Operating invariant",
        "",
        "Atlas is a fast map for stack/infra only: locate the smallest relevant stack owner, entrypoint, dependency, or blast radius, then leave Atlas and work from that live owner. Do not use Atlas to navigate ordinary P3, Tiny3D, LowVRAM, or other product-repository work. Atlas does not plan work, establish product truth, or require deep lookups before ordinary reasoning.",
        "",
        "## Capability routing",
        "",
        "| Capability | Ordered adapter roles | Fallback |",
        "| --- | --- | --- |",
    ]
    for name, spec in inventory["capability_policy"]["capabilities"].items():
        lines.append(f"| `{name}` | {' -> '.join(spec['ordered_adapter_roles'])} | `{spec['fallback_mode']}` |")
    lines.extend(["", "## Feature discovery", "", "Use `find <query>` when you know the need but not the component. Search this derived index before proposing new stack machinery.", "", "| Feature | Owner components | Entrypoints | Boundary |", "| --- | --- | --- | --- |"])
    for feature_id, spec in inventory["features"].items():
        lines.append(f"| `{feature_id}` | {', '.join(spec['owner_components'])} | {'; '.join(spec['entrypoints'])} | {spec['boundary']} |")
    lines.extend(["", "## Components", ""])
    for name, spec in inventory["components"].items():
        lines.extend([f"### `{name}`", "", f"- Role: `{spec['role']}`", f"- Capabilities: {', '.join(spec['capabilities']) or 'none'}"])
        for label, key in (("Canonical sources", "canonical_sources"), ("Live status", "live_status"), ("Independent recovery", "independent_recovery"), ("Resources", "resources"), ("Dependents", "dependents"), ("Runbook", "runbook")):
            values = "; ".join(str(item) for item in spec.get(key, []))
            lines.append(f"- {label}: {values or 'none'}")
        lines.extend([f"- Supervisor: {spec['supervisor']}", f"- Self-heal: {spec['self_heal']}", ""])
    lines.extend(["## Process identity and blast radius", "", "OS PIDs are ephemeral lookup keys only. `blast-radius --pid <pid>` resolves stable identity from executable/command line, ancestry, supervisor/config/resource evidence, then reports affected control paths and a destructive verdict.", "", "MCP/VPS process identity is derived from executable, command line, ancestry, supervisor, and resource evidence; never infer safety from a tool name alone.", ""])
    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Derived stack capability/dependency Atlas; never a runtime authority.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap-glance", help="one compact fresh-session orientation snapshot: paths, defaults, memory titles, PC/workers, live MCP")
    sub.add_parser("inventory", help="full stack inventory; deep audit only, never normal startup")
    sub.add_parser("library-plan")
    lib_render = sub.add_parser("library-render")
    lib_render.add_argument("--output", type=Path, required=True)
    lib_verify = sub.add_parser("library-verify")
    lib_verify.add_argument("copy", type=Path)
    manual = sub.add_parser("manual")
    manual.add_argument("--output", type=Path)
    find = sub.add_parser("find", help="fuzzy stack/infra navigation when exact component id is unknown")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5)
    lookup = sub.add_parser("lookup", help="resolve one exact stack component id/alias to owner, entrypoint, dependencies and live-status hints")
    lookup.add_argument("component")
    blast = sub.add_parser("blast-radius", help="show dependents/resources for a disruptive stack/infra change")
    blast.add_argument("--pid", type=int, required=True)
    blast.add_argument("--snapshot", type=Path)
    args = parser.parse_args()

    if args.command == "bootstrap-glance":
        value = build_live_bootstrap_glance()
    elif args.command == "inventory":
        value = full_inventory()
    elif args.command == "library-plan":
        value = atlas_publication_plan()
    elif args.command == "library-render":
        data = render_library_atlas_bytes()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(data)
        value = {"status": "RENDERED", "path": str(args.output), "bytes": len(data), "library_path": ATLAS_LIBRARY_PATH}
    elif args.command == "library-verify":
        value = verify_library_atlas_copy(args.copy)
    elif args.command == "manual":
        text = render_manual()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text + "\n", encoding="utf-8")
            value = {"status": "RENDERED", "path": str(args.output), "bytes": len((text + "\n").encode("utf-8"))}
        else:
            print(text)
            return 0
    elif args.command == "find":
        value = find_features(args.query, args.limit)
    elif args.command == "lookup":
        try:
            value = component_details(args.component)
        except KeyError:
            parser.error(f"unknown Atlas component: {args.component}")
    else:
        if args.snapshot:
            processes, ports, resources = load_snapshot(args.snapshot)
        else:
            processes, ports, resources = capture_windows_processes(), capture_windows_ports(), []
        value = blast_radius(args.pid, processes, ports=ports, resource_observations=resources)
    if args.command == "bootstrap-glance":
        print(json.dumps(value, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
