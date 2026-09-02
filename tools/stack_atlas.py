from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

try:
    from .capability_routing import load_policy, validate_policy
except ImportError:
    from capability_routing import load_policy, validate_policy

ROOT = Path(__file__).resolve().parents[1]
BUSY_STORE = r"%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json"
MCP_ROOT = r"%LOCALAPPDATA%\ChatGPTMcpClean"
COMMANDER_ROOT = r"%LOCALAPPDATA%\DesktopCommanderFallback"
ATLAS_LIBRARY_PATH = "/Agent Bootstrap/stack-atlas.json"
CAPABILITY_POLICY_PATH = ROOT / "tests" / "fixtures" / "capability-routing-policy.json"

ATLAS_CONTRACT = {
    "authority": "DERIVED_OPERATIONAL_VIEW_NOT_AUTHORITY",
    "stack_work_gate": "before stack/infra reasoning, answers, redesign, repair, or mutation, consume the compact Atlas; load the relevant deep runbook before modification",
    "pid_semantics": "PID is an ephemeral live lookup key only; stable identity comes from executable/command line/ancestry/supervisor/config/resources",
    "destructive_gate": "unknown component identity, dependency role, supervisor, self-heal, blast radius, or independent recovery means BLOCK destructive action",
    "live_status": "fetch from the named live authority at use time; Atlas never promotes cached status to current truth",
}
COMPONENTS: dict[str, dict[str, Any]] = {
    "busy_coordinator": {
        "role": "coordination_authority",
        "capabilities": ["coordination"],
        "canonical_sources": [r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd", BUSY_STORE],
        "live_status": [r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd snapshot", "inspect <scope>"],
        "supervisor": "none; CLI/service contract owns durable store semantics",
        "self_heal": "not_applicable",
        "independent_recovery": [r"%LOCALAPPDATA%\BusyCoordinator\busy-python.cmd recover"],
        "resources": [BUSY_STORE],
        "dependents": ["chatgpt_orchestrator", "execution_workers"],
        "runbook": ["AGENTS.md", "tools/busy_authority.py"],
    },
    "mcp_front_door": {
        "role": "process_transport_front_door",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": [r"%LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1", "chatgpt-mcp-clean/src/front-door.ts"],
        "live_status": [
            "front-door health plus exact tool contract/semantic call",
            "ordered static-array fallback + backend connection reuse; verify the live route before disruption",
        ],
        "supervisor": "ChatGPTMcpClean keepalive FrontDoor role",
        "self_heal": "supervisor_managed_but_not_permission_to_disrupt",
        "independent_recovery": ["inactive backend generation + atomic front-door switch"],
        "resources": ["front-door port", "active-backend.json", "process-routes.json"],
        "dependents": ["chatgpt_process_transport"],
        "runbook": ["chatgpt-mcp-clean/AGENTS.md", "chatgpt-mcp-clean/keepalive.ps1"],
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
        "runbook": ["chatgpt-mcp-clean/AGENTS.md", "chatgpt-mcp-clean/keepalive.ps1"],
    },
    "mcp_minimal_clone": {
        "role": "generation_pinned_process_transport_clone",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["chatgpt-mcp-clean/scripts/start-minimal-clone.ps1"],
        "live_status": [
            "clone health",
            "exact tool contract",
            "process receipt/control route",
            "2026-09-02 reconciliation checkpoint: clone-a fallback must contain only generations compatible with merged master process contract; verify route + generation + authenticated smoke",
        ],
        "supervisor": "instance launcher / owning generation",
        "self_heal": "generation_specific",
        "independent_recovery": [
            "sibling clone or stable front door when proven compatible",
            "preserve public clone identity/OAuth/shared receipts and never leave a stale-regression generation in ordered fallback",
        ],
        "resources": ["clone port", "oauth.json", "transport.jsonl", "shared-process-receipts", "process-control"],
        "dependents": ["chatgpt_process_transport"],
        "runbook": [
            "chatgpt-mcp-clean/AGENTS.md",
            "C:/Users/Lauri/Desktop/vault/01 Reports/2026-09-02_1458_EEST_MCP_runtime_source_reconciliation.md",
        ],
    },
    "desktop_commander_watchdog": {
        "role": "machine_transport_supervisor",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": [r"%LOCALAPPDATA%\DesktopCommanderFallback\watchdog.ps1"],
        "live_status": ["watchdog process", "device/relay connection", "semantic execution call"],
        "supervisor": "host startup / watchdog process",
        "self_heal": "owns Commander child recovery",
        "independent_recovery": ["MCP process route only when independently proven available and sufficient"],
        "resources": ["Commander fallback install", "relay session"],
        "dependents": ["desktop_commander_remote"],
        "runbook": [r"%LOCALAPPDATA%\DesktopCommanderFallback\watchdog.ps1"],
    },
    "desktop_commander_remote": {
        "role": "machine_transport_relay_client",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": [r"%LOCALAPPDATA%\DesktopCommanderFallback\app\...\desktop-commander\dist\index.js"],
        "live_status": ["device online is insufficient; require Commander semantic operation"],
        "supervisor": "desktop_commander_watchdog",
        "self_heal": "watchdog_expected_but_not_safe-to-kill-proof",
        "independent_recovery": ["must prove another machine execution route before disruption"],
        "resources": ["hosted relay/device session"],
        "dependents": ["desktop_commander_local", "chatgpt_machine_execution", "execution_workers"],
        "runbook": [r"%LOCALAPPDATA%\DesktopCommanderFallback\watchdog.ps1"],
    },
    "desktop_commander_local": {
        "role": "machine_transport_execution_child",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": [r"%LOCALAPPDATA%\DesktopCommanderFallback\app\...\desktop-commander\dist\index.js"],
        "live_status": ["Commander semantic file/process operation"],
        "supervisor": "desktop_commander_remote",
        "self_heal": "parent/watchdog_may_recreate; never assume without proof",
        "independent_recovery": ["prove another machine execution route before disruption"],
        "resources": ["machine files", "spawned process handles"],
        "dependents": ["chatgpt_machine_execution", "execution_workers"],
        "runbook": [r"%LOCALAPPDATA%\DesktopCommanderFallback\watchdog.ps1"],
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
    "vault_history": {
        "role": "context:history-notebook",
        "capabilities": ["memory_read", "memory_write"],
        "canonical_sources": [r"C:\Users\Lauri\Desktop\vault\memory", "tools/memory_bank.py"],
        "live_status": [
            "targeted Vault search/context/history/timeline/recent-titles when needed; do not recursively scan the Vault filesystem for ordinary recall",
        ],
        "supervisor": "none",
        "self_heal": "not_applicable",
        "independent_recovery": ["continue without Vault; current conversation/memory and live sources remain available"],
        "resources": ["memory-bank.jsonl", "behavior-authority-registry.json"],
        "dependents": ["chatgpt_orchestrator", "execution_workers"],
        "runbook": ["memory/README.md"],
    },
    "local_git": {
        "role": "local_source_truth",
        "capabilities": ["source_read", "repository_mutate"],
        "canonical_sources": ["per-repo filesystem/.git/worktrees"],
        "live_status": ["git status", "HEAD", "origin/main", "worktree list"],
        "supervisor": "none",
        "self_heal": "not_applicable",
        "independent_recovery": ["preserve dirty/foreign state; use isolated worktree"],
        "resources": ["working tree", ".git/worktrees"],
        "dependents": ["chatgpt_orchestrator", "execution_workers"],
        "runbook": ["repo AGENTS.md"],
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
        "dependents": ["chatgpt_orchestrator", "execution_workers"],
        "runbook": ["repo AGENTS.md"],
    },
    "dev_progress_board": {
        "role": "derived_progress_projection",
        "capabilities": ["source_read"],
        "canonical_sources": [r"C:\Users\Lauri\Desktop\DevProgressBoard"],
        "live_status": ["board process/feed age; never treat projection as authority"],
        "supervisor": "Board-Watchdog.ps1 / feed scripts",
        "self_heal": "projection-specific",
        "independent_recovery": ["read canonical repo/coordinator/runtime sources directly"],
        "resources": ["operator-live.json", "board state"],
        "dependents": ["human_orientation", "chatgpt_orientation"],
        "runbook": [r"C:\Users\Lauri\Desktop\DevProgressBoard"],
    },
}

COMPONENTS.update({
    "shared_policy": {
        "role": "authority:cross-project", "capabilities": ["source_read"],
        "canonical_sources": [r"C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md"],
        "live_status": ["read current shared policy"], "supervisor": "none", "self_heal": "not_applicable",
        "independent_recovery": ["current instruction + repo rules remain authoritative"], "resources": ["generated policy blocks"],
        "dependents": ["chatgpt_orchestrator", "execution_workers"], "runbook": [r"C:\Users\Lauri\.agents\SHARED-AGENT-POLICY.md"],
    },
    "repo_agents": {
        "role": "authority:repo-local", "capabilities": ["source_read", "repository_mutate"],
        "canonical_sources": ["admitted worktree AGENTS.md"], "live_status": ["read admitted-worktree AGENTS.md"],
        "supervisor": "repo-local", "self_heal": "not_applicable", "independent_recovery": ["block repo mutation until readable"],
        "resources": ["AGENTS.md"], "dependents": ["chatgpt_orchestrator", "execution_workers"], "runbook": ["repo AGENTS.md"],
    },
    "north_star": {
        "role": "direction:project", "capabilities": ["source_read"], "canonical_sources": ["repo NORTH_STAR/equivalent"],
        "live_status": ["read current direction doc"], "supervisor": "repo-local", "self_heal": "not_applicable",
        "independent_recovery": ["current user direction outranks stale prose"], "resources": ["NORTH_STAR/equivalent"],
        "dependents": ["chatgpt_orchestrator", "execution_workers"], "runbook": ["repo NORTH_STAR/equivalent"],
    },
    "chatgpt_memory": {
        "role": "context:chatgpt-continuity", "capabilities": ["memory_read"],
        "canonical_sources": ["current conversation", "ChatGPT Memory"],
        "live_status": ["current conversation and delivered ChatGPT Memory"], "supervisor": "ChatGPT",
        "self_heal": "product_managed", "independent_recovery": ["current conversation; targeted Vault history when useful"],
        "resources": ["ChatGPT Memory"], "dependents": ["chatgpt_orchestrator"],
        "runbook": ["04 Operating Contracts/fresh-chat-startup-orientation.md"],
    },
    "memory_bank": {
        "role": "context:bounded-history", "capabilities": ["memory_read", "memory_write"],
        "canonical_sources": ["tools/memory_bank.py", "memory/memory-bank.jsonl"], "live_status": ["memory_bank.py validate / bounded read"],
        "supervisor": "none", "self_heal": "not_applicable", "independent_recovery": ["continue without optional history enrichment"],
        "resources": ["memory-bank.jsonl", "behavior-authority-registry.json"], "dependents": ["chatgpt_orchestrator", "execution_workers"],
        "runbook": ["memory/README.md"],
    },
    "worker_reports": {
        "role": "projection:worker-self-report", "capabilities": ["source_read"],
        "canonical_sources": [r"C:\Users\Lauri\Desktop\vault\worker-reports\<WorkerName>.md"],
        "live_status": ["read the named current worker report; reconcile important progress/liveness claims with repo/runtime/CI/artifact evidence"],
        "supervisor": "none", "self_heal": "not_applicable",
        "independent_recovery": ["read canonical repo/runtime/CI/artifact evidence directly"],
        "resources": ["worker-reports/*.md"], "dependents": ["chatgpt_orchestrator"],
        "runbook": [r"C:\Users\Lauri\Desktop\vault\worker-reports"],
    },
    "chatgpt_orchestrator": {
        "role": "orchestrator:user-facing", "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["current conversation", "ChatGPT Memory", "Atlas", "current authorities"], "live_status": ["current task + relevant live-source refresh"],
        "supervisor": "current ChatGPT session", "self_heal": "session_specific", "independent_recovery": ["current conversation/ChatGPT Memory; Atlas on stack work; Vault history optional"],
        "resources": ["current task context"], "dependents": ["user"], "runbook": ["04 Operating Contracts/fresh-chat-startup-orientation.md"],
    },
    "execution_workers": {
        "role": "executor:bounded", "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["fresh-worker launch contract", "repo AGENTS.md"], "live_status": ["independent execution/activity evidence"],
        "supervisor": "ChatGPT + BusyCoordinator ownership", "self_heal": "worker_specific",
        "independent_recovery": ["preserve task/checkpoint; use another proven execution route"],
        "resources": ["claimed scope", "worktree", "execution route"], "dependents": ["chatgpt_orchestrator"],
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
        "dependents": ["chatgpt_orchestrator", "execution_workers"], "runbook": ["repo workflow files"],
    },
    "operator_live": {
        "role": "projection:near-live", "capabilities": ["source_read"],
        "canonical_sources": [r"C:\Users\Lauri\Desktop\DevProgressBoard\state\operator-live.json"],
        "live_status": ["projection timestamp/age; reconcile canonical sources"], "supervisor": "DevProgressBoard feeds",
        "self_heal": "projection_specific", "independent_recovery": ["read coordinator/Git/CI/runtime directly"],
        "resources": ["operator-live.json"], "dependents": ["chatgpt_orientation"],
        "runbook": [r"C:\Users\Lauri\Desktop\DevProgressBoard"],
    },
})

PRODUCT_ROOTS = {
    "lowvram": r"C:\Users\Lauri\Desktop\lowvram3d-repo",
    "asset_library": r"C:\Users\Lauri\Desktop\PIPELINE_RESULTS_LIBRARY",
    "tinylab": r"C:\Users\Lauri\Desktop\TinyLab",
    "tiny3d": r"C:\Users\Lauri\Desktop\tiny3d",
    "p3": r"C:\Users\Lauri\Documents\Unreal Projects\p3",
}

FEATURE_INDEX: dict[str, dict[str, Any]] = {
    "vault.history": {
        "owner_components": ["vault_history"],
        "triggers": ["vault", "history", "timeline", "chronology", "incident", "past decision", "context", "recent titles", "changes"],
        "entrypoints": ["memory_bank.py search", "memory_bank.py context", "memory_bank.py history", "memory_bank.py timeline", "memory_bank.py orient", "memory_bank.py recent-titles", "memory_bank.py changes"],
        "boundary": "History/evidence only; use targeted indexed reads, never recursive Vault scans or current-state inference.",
    },
    "project.current_truth": {
        "owner_components": ["repo_agents", "north_star", "local_git", "github"],
        "triggers": ["current truth", "project state", "repo state", "direction", "north star", "git", "github", "runtime"],
        "entrypoints": ["admitted worktree AGENTS.md", "repo NORTH_STAR/equivalent", "git status/HEAD/origin", "exact GitHub issue/PR/check/runtime evidence"],
        "boundary": "Current project truth comes from the smallest relevant live authority, not Atlas, memory, reports, or dashboards.",
    },
    "coordination.ownership": {
        "owner_components": ["busy_coordinator"],
        "triggers": ["busy", "ownership", "claim", "collision", "mutation scope", "release", "recover"],
        "entrypoints": ["busy-python.cmd inspect <actor> <scope>", "claim", "release", "recover", "snapshot"],
        "boundary": "Exact mutation collision/ownership only; never infer backlog, liveness, priority, capacity, or progress.",
    },
    "coordination.checkpoint_handoff": {
        "owner_components": ["busy_coordinator"],
        "triggers": ["checkpoint", "handoff", "resume", "pending work", "next action"],
        "entrypoints": ["busy-python.cmd inspect", "handoff", "next", "claim --checkpoint"],
        "boundary": "Reuse coordinator checkpoint/handoff state; do not create a second resume registry or queue.",
    },
    "worker.reports": {
        "owner_components": ["worker_reports"],
        "triggers": ["worker report", "worker status", "worker progress", "liveness", "cedar", "alder", "juniper"],
        "entrypoints": [r"C:\Users\Lauri\Desktop\vault\worker-reports\<WorkerName>.md"],
        "boundary": "Self-report/navigation surface; verify important liveness/progress claims against repo/runtime/CI/artifact evidence.",
    },
    "execution.transport": {
        "owner_components": ["mcp_front_door", "desktop_commander_remote"],
        "triggers": ["process execution", "shell", "file access", "mcp", "plugin2", "commander", "tool route"],
        "entrypoints": ["discover/attempt current MCP tool contract", "Desktop Commander semantic file/process operation"],
        "boundary": "Transport only; tool availability does not confer ownership, scheduling, or product authority.",
    },
    "progress.board": {
        "owner_components": ["dev_progress_board", "operator_live"],
        "triggers": ["progress board", "dashboard", "stack delivery", "operator live", "overview"],
        "entrypoints": [r"C:\Users\Lauri\Desktop\DevProgressBoard", "state/operator-live.json"],
        "boundary": "Derived orientation/projection only; reconcile important claims with canonical sources.",
    },
}

def _expand_env(value: str) -> str:
    return os.path.expandvars(value)


def build_bootstrap_atlas() -> dict[str, Any]:
    """Cheap mandatory pointer to the canonical generated Atlas."""
    validate_policy(load_policy())
    return {
        "schema": "atlas.v1",
        "must": "Stack work: load canonical inventory before reasoning/answer/change; lookup touched components for live proof; unknown blast radius blocks disruption.",
        "library": ATLAS_LIBRARY_PATH,
        "local_fallback": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py",
        "inventory": "inventory",
        "find": "find <query>",
        "lookup": "lookup <id>",
        "blast": "blast-radius --pid <pid>",
    }

def component_details(name: str) -> dict[str, Any]:
    if name in COMPONENTS:
        return {"id": name, **COMPONENTS[name], "authority": ATLAS_CONTRACT["authority"]}
    if name in PRODUCT_ROOTS:
        return {
            "id": name,
            "role": "product_or_workspace",
            "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
            "canonical_sources": [PRODUCT_ROOTS[name]],
            "live_status": ["inspect current filesystem/Git/runtime as applicable"],
            "supervisor": "project-specific",
            "self_heal": "project-specific",
            "independent_recovery": ["project-specific AGENTS/runbook"],
            "resources": [PRODUCT_ROOTS[name]],
            "dependents": [],
            "runbook": [PRODUCT_ROOTS[name]],
            "authority": ATLAS_CONTRACT["authority"],
        }
    raise KeyError(name)


def find_features(query: str, limit: int = 5) -> list[dict[str, Any]]:
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

    if "desktopcommanderfallback" in ancestry_text and "watchdog.ps1" in command:
        component = "desktop_commander_watchdog"
        evidence.append("DesktopCommanderFallback watchdog command")
    elif "desktopcommanderfallback" in ancestry_text and "desktop-commander" in command and "remote --persist-session" in command:
        component = "desktop_commander_remote"
        evidence.append("Desktop Commander remote persistent-session command")
    elif "desktopcommanderfallback" in ancestry_text and "desktop-commander" in command:
        component = "desktop_commander_local"
        evidence.append("Desktop Commander child under fallback process tree")
    elif "chatgptmcpclean" in ancestry_text and "front-door" in ancestry_text:
        component = "mcp_front_door"
        evidence.append("ChatGPTMcpClean front-door process ancestry")
    elif "chatgptmcpclean" in ancestry_text and "start-minimal-clone.ps1" in ancestry_text:
        component = "mcp_minimal_clone"
        evidence.append("ChatGPTMcpClean minimal-clone launcher ancestry")
    elif "chatgptmcpclean" in ancestry_text:
        component = "mcp_backend"
        evidence.append("ChatGPTMcpClean backend/supervisor ancestry")
    elif "start-githubrunnerhidden.ps1" in ancestry_text or "actions-runner" in ancestry_text:
        component = "github_runner"
        evidence.append("GitHub runner launcher ancestry")
    elif "devprogressboard" in ancestry_text:
        component = "dev_progress_board"
        evidence.append("DevProgressBoard process ancestry")
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
    if component.startswith("desktop_commander"):
        return "BLOCK_CONTROL_PATH_DEPENDENCY", "prove independent machine execution recovery before any disruption"
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
        "commander": bool(component and component.startswith("desktop_commander")) or any(str(item).startswith("desktop_commander") for item in descendant_components),
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
def _powershell_json(script: str) -> Any:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
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
        "components": {name: component_details(name) for name in [*COMPONENTS, *PRODUCT_ROOTS]},
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
        "For stack/infra work, consume the compact Atlas first and deep-lookup every relevant component before reasoning, answering, redesigning, repairing, or mutating. Fetch status from the named live route. If identity, dependency role, supervisor, self-heal, blast radius, or independent recovery is unknown, disruptive action is blocked.",
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
    lines.extend(["## Process identity and blast radius", "", "OS PIDs are ephemeral lookup keys only. `blast-radius --pid <pid>` resolves stable identity from executable/command line, ancestry, supervisor/config/resource evidence, then reports affected control paths and a destructive verdict.", "", "Commander and MCP are separate declared process trees. Never infer independence from tool names: observed shared-resource coupling is additional evidence and must be included in blast-radius analysis.", ""])
    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Derived stack capability/dependency Atlas; never a runtime authority.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap-glance")
    sub.add_parser("inventory")
    sub.add_parser("library-plan")
    lib_render = sub.add_parser("library-render")
    lib_render.add_argument("--output", type=Path, required=True)
    lib_verify = sub.add_parser("library-verify")
    lib_verify.add_argument("copy", type=Path)
    manual = sub.add_parser("manual")
    manual.add_argument("--output", type=Path)
    find = sub.add_parser("find")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5)
    lookup = sub.add_parser("lookup")
    lookup.add_argument("component")
    blast = sub.add_parser("blast-radius")
    blast.add_argument("--pid", type=int, required=True)
    blast.add_argument("--snapshot", type=Path)
    args = parser.parse_args()

    if args.command == "bootstrap-glance":
        value = build_bootstrap_atlas()
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
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
