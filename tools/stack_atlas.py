from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import locale
import os
import platform
import pickle
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from concurrent.futures import ThreadPoolExecutor

try:
    from tools.yard_inbox_bridge import count_pending as _yard_inbox_check
except ModuleNotFoundError:
    from yard_inbox_bridge import count_pending as _yard_inbox_check

try:
    from tools.live_swarm_search import search_live_swarm as _search_live_swarm
except ModuleNotFoundError:
    from live_swarm_search import search_live_swarm as _search_live_swarm

try:
    from tools.unified_search_sources import search_gh_buffer_cache as _search_gh_buffer_cache
except ModuleNotFoundError:
    from unified_search_sources import search_gh_buffer_cache as _search_gh_buffer_cache

try:
    from tools.recurring_slot_registry import RECURRING_WORKER_SLOTS, load_slot_snapshot
except ModuleNotFoundError:
    from recurring_slot_registry import RECURRING_WORKER_SLOTS, load_slot_snapshot

def _terminate_windows_process_tree(process: subprocess.Popen[Any], *, timeout_seconds: float = 2.0) -> None:
    """Best-effort bounded tree termination for a task-owned Windows child."""
    if process.poll() is not None:
        return
    try:
        killer = subprocess.Popen(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
        try:
            killer.wait(timeout=max(0.1, timeout_seconds))
        except subprocess.TimeoutExpired:
            killer.kill()
    except OSError:
        pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass


def _decode_process_capture(data: bytes, *, text_mode: bool, encoding: str | None, errors: str | None) -> Any:
    if not text_mode:
        return data
    return data.decode(encoding or locale.getpreferredencoding(False), errors=errors or "strict")


def _run_process(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Run hidden Windows children without pipe-EOF stalls from inherited descendant handles."""
    if os.name != "nt":
        return subprocess.run(*args, **kwargs)

    kwargs["creationflags"] = int(kwargs.get("creationflags", 0)) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if "startupinfo" not in kwargs and hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
        kwargs["startupinfo"] = startupinfo

    capture_output = bool(kwargs.get("capture_output"))
    timeout = kwargs.get("timeout")
    if not capture_output or timeout is None:
        return subprocess.run(*args, **kwargs)

    kwargs = dict(kwargs)
    kwargs.pop("capture_output", None)
    timeout = kwargs.pop("timeout", None)
    check = bool(kwargs.pop("check", False))
    input_data = kwargs.pop("input", None)
    text_mode = bool(
        kwargs.get("text")
        or kwargs.get("universal_newlines")
        or kwargs.get("encoding") is not None
        or kwargs.get("errors") is not None
    )
    encoding = kwargs.get("encoding")
    errors = kwargs.get("errors")
    command = args[0] if args else kwargs.get("args")

    stdout_path = stderr_path = None
    stdout_stream = stderr_stream = None
    try:
        stdout_stream = tempfile.NamedTemporaryFile(
            mode="w+b", prefix="stack-atlas-stdout-", suffix=".tmp", delete=False
        )
        stderr_stream = tempfile.NamedTemporaryFile(
            mode="w+b", prefix="stack-atlas-stderr-", suffix=".tmp", delete=False
        )
        stdout_path = Path(stdout_stream.name)
        stderr_path = Path(stderr_stream.name)
        process = subprocess.Popen(
            *args,
            stdout=stdout_stream,
            stderr=stderr_stream,
            stdin=subprocess.PIPE if input_data is not None else None,
            **kwargs,
        )
        timed_out = False
        try:
            process.communicate(input=input_data, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_windows_process_tree(process)

        stdout_stream.flush()
        stdout_stream.seek(0)
        stderr_stream.flush()
        stderr_stream.seek(0)
        stdout = _decode_process_capture(
            stdout_stream.read(), text_mode=text_mode, encoding=encoding, errors=errors
        )
        stderr = _decode_process_capture(
            stderr_stream.read(), text_mode=text_mode, encoding=encoding, errors=errors
        )
        if timed_out:
            raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
        completed = subprocess.CompletedProcess(command, int(process.returncode or 0), stdout, stderr)
        if check and completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode, command, output=stdout, stderr=stderr
            )
        return completed
    finally:
        for stream in (stdout_stream, stderr_stream):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        for path in (stdout_path, stderr_path):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


try:
    from live_swarm import build_live_swarm_snapshot, compact_for_bootstrap, identify_current_actor
except ModuleNotFoundError:
    from tools.live_swarm import build_live_swarm_snapshot, compact_for_bootstrap, identify_current_actor

try:
    from tools.memory_recent_projection import default_local_bank_path, read_current_projection
except ModuleNotFoundError:
    from memory_recent_projection import default_local_bank_path, read_current_projection

try:
    from tools.tiny3d_atlas_projection import project_current as project_tiny3d_current
except ModuleNotFoundError:
    from tiny3d_atlas_projection import project_current as project_tiny3d_current

ROOT = Path(os.environ.get("STACK_ATLAS_ROOT_OVERRIDE") or Path(__file__).resolve().parents[1]).resolve()
ATLAS_LIVE_ROOT = Path(r"C:\Users\Lauri\Desktop\vault")
BUSY_ROOT = Path(os.path.expandvars(r"%LOCALAPPDATA%\BusyCoordinator"))
BUSY_CONTRACT = str(BUSY_ROOT / "coordinator-contract.json")
BUSY_CMD = str(BUSY_ROOT / "busy-python.cmd")
BUSY_PY = str(BUSY_ROOT / "busy.py")
BUSY_STORE = os.path.expandvars(r"%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json")
MCP_ROOT = r"%LOCALAPPDATA%\ChatGPTMcpClean"
MCP_RUNTIME_ROOT = r"%LOCALAPPDATA%\ChatGPTMcpMinimal"
MCP_HOME_DIRECT_RUNTIME_ROOT = r"%LOCALAPPDATA%\ChatGPTMcpCandidate1100969"
MCP_CURRENT_FROZEN_ROOT = r"%LOCALAPPDATA%\ChatGPTMcpFrozen\issue281-b7b1e24"
VPS_EDGE_ROOT = r"%LOCALAPPDATA%\McpVpsEdge"
AGENT_RULES_ROOT = r"C:\Users\Lauri\.agents"
TINY3D_REPO = r"C:\Users\Lauri\Desktop\tiny3d"
TINY3D_LIBRARY = r"C:\Users\Lauri\Desktop\Tiny3D_LIBRARY"
TINY3D_LIBRARY_INDEX = TINY3D_LIBRARY + r"\.tiny3d\library\unified-asset-inventory-v1.json"
TINY3D_SHOWROOM_CATALOGUE = TINY3D_LIBRARY + r"\.tiny3d\library\showroom-v2-catalog-v1.json"
TINY3D_LIBRARY_SHOW = r"$env:PYTHONPATH='C:\Users\Lauri\Desktop\tiny3d\src'; python -m tiny3d library show <asset-id> --workspace 'C:\Users\Lauri\Desktop\Tiny3D_LIBRARY'"
TINY3D_LIBRARY_SEARCH = r"$env:PYTHONPATH='C:\Users\Lauri\Desktop\tiny3d\src'; python -m tiny3d library search <query> --workspace 'C:\Users\Lauri\Desktop\Tiny3D_LIBRARY'"
P3_VISUAL_EVIDENCE_ROOT = r"G:\Oma Drive\P3 Visual Evidence\p3"
P3_VISUAL_EVIDENCE_INDEX = P3_VISUAL_EVIDENCE_ROOT + r"\index-v1.json"
P3_VISUAL_EVIDENCE_QUERY = r"$i=Get-Content 'G:\Oma Drive\P3 Visual Evidence\p3\index-v1.json' -Raw | ConvertFrom-Json; $i.entries | Where-Object { $_.search_text -match '<query>' } | Select-Object -First 10"
MCP_CURRENT_TOPOLOGY_PATH = ROOT / "04 Operating Contracts" / "mcp-current-topology.json"
MCP_RECOVERY_STATE_PATH = ATLAS_LIVE_ROOT / "04 Operating Contracts" / "mcp-recovery-state.json"
MCP_SECURITY_ROUTING_LOG_PATH = ATLAS_LIVE_ROOT / "02 Evidence" / "mcp-security-routing-events.jsonl"
LINUX_OMEN_CONTRACT = str(ATLAS_LIVE_ROOT / "04 Operating Contracts" / "linux-omen-execution-node.md")
SWARM_ROUTING_CONTRACT = str(ATLAS_LIVE_ROOT / "04 Operating Contracts" / "swarm-routing-cohort.md")
EXECUTION_NODE_TOPOLOGY_SCHEMA = "swarm.execution-node-topology.v1"
EXECUTION_NODE_TOPOLOGY_RELATIVE_PATH = Path("04 Operating Contracts") / "execution-node-topology.json"
BOOTSTRAP_MCP_CACHE_SECONDS = 5.0
BOOTSTRAP_MCP_HEALTH_TIMEOUT_SECONDS = 0.75
BOOTSTRAP_MCP_SOURCE_FRESH_SECONDS = 60.0
BOOTSTRAP_GITHUB_CACHE_SECONDS = 60.0
BOOTSTRAP_SOURCE_FRESHNESS_CACHE_SECONDS = 60.0
BOOTSTRAP_GITHUB_FAILURE_CACHE_SECONDS = 10.0
BOOTSTRAP_GITHUB_API_TIMEOUT_SECONDS = 1.5
BOOTSTRAP_GITHUB_AUTH_FALLBACK_TIMEOUT_SECONDS = 1.0
BOOTSTRAP_GIT_COMMAND_TIMEOUT_SECONDS = 3.0
BOOTSTRAP_SOURCE_FRESHNESS_LOCAL_GIT_BUDGET_SECONDS = 6.0
MCP_ACTIVE_SESSION_COUNT_SEMANTICS = "recent_callers_with_process_start_or_read_in_activity_window_not_current_running_processes"
BOOTSTRAP_GPU_CACHE_SECONDS = 15.0
BOOTSTRAP_ACTIVE_SESSION_DETAIL_LIMIT = 3
BOOTSTRAP_MEMORY_TITLE_LIMIT = 3
BOOTSTRAP_MEMORY_CANDIDATE_LIMIT = 20
BOOTSTRAP_MEMORY_OVERVIEW_MAX_BYTES = 5_500  # structural glance guard, not detailed-memory compression
BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES = 15_000
BOOTSTRAP_GLANCE_MAX_BYTES = 25_000
BOOTSTRAP_MCP_SERVICE_HEALTH_SOURCE_LIMIT = 4
BOOTSTRAP_INTEGRITY_WARNING = (
    "BOOTSTRAP INTEGRITY: Treat this payload as complete only if its final top-level "
    "bootstrap_end.status is COMPLETE and the transport/tool evidence does not report truncation "
    "or incompleteness. If the end marker is missing, or any truncation/incompleteness is reported, "
    "immediately tell the user after reading this bootstrap before relying on it as complete context."
)
BOOTSTRAP_MEMORY_TITLE_CACHE_SECONDS = 10.0
BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT = 64
BOOTSTRAP_MANUAL_RUNNING_DETAIL_LIMIT = 4
BOOTSTRAP_MANUAL_LIVE_IDENTITY_LIMIT = 1
BOOTSTRAP_MANUAL_MALFORMED_DETAIL_LIMIT = 4
BOOTSTRAP_MANUAL_RUNNING_RECENT_MINUTES = 30.0
BOOTSTRAP_MANUAL_REPORT_READ_BYTES = 16 * 1024
RECURRING_WORKER_PARTITIONS = tuple(RECURRING_WORKER_SLOTS)
RECURRING_WORKER_SLOT_CAPACITY_TOTAL = sum(len(slots) for slots in RECURRING_WORKER_SLOTS.values())
BOOTSTRAP_RECURRING_CADENCE_GRACE_MINUTES = 70.0
BOOTSTRAP_RECURRING_RECOVERY_COOLDOWN_MINUTES = 70.0
BOOTSTRAP_RECURRING_RECOVERY_START_GRACE_MINUTES = 10.0
BOOTSTRAP_RECURRING_START_RECEIPT_GRACE_MINUTES = 2.0
AGENT_RULES_REMOTE = "organicoverlords/agents@main"
COMPONENT_ALIASES = {
    "chatgpt": "chatgpt_session",
    "webgpt": "chatgpt_session",
    "swarm": "swarm_topology",
    "swarm topology": "swarm_topology",
    "worker topology": "swarm_topology",
    "subscription topology": "swarm_topology",
    "mcp": "mcp_minimal_clone",
    "mcpv3": "vps_edge_ingress",
    "coordinator": "busy_coordinator",
    "busy": "busy_coordinator",
    "busycoordinator": "busy_coordinator",
    "busy coordinator": "busy_coordinator",
    "tailscale": "tailscale_ingress",
    "funnel": "tailscale_ingress",
    "vps": "vps_edge_ingress",
    "edge": "vps_edge_ingress",
    "vps edge": "vps_edge_ingress",
    "mcp edge": "vps_edge_ingress",
    "transfer": "file_transfer",
    "file transfer": "file_transfer",
    "linux omen": "linux_omen_node",
    "omen laptop": "linux_omen_node",
    "linux laptop": "linux_omen_node",
    "linux node": "linux_omen_node",
    "visual proof": "visual_proof",
    "proof": "visual_proof",
    "worker": "execution_workers",
    "workers": "execution_workers",
    "rules": "agent_rules",
    "agent rules": "agent_rules",
    "policy": "agent_rules",
    "orchestrator": "agent_rules",
    "operator": "agent_rules",
    "designated orchestrator": "agent_rules",
    "repo rules": "repo_rule_pointer",
    "atlas": "stack_atlas",
    "stack atlas": "stack_atlas",
    "bootstrap snapshot": "bootstrap_snapshot",
    "vault bootstrap snapshot": "bootstrap_snapshot",
    "bootstrap producer": "bootstrap_snapshot",
    "vault checkout sync": "vault_checkout_sync",
    "vaultcheckoutsync": "vault_checkout_sync",
    "serving checkout": "vault_checkout_sync",
    "worktree hygiene": "worktree_hygiene",
    "vault worktree hygiene": "worktree_hygiene",
    "vaultworktreehygiene": "worktree_hygiene",
    "worktree hygiene task": "worktree_hygiene",
    "timeline materializer": "timeline_materializer",
    "vault timeline materializer": "timeline_materializer",
    "behavior regressions": "assistant_behavior_regressions",
    "behavior regression": "assistant_behavior_regressions",
    "replay scoring": "assistant_behavior_regressions",
    "replay fixture": "assistant_behavior_regressions",
    "behavior contract": "assistant_behavior_regressions",
    "acceptance contract": "assistant_behavior_regressions",
    "slopwall replay": "assistant_behavior_regressions",
    "incident report": "assistant_behavior_regressions",
}

ATLAS_CONTRACT = {
    "authority": "DERIVED_OPERATIONAL_VIEW_NOT_AUTHORITY",
    "scope": "STACK_INFRA_MAP_ONLY; ordinary P3/Tiny3D/LowVRAM product work goes directly to each product repo",
    "stack_work_gate": "after reading canonical agent_rules, before stack/infra reasoning, answers, redesign, repair, or mutation, consume the compact Atlas; load only the relevant deep runbook before modification",
    "pid_semantics": "PID is an ephemeral live lookup key only; stable identity comes from executable/command line/ancestry/supervisor/config/resources",
    "destructive_gate": "unknown component identity, dependency role, supervisor, self-heal, blast radius, or independent recovery means BLOCK destructive action",
    "live_status": "fetch from the named live authority at use time; Atlas never promotes cached status to current truth",
}
COMPONENTS: dict[str, dict[str, Any]] = {
    "assistant_behavior_regressions": {
        "role": "assistant_behavior_regression_owner",
        "capabilities": ["source_read", "runtime_validate"],
        "canonical_sources": [
            r"C:\Users\Lauri\Desktop\vault\04 Operating Contracts\assistant-behavior-regression.md",
            r"C:\Users\Lauri\Desktop\vault\tools\replay_scoring.py",
            r"C:\Users\Lauri\Desktop\vault\tools\behavior_incident_capture.py",
            r"C:\Users\Lauri\Desktop\vault\tools\behavior_incident_close.py",
            r"C:\Users\Lauri\Desktop\vault\tools\slopwall_v2.py",
            r"C:\Users\Lauri\Desktop\vault\03 Fixtures and Experiments",
            r"C:\Users\Lauri\Desktop\vault\tools\verify.py",
        ],
        "live_status": [
            "provider-free replay scoring against tracked fixtures",
            "bounded transactional behavior-incident capture from explicit visible context",
            "resumable canonical-memory closure through memory_bank owner",
            "repository verification for fixture/scorer regression coverage",
        ],
        "supervisor": "none; repository-owned deterministic tests",
        "self_heal": "not_applicable",
        "independent_recovery": ["Git history preserves incident reports, fixtures, scorer and tests"],
        "resources": ["incident reports", "visible-context capture bundles", "replay fixtures", "behavior-contract assertions", "deterministic scorer"],
        "dependents": ["agent_rules", "memory_bank"],
        "runbook": [r"04 Operating Contracts\assistant-behavior-regression.md", r"tools\behavior_incident_capture.py", r"tools\behavior_incident_close.py", r"tools\slopwall_v2.py", r"tools\replay_scoring.py"],
    },
    "busy_coordinator": {
        "role": "coordination_authority",
        "capabilities": ["coordination"],
        "canonical_sources": [BUSY_CONTRACT, BUSY_CMD, BUSY_PY, BUSY_STORE],
        "live_status": [f"{BUSY_CMD} --help", f"{BUSY_CMD} snapshot", f"{BUSY_CMD} inspect <scope>"],
        "supervisor": "none; CLI/service contract owns durable store semantics",
        "self_heal": "not_applicable",
        "independent_recovery": [f"{BUSY_CMD} recover"],
        "resources": [BUSY_STORE],
        "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": [BUSY_CONTRACT, "AGENTS.md"],
    },
    "mcp_front_door": {
        "role": "process_transport_front_door",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": [r"%LOCALAPPDATA%\ChatGPTMcpClean\keepalive.ps1", "chatgpt-mcp-clean/src/front-door.ts"],
        "live_status": [
            "root front-door health plus exact tool contract/semantic call",
            "root / may remain on 3003 as a separate legacy/fallback surface; current production bypasses it through VPS Caddy -> WireGuard 10.203.0.2:3011, and SSH 3101-3104 are explicit recovery only, not automatic Caddy upstreams",
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
        "canonical_sources": [
            str(MCP_CURRENT_TOPOLOGY_PATH),
            MCP_CURRENT_FROZEN_ROOT + r"\start-frozen.ps1",
            r"%LOCALAPPDATA%\\Caddy\\mcp-home-test\\Caddyfile",
            MCP_ROOT + r"\config\process-tool-contract.json",
            MCP_CURRENT_FROZEN_ROOT + r"\runtime\src\index.ts",
            MCP_CURRENT_FROZEN_ROOT + r"\runtime\src\lib\file-transfer.ts",
            str(MCP_RECOVERY_STATE_PATH),
        ],
        "chatgpt_plugin_surface": {
            "profile": "process",
            "tool_count": 5,
            "tools": ["start_process", "read_output", "kill_process", "upload_local_file", "download_chatgpt_file"],
            "image_delivery": {
                "adds_tool": True,
                "upload_tool": "upload_local_file",
                "download_tool": "download_chatgpt_file",
                "widget_resource": "ui://process/file-transfer-v1.html",
                "result_carriers": ["resource_link", "structuredContent", "_meta.file_transfer"],
                "default_visual_retrieval": True,
                "default_scope": "all workers/projects when exact image pixels are not already exposed and the original supported image file is reachable through the normal machine route",
                "sequence": [
                    "resolve the exact original image path without changing proof identity",
                    "call upload_local_file with the absolute original path",
                    "consume the same-turn exact-original resource_link in chat",
                    "inspect the exposed pixels with native vision before any visual verdict",
                ],
                "fallback": "legacy CHATGPT_LIBRARY_UPLOAD is rollback-only; otherwise use the smallest faithful project-owned path only when upload_local_file cannot carry the exact media",
            },
            "excluded_actions": ["view_image", "busy_list", "busy_claim", "busy_release", "open_visual_proof", "open_visual_proof_run", "record_visual_proof_review"],
            "internal_only_profiles": ["full"],
            "boundary": "The GPT1 ChatGPT connector exposes exactly five process-profile tools: start_process, read_output, kill_process, upload_local_file, and download_chatgpt_file. For an image, upload_local_file returns a same-turn resource_link backed by the exact original file bytes; the inline thumbnail is UI-only and native vision must inspect the original resource. view_image, busy_*, and visual-proof actions remain outside this connector surface. A chat opened before promotion may retain a cached three-tool schema; verify the live backend commit/tool contract before changing MCP or OAuth.",
        },
        "live_status": [
            "current GPT1 serving identity is loaded from mcp-current-topology.v1 at lookup/inventory time; static Atlas metadata is not current-serving authority",
            "connector URL, authorization endpoint, serving path, and excluded legacy routes come from the named current-topology contract",
            "worker-visible contract is exactly five tools: start_process, read_output, kill_process, upload_local_file, download_chatgpt_file",
            "default visual retrieval for all workers/projects is upload_local_file -> exact original resource_link -> native full-resolution inspection; thumbnail is UI-only",
            "mcp-recovery-state.json selects recovery targets but is never current serving identity",
        ],
        "supervisor": "resolve current serving process/task ownership from mcp-current-topology.v1 plus live process ancestry; static Atlas labels are not liveness or ownership proof",
        "self_heal": "generation_specific",
        "independent_recovery": [
            "mcp-recovery-state.json owns selected recovery targets and rollback lanes; do not project it as current serving identity",
            "client-visible stale connector metadata does not authorize VPS/WireGuard/Tailscale repair or backend/OAuth churn",
            "authentication repair must preserve separate OAuth stores and the current five-tool serving topology from mcp-current-topology.v1",
        ],
        "resources": ["91-159-12-133.sslip.io HTTPS", "local Caddy", "current main/peer backend endpoints from mcp-current-topology.v1", "separate oauth.json stores", "transport.jsonl", "shared-process-receipts", "process-control", "exact-byte file-transfer resource handler"],
        "dependents": ["chatgpt_process_transport"],
        "runbook": [str(MCP_CURRENT_TOPOLOGY_PATH), MCP_ROOT + r"\AGENTS.md", str(MCP_RECOVERY_STATE_PATH)],
    },
    "vps_edge_ingress": {
        "role": "public_mcp_edge_and_observer",
        "capabilities": ["source_read", "runtime_validate", "artifact_transfer"],
        "canonical_sources": [VPS_EDGE_ROOT + r"\mcp-wireguard.conf", VPS_EDGE_ROOT + r"\start-tunnel.ps1", VPS_EDGE_ROOT + r"\provision_edge_extras.py", VPS_EDGE_ROOT + r"\publish-artifact.ps1", "5.61.91.127:/etc/caddy/Caddyfile"],
        "live_status": [
            "https://5-61-91-127.sslip.io/edge-status is the deployed observer snapshot; healthy is automatic-edge health and requires primary_healthy plus metadata_http=200 plus caddy=active",
            "primary_healthy is the automatic WireGuard primary only: primary_backend_http=200 plus wireguard_peer_fresh=true; SSH recovery lanes never contribute to primary_healthy or healthy",
            "WireGuard freshness fields are wireguard_interface, wireguard_handshake_age_seconds, and wireguard_peer_fresh; the deployed observer treats handshake age 0-180 seconds as fresh",
            "recovery_available and fallback_healthy_count describe explicit-recovery SSH lanes 3101-3104 only; fallback_3101_http through fallback_3104_http represent recovery availability, and Caddy does not select them automatically",
            "https://5-61-91-127.sslip.io/.well-known/oauth-protected-resource/mcp",
            "Windows WireGuardTunnel$mcp-wireguard service owns the 10.203.0.2/30 primary; Caddy automatic upstream is only 10.203.0.2:3011 over WireGuard",
            "Windows scheduled task McpVpsEdgeTunnel owns SSH fallback recovery; VPS /usr/local/bin/mcp-edge-health via mcp-edge-health.service and mcp-edge-health.timer owns one-minute observation",
        ],
        "supervisor": "Caddy/systemd on VPS plus Windows WireGuard tunnel service primary and McpVpsEdgeTunnel task for SSH fallbacks",
        "self_heal": "WireGuard service is the automatic primary path; VPS mcp-edge-health.timer observes health; native SSH 3101-3104 remain explicit recovery only; Caddy active health polling is disabled",
        "independent_recovery": [
            "local clone can be tested directly without edge; edge failure must not authorize backend/OAuth/receipt churn",
            "if WireGuard primary fails, 3101-3104 may be selected only by an explicit authorized recovery action; Caddy must not automatically reroute to them",
            "Tailscale may be used only as an explicitly revalidated non-production fallback",
        ],
        "resources": ["VPS 5.61.91.127", "public TCP 80/443", "WireGuard UDP 51820", "WireGuard 10.203.0.1/30 <-> 10.203.0.2/30", "SSH TCP 22 fallback transport", "VPS loopback 3101-3104 reverse listeners", "/usr/local/bin/mcp-edge-health", "/etc/systemd/system/mcp-edge-health.service", "/etc/systemd/system/mcp-edge-health.timer", "/srv/mcp-artifacts", "/var/lib/mcp-edge/status.json"],
        "dependents": ["mcp_minimal_clone", "file_transfer", "chatgpt_process_transport"],
        "runbook": ["01 Reports/2026-09-03_MCP_vps_edge_cutover.md"],
    },
    "tailscale_ingress": {
        "role": "secondary_network_ingress_fallback",
        "capabilities": ["source_read", "runtime_validate"],
        "canonical_sources": [r"C:\Program Files\Tailscale\tailscale.exe", MCP_ROOT + r"\keepalive.ps1"],
        "live_status": ["secondary public ingress after the 2026-09-03 VPS cutover", "MCP_PUBLIC_ORIGIN host", "tailscale funnel status --json", "stable front door 127.0.0.1:3003", "if fallback is used, require a fresh full MCP handshake before relying on it"],
        "supervisor": "Tailscale service; Funnel configuration owner is ChatGPTMcpClean keepalive.ps1",
        "self_heal": "service_specific; route edits require explicit verification",
        "independent_recovery": ["production MCPv3/VPS remains independent; the stable front door can be tested locally without Tailscale ingress"],
        "resources": ["Funnel config", "HTTPS listener", "stable front-door proxy"],
        "dependents": ["mcp_front_door"],
        "runbook": [MCP_ROOT + r"\keepalive.ps1"],
    },
    "linux_omen_node": {
        "role": "primary_lan_execution_node",
        "capabilities": ["source_read", "repository_mutate", "runtime_validate", "artifact_transfer", "build_compute"],
        "canonical_sources": [LINUX_OMEN_CONTRACT, SWARM_ROUTING_CONTRACT],
        "live_status": [
            "bounded SSH probe through the documented Windows MCP -> LAN SSH route",
            "mDNS aatuska-OMEN-by-HP-Laptop-15-dc0xxx.local must resolve to the intended host and host-key verification must pass",
            "current disk/RAM/GPU state must be re-read before heavy UE work; historical capability snapshots are not liveness proof",
            "sudo -n /usr/local/sbin/omen-agent-admin verify-storage validates /mnt/ue and /boot/efi without exposing a general root shell",
        ],
        "supervisor": "user-owned Linux Mint laptop; sshd on laptop; Windows MCP is transport only",
        "self_heal": "machine admission is owned by the shared swarm routing cohort; repository lanes supervise their own execution; do not add a second scheduler/control plane on OMEN",
        "independent_recovery": [
            "local laptop console remains independent of SSH",
            "existing Windows MCP/VPS/WireGuard serving topology is independent and must not be changed to recover this preferred execution node",
        ],
        "resources": [
            "HP OMEN by HP Laptop 15-dc0xxx",
            "Linux user aatuska",
            "mDNS aatuska-OMEN-by-HP-Laptop-15-dc0xxx.local",
            r"C:\Users\Lauri\.ssh\chatgpt-linux-aatuska-ed25519 (private key path only; never read/report contents)",
            "LAN SSH TCP 22",
            "Intel i7-8750H / 15 GiB RAM / GeForce GTX 1070 Mobile",
            "NVMe UE_FAST /dev/nvme0n1p5 ext4 UUID a6c05af1-0ede-4327-9fec-0411ac6628ee mounted at /mnt/ue",
            "/usr/local/sbin/omen-agent-admin fixed-action storage helper (status, verify-storage, mount-ue, restart-ready)",
        ],
        "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": [LINUX_OMEN_CONTRACT, SWARM_ROUTING_CONTRACT, r"python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py status --refresh-probe"],
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
        "canonical_sources": ["project-owned durable proof bundle/library", "repo-local proof/acceptance contract", "independent review receipt when one exists"],
        "live_status": ["durable original media bytes and hashes", "capture/result receipt", "independent review state", "user-visible acceptance target"],
        "supervisor": "project-specific proof workflow",
        "self_heal": "not_applicable",
        "independent_recovery": ["classify why the previous proof failed and change a load-bearing condition before another expensive retry"],
        "resources": ["durable capture/media bytes", "manifest/receipt", "review verdict", "acceptance requirement"],
        "dependents": ["project runtime", "worker_reports"],
        "runbook": [AGENT_RULES_ROOT + r"\AGENTS.md"],
        "boundary": r"Producer capture staging such as C:\P3Proofs is input, not durable proof authority. A receipt or hash without reopenable canonical media is a durability gap, not visual acceptance.",
    },
    "github_runner": {
        "role": "ci_execution_worker",
        "capabilities": ["runtime_validate", "runtime_control"],
        "canonical_sources": [
            r"C:\Users\Lauri\.agents\Manage-GitHubRunner.ps1",
            r"C:\Users\Lauri\.agents\Start-GitHubRunnerHidden.ps1",
        ],
        "live_status": [
            r"powershell -NoProfile -File C:\Users\Lauri\.agents\Manage-GitHubRunner.ps1 -RunnerRoot <runner-root> -Action Status",
            "GitHub runner registration + exact workflow run",
        ],
        "control": {
            "entrypoint": r"C:\Users\Lauri\.agents\Manage-GitHubRunner.ps1",
            "actions": ["Status", "Install", "On", "Off", "Start", "Stop", "AutostartOn", "AutostartOff", "Uninstall"],
            "autostart": "explicit logon trigger; independent from enabled/running state",
            "intent_semantics": {
                "off": "task disabled intentionally",
                "on_stopped": "task enabled but not running",
                "on_running": "task enabled and running",
                "misconfigured": "task action no longer matches the canonical launcher/root",
                "not_installed": "no task is registered",
            },
        },
        "supervisor": "Start-GitHubRunnerHidden.ps1 only after an explicit successful task start",
        "self_heal": "bounded broker/listener recovery after successful launch only; Task Scheduler restart-on-failure loops are not a recovery mechanism",
        "independent_recovery": ["other online compatible runners"],
        "resources": ["runner work directory", "explicit scheduled task state"],
        "dependents": ["github_actions"],
        "runbook": [
            r"C:\Users\Lauri\.agents\Manage-GitHubRunner.ps1",
            r"C:\Users\Lauri\.agents\Start-GitHubRunnerHidden.ps1",
        ],
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
        "role": "direction:project", "capabilities": ["source_read"], "canonical_sources": ["organicoverlords/agents@main docs/repos/<repo>/ North Star/equivalent"],
        "live_status": ["read current Agents-repo product direction; derive obvious unmet product outcomes into actionable work and prefer visible progress"], "supervisor": "organicoverlords/agents", "self_heal": "not_applicable",
        "independent_recovery": ["current user direction outranks stale prose"], "resources": ["docs/repos/<repo>/ North Star/equivalent"],
        "dependents": ["chatgpt_session", "execution_workers"], "runbook": ["organicoverlords/agents@main docs/repos/<repo>/"],
    },
    "stack_atlas": {
        "role": "derived:stack-atlas-navigation",
        "capabilities": ["source_read", "runtime_validate"],
        "canonical_sources": [
            "organicoverlords/agents@main docs/repos/regression-research/STACK_ATLAS_NORTH_STAR.md",
            r"C:\\Users\\Lauri\\Desktop\\vault\\tools\\stack_atlas.py",
            r"C:\\Users\\Lauri\\Desktop\\vault\\tools\\runtime_dependency_graph.py",
            r"C:\\Users\\Lauri\\Desktop\\vault\\docs\\assistant-stack-operational-atlas.md",
        ],
        "live_status": [
            r"python C:\\Users\\Lauri\\Desktop\\vault\\tools\\stack_atlas.py bootstrap-glance",
            r"python C:\\Users\\Lauri\\Desktop\\vault\\tools\\stack_atlas.py lookup stack_atlas",
        ],
        "supervisor": "none; derived map generated from named authorities",
        "self_heal": "not_applicable",
        "independent_recovery": [
            "read canonical agent rules, project direction, and named live/source authorities directly; Atlas unavailability is not a permission gate"
        ],
        "resources": ["Stack Atlas North Star", "derived component map", "feature index", "runtime deployment graph", "generated operational manual"],
        "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": ["organicoverlords/agents@main docs/repos/regression-research/STACK_ATLAS_NORTH_STAR.md"],
    },
    "bootstrap_snapshot": {
        "role": "runtime:persistent-bootstrap-producer",
        "capabilities": ["source_read", "runtime_validate"],
        "canonical_sources": ["tools/install_bootstrap_snapshot_task.ps1", "tools/bootstrap_read_loop.py", "tools/memory_recent_projection.py", "tools/stack_atlas.py"],
        "live_status": ["exact Windows tasks VaultBootstrapSnapshot + VaultBootstrapSnapshotWatchdog", r"%LOCALAPPDATA%\VaultBootstrapSnapshot\bootstrap_read_loop.py", r"%LOCALAPPDATA%\VaultBootstrapSnapshot\stack_atlas.py", r"C:\Users\Lauri\Desktop\vault\.state\bootstrap\latest.json"],
        "supervisor": "Windows Task Scheduler; producer owns bounded Atlas child lifecycle",
        "self_heal": "scheduled producer bundle repairs producer/helper/Atlas from cached refs/remotes/origin/main; VaultCheckoutSync owns refreshing that ref; watchdog can publish an honest degraded heartbeat",
        "independent_recovery": ["tools/install_bootstrap_snapshot_task.ps1", r"%LOCALAPPDATA%\VaultBootstrapSnapshot rollback-* copies"],
        "resources": [r"%LOCALAPPDATA%\VaultBootstrapSnapshot", "refs/remotes/origin/main", r".state\bootstrap\latest.json", r".state\bootstrap\producer-status.json", "MCP persistent process_id=bootstrap"],
        "dependents": ["stack_atlas", "chatgpt_session", "execution_workers"],
        "runbook": ["organicoverlords/regression-research#987", "organicoverlords/regression-research#1025"],
    },
    "vault_checkout_sync": {
        "role": "runtime:canonical-vault-serving-checkout-sync",
        "capabilities": ["source_read", "runtime_validate", "repository_mutate"],
        "canonical_sources": ["tools/Sync-VaultCheckout.ps1", "tools/Install-VaultCheckoutSyncTask.ps1"],
        "live_status": ["exact Windows task VaultCheckoutSync", r"C:\Users\Lauri\Desktop\vault", "cached refs/remotes/origin/main"],
        "supervisor": "Windows Task Scheduler when installed; exact sync script owns fetch/convergence semantics",
        "self_heal": "fetch refreshes cached origin/main even when worktree convergence fails closed; clean-behind can fast-forward",
        "independent_recovery": ["tools/Install-VaultCheckoutSyncTask.ps1", "tools/Sync-VaultCheckout.ps1 -Repair after attribution/authorization"],
        "resources": [r"C:\Users\Lauri\Desktop\vault", "refs/remotes/origin/main", "preserve/vault-live-*"],
        "dependents": ["bootstrap_snapshot", "stack_atlas", "chatgpt_session", "execution_workers"],
        "runbook": ["organicoverlords/regression-research#1021"],
    },
    "worktree_hygiene": {
        "role": "runtime:scheduled-worktree-hygiene-control-plane",
        "capabilities": ["source_read", "runtime_validate", "repository_mutate"],
        "canonical_sources": [
            "tools/Install-WorktreeHygieneTask.ps1",
            "tools/worktree_hygiene_task.py",
            "tools/worktree_hygiene_guard.py",
            "tools/cleanup_converger.py",
            "tools/live_swarm.py",
        ],
        "live_status": [
            "exact Windows task VaultWorktreeHygiene",
            r"%LOCALAPPDATA%\VaultWorktreeHygiene\runtime\<commit>\worktree_hygiene_task.py",
            r"%LOCALAPPDATA%\VaultWorktreeHygiene\latest.json",
        ],
        "supervisor": "Windows Task Scheduler; commit-addressed runtime bundle performs bounded fail-closed hygiene",
        "self_heal": "task reruns every minute and writes health state; runtime version changes only through the validated installer",
        "independent_recovery": [
            "tools/Install-WorktreeHygieneTask.ps1 from a clean commit contained in cached origin/main",
            r"preserve existing %LOCALAPPDATA%\VaultWorktreeHygiene\runtime\<commit> snapshots for rollback",
        ],
        "resources": [
            r"%LOCALAPPDATA%\VaultWorktreeHygiene",
            r"C:\Users\Lauri\Desktop\vault and C:\Users\Lauri\.agents worktree metadata",
            "Busy Coordinator exact repo/worktree scopes",
        ],
        "dependents": ["stack_atlas", "chatgpt_session", "execution_workers"],
        "runbook": ["organicoverlords/regression-research#900", "organicoverlords/regression-research#1047"],
    },
    "timeline_materializer": {
        "role": "runtime:materialized-history-producer",
        "capabilities": ["source_read", "runtime_validate"],
        "canonical_sources": ["tools/timeline_materializer.py", "tools/memory_bank.py", "tools/memory_git_sync.py", "tools/memory_timeline.py", "tools/repo_timeline.py", "tools/worker_report_history.py"],
        "live_status": ["exact Windows task Vault Timeline Materializer", r"%LOCALAPPDATA%\VaultTimeline\timeline-store.json", r"%LOCALAPPDATA%\VaultTimeline\timeline-query-index.pkl", r"%LOCALAPPDATA%\VaultTimeline\status.json"],
        "supervisor": "Windows Task Scheduler; commit-addressed runtime owns periodic materialization",
        "self_heal": "derived state is rebuildable from canonical/history sources",
        "independent_recovery": ["python tools\timeline_materializer.py refresh --rebuild", "validated runtime install-task path"],
        "resources": [r"%LOCALAPPDATA%\VaultTimeline", "materialized Timeline/query index"],
        "dependents": ["stack_atlas", "memory_bank", "chatgpt_session", "execution_workers"],
        "runbook": ["organicoverlords/regression-research#820"],
    },
    "chatgpt_memory": {
        "role": "context:disabled-product-memory", "capabilities": ["memory_read"],
        "canonical_sources": ["ChatGPT Memory disabled by current account configuration"],
        "live_status": ["disabled; not a continuity source and never current-state authority"], "supervisor": "ChatGPT",
        "self_heal": "product_managed", "independent_recovery": ["current conversation; targeted Vault history"],
        "resources": [], "dependents": [],
        "runbook": [],
    },
    "memory_bank": {
        "role": "context:bounded-history", "capabilities": ["memory_read", "memory_write"],
        "canonical_sources": ["tools/memory_bank.py", "memory/memory-bank.jsonl", "origin/memory/live"],
        "live_status": ["memory_bank.py validate / bounded read", "writes reconcile through dedicated origin/memory/live; protected main/master/dev/develop are forbidden publication targets"],
        "supervisor": "none", "self_heal": "not_applicable", "independent_recovery": ["continue without optional history enrichment"],
        "resources": ["memory-bank.jsonl", "memory/live"], "dependents": ["chatgpt_session", "execution_workers"],
        "runbook": ["memory/README.md"],
    },
    "worker_reports": {
        "role": "projection:worker-self-report", "capabilities": ["source_read"],
        "canonical_sources": [r"C:\Users\Lauri\Desktop\vault\worker-reports\current\<automation-id>.md", r"C:\Users\Lauri\Desktop\vault\worker-reports\history\_reports\*.json"],
        "live_status": [r"current/<automation-id>.md is a run-lifecycle start/finalization snapshot, not live progress telemetry; it may be updated at material natural checkpoints, but checkpoint cadence or staleness is not in-run liveness/progress authority. Use MCP/runtime/Git/Busy/CI/artifact evidence for in-run progress and liveness; use immutable worker-reports\history\_reports metadata only for past-run chronology; when visual_proof_run is present inspect that local run under C:\P3Proofs plus reviewed.json"],
        "supervisor": "none", "self_heal": "not_applicable",
        "independent_recovery": ["read canonical repo/runtime/CI/artifact evidence directly"],
        "resources": ["worker-reports/current/<automation-id>.md", "worker-reports/history/_reports/*.json"], "dependents": ["chatgpt_session"],
        "runbook": [r"C:\Users\Lauri\Desktop\vault\worker-reports"],
    },
    "swarm_topology": {
        "role": "contract:chatgpt-worker-swarm-topology", "capabilities": ["source_read"],
        "canonical_sources": [r"C:\Users\Lauri\Desktop\vault\04 Operating Contracts\chatgpt-swarm-topology.json", r"C:\Users\Lauri\.agents\RULES.md", r"C:\Users\Lauri\Desktop\vault\04 Operating Contracts\fresh-worker-generation-launch.md"],
        "live_status": [r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance", r"python C:\Users\Lauri\Desktop\vault\tools\recurring_slot_registry.py list"],
        "supervisor": "recurring workers own only bounded same-partition sibling re-enable; supervising/manual ChatGPT owns guarded fallback; operator handoff is administrative fallback",
        "self_heal": "bounded_same_partition_peer_reenable_with_supervising_fallback",
        "independent_recovery": [
            r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>",
            r"python C:\Users\Lauri\Desktop\vault\tools\worker_recovery_guard.py --supervising-chat-partition <S1-or-S2> --target-worker-id <target-worker-id>",
            "recurring workers may perform one exact same-partition targeted is_enabled=true only after the launch-contract fleet-watch + live-scheduler gate; supervising/manual ChatGPT or explicit operator handoff remains the guarded fallback",
        ],
        "resources": ["S1 five recurring slots + S2 five recurring slots (max 5 per partition; 10 total)", "manual/on-demand worker population"],
        "dependents": ["chatgpt_session", "execution_workers", "chatgpt_automations"],
        "runbook": [r"C:\Users\Lauri\Desktop\vault\04 Operating Contracts\chatgpt-swarm-topology.json", r"C:\Users\Lauri\Desktop\vault\04 Operating Contracts\fresh-worker-generation-launch.md", r"python C:\Users\Lauri\Desktop\vault\tools\recurring_slot_registry.py list"],
    },
    "chatgpt_session": {
        "role": "session:user-facing", "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["current conversation", "targeted Vault history", "agent_rules", "Atlas", "current authorities"], "live_status": ["current task + relevant live-source refresh"],
        "supervisor": "current ChatGPT session", "self_heal": "session_specific", "independent_recovery": ["current conversation; targeted Vault history; Atlas on stack work"],
        "resources": ["current task context"], "dependents": ["user"], "runbook": [AGENT_RULES_ROOT + r"\RULES.md"],
    },
    "execution_workers": {
        "role": "executor:bounded", "capabilities": ["source_read", "repository_mutate", "runtime_validate"],
        "canonical_sources": ["fresh-worker launch contract", "agent_rules"], "live_status": ["independent execution/activity evidence"],
        "supervisor": "recurring workers may only re-enable an exact same-partition sibling after the full recovery gate; supervising/manual ChatGPT handles guarded fallback; BusyCoordinator is exact mutation collision control only", "self_heal": "bounded_same_partition_peer_reenable_only",
        "independent_recovery": [
            r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>",
            "after an actionable same-partition fleet-watch candidate, corroborate that exact target in the live scheduler and perform at most one idempotent is_enabled=true; hand off when the gate cannot be proven",
            "preserve task/checkpoint and use another proven execution route for execution-path failures",
        ],
        "resources": ["claimed scope", "worktree", "execution route"], "dependents": ["chatgpt_session"],
        "runbook": ["04 Operating Contracts/fresh-worker-generation-launch.md"],
    },
    "chatgpt_automations": {
        "role": "scheduler:recurrence", "capabilities": ["schedule"], "canonical_sources": ["ChatGPT Automations state"],
        "live_status": ["current automation enabled/schedule state only; not worker liveness, supervision, or recovery authority"],
        "supervisor": "platform recurrence service only; it does not supervise worker health or own swarm recovery", "self_heal": "not_swarm_supervision",
        "independent_recovery": [
            "recurring workers may issue only one exact same-partition is_enabled=true after the launch-contract fleet-watch + live-scheduler gate; supervising/manual ChatGPT or explicit operator handoff may use fleet-watch plus worker_recovery_guard as fallback; scheduler listing is not the discovery path",
            "present-turn work continues without recurrence",
        ], "resources": ["timed recurrence and enabled state only"],
        "dependents": ["execution_workers"], "runbook": ["04 Operating Contracts/fresh-worker-generation-launch.md"],
    },
    "github_actions": {
        "role": "evidence:ci", "capabilities": ["runtime_validate"], "canonical_sources": ["exact GitHub Actions run"],
        "live_status": ["exact workflow run/check status"], "supervisor": "GitHub Actions", "self_heal": "external",
        "independent_recovery": ["local proof may supplement, never impersonate exact CI"], "resources": ["workflow runs", "checks"],
        "dependents": ["chatgpt_session", "execution_workers"], "runbook": ["repo workflow files"],
    },
})

SHARED_PRODUCTION_COMPONENTS = frozenset({
    "agent_rules",
    "busy_coordinator",
    "bootstrap_snapshot",
    "vault_checkout_sync",
    "worktree_hygiene",
    "github_runner",
    "vps_edge_ingress",
    "mcp_front_door",
    "mcp_minimal_clone",
})
MCP_SHARED_PRODUCTION_COMPONENTS = frozenset({
    "vps_edge_ingress",
    "mcp_front_door",
    "mcp_minimal_clone",
})


FEATURE_INDEX: dict[str, dict[str, Any]] = {
    "assistant.behavior_regressions": {
        "owner_components": ["assistant_behavior_regressions", "agent_rules", "memory_bank"],
        "triggers": [
            "behavior regression", "assistant regression", "behavior contract", "acceptance contract",
            "replay fixture", "replay scoring", "regression scoring", "correction binding",
            "slopwall replay", "incident replay", "incident report", "behavior incident capture", "incident closure", "canonical memory closure", "visible context capture", "executable behavior contract",
        ],
        "entrypoints": [
            r"C:\Users\Lauri\Desktop\vault\04 Operating Contracts\assistant-behavior-regression.md",
            r"python C:\Users\Lauri\Desktop\vault\tools\replay_scoring.py --help",
            r"python C:\Users\Lauri\Desktop\vault\tools\behavior_incident_capture.py --help",
            r"python C:\Users\Lauri\Desktop\vault\tools\behavior_incident_close.py --help",
            r"python C:\Users\Lauri\Desktop\vault\tools\slopwall_v2.py --help",
            r"C:\Users\Lauri\Desktop\vault\03 Fixtures and Experiments",
            r"python C:\Users\Lauri\Desktop\vault\tools\verify.py --all",
        ],
        "boundary": "Rules/prose state desired behavior but do not prove regression resistance. Behavior-incident capture consumes explicit agent-visible context only and transactionally materializes evidence/report/replay/pending-memory/provenance; it never retrieves whole-chat history or writes canonical memory. Closure delegates canonical memory to `memory_bank` under a deterministic event ID and resumably finalizes replay/provenance. Incident reports preserve what failed; replay fixtures encode bounded historical failure/success controls; deterministic scoring/verification tests candidate next actions. Reuse an existing behavior contract when it covers the failure. Promote a new shared behavior contract only when evidence proves a reusable uncovered invariant; do not turn every incident into another global rule or registry entry.",
    },
    "orchestration.operator": {
        "owner_components": ["agent_rules"],
        "triggers": ["orchestrator", "designated orchestrator", "operator", "operator role", "orchestration policy"],
        "entrypoints": [r"C:\Users\Lauri\.agents\RULES.md", "python tools\\stack_atlas.py lookup agent_rules"],
        "boundary": "Navigation to the designated main-chat/operator behavior owner only. The orchestrator is a role governed by canonical agent_rules, not a daemon or separate runtime/control-plane component; live project/runtime evidence and BusyCoordinator remain their own authorities.",
    },
    "production.change_gate": {
        "owner_components": ["agent_rules", "busy_coordinator", "vps_edge_ingress", "mcp_front_door"],
        "triggers": ["production mutation", "control plane mutation", "serving path", "cutover", "live routing", "shared production", "rollback", "blast radius"],
        "entrypoints": [
            "python tools\\stack_atlas.py production-change-gate <component> --actor <actor> --busy-scope <exact-scope>",
            "PASS requires --independent-rollback-verified --offpath-proof-verified plus either --routine-scoped-advance for an already-established reversible serving advance or --explicit-user-authorization for a scope-widening/destructive/topology change",
        ],
        "boundary": "Read-only preflight for shared production/control-plane mutation. A routine already-scoped reversible serving advance does not require redundant per-cutover user approval; arbitrary new, scope-widening, destructive, credential/permission, scheduler/fleet, or topology/control-plane mutation still requires explicit user authorization.",
    },
    "mcp.edge_monitoring": {
        "owner_components": ["vps_edge_ingress"],
        "triggers": ["monitoring", "edge monitoring", "edge health", "vps observer", "vps health", "wireguard health", "recovery health"],
        "entrypoints": [
            "https://5-61-91-127.sslip.io/edge-status",
            "python tools\\stack_atlas.py lookup vps_edge_ingress",
            VPS_EDGE_ROOT + r"\provision_edge_extras.py",
        ],
        "boundary": "Observer semantics only: healthy/primary_healthy describe the automatic WireGuard primary path, while SSH 3101-3104 contribute only recovery_available/fallback health. WireGuard freshness is explicit in wireguard_handshake_age_seconds and wireguard_peer_fresh. Observation never authorizes automatic SSH failover or serving-path mutation.",
    },
    "resource.disk_pressure": {
        "owner_components": ["agent_rules", "execution_nodes"],
        "triggers": ["disk cleanup", "disk full", "low disk", "free disk", "runner cache", "build cache", "runner cleanup", "disk pressure"],
        "entrypoints": [
            r"python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py status --refresh-probe",
            r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py live-swarm",
            "inspect the exact live runner/build owner before cleanup; use that repo's owned cache/reclaim entrypoint",
        ],
        "boundary": "Disk-pressure recovery is provenance-first, not name/age/size-first. Stop new heavy growth through machine admission, identify the live runner/process/work-id that created the space, then reclaim only its repo-owned regeneratable cache/output after its hot lease/process ends. Never substitute generic worktree cleanup for runner-cache recovery, never delete Content/source/evidence/user data merely to hit a free-space target, and never treat process-free/old/large alone as proof of disposability.",
    },
    "cleanup.convergence": {
        "owner_components": ["agent_rules", "local_git", "busy_coordinator"],
        "triggers": ["cleanup convergence", "worktree cleanup", "converge worktrees", "stale worktrees", "orphan residue", "reap worktrees"],
        "entrypoints": [
            r"python C:\Users\Lauri\Desktop\vault\tools\cleanup_converger.py --apply --operator-ack",
            r"C:\Users\Lauri\Desktop\vault\04 Operating Contracts\operator-cleanup-convergence.md",
        ],
        "boundary": "Operator-only bounded convergence. One invocation loops internally to a stable boundary; it may remove only clean branch-anchored inactive secondary P3/Vault worktrees, and may reclaim only Git-ignored standard Unreal Binaries/Intermediate/DerivedDataCache from inactive preserved secondary P3 lanes. Recent MCP-CWD, external process targets, and Git-locked lanes veto cache cleanup; tracked Content/Saved/proof/evidence/source are excluded. No force removal, branch deletion, fetch, reset/rebase, dirty/unanchored deletion, permission change, or process kill. Recurring workers must not use it to administer themselves or sibling lanes.",
    },
    "work.intake": {
        "owner_components": ["agent_rules", "github", "local_git", "busy_coordinator"],
        "triggers": ["issue first", "start work", "new task", "technical work", "issue", "pr", "busy claim", "before mutation", "dirty state", "wip", "handoff", "convergence"],
        "entrypoints": [
            "bounded matching issue/PR search in the owning repo",
            "continue the matching issue or create one when none exists",
            "relevant live git status/HEAD + attributed dirty state",
            f"{BUSY_CMD} inspect <exact-scope>",
            f"{BUSY_CMD} claim <actor> <exact-scope>",
            "before yielding: commit/branch/PR coherent work or record exact remaining dirty paths/checkpoint on the issue",
        ],
        "boundary": "Ordered navigation to the existing .agents issue-first contract: inspect/claim occurs immediately before shared mutation. The GitHub issue is the shared convergence record, not a queue, priority, capacity, or admission system. Busy is exact mutation collision control only. No new workflow authority is created.",
    },
    "mcp.current_topology": {
        "owner_components": ["mcp_minimal_clone"],
        "triggers": ["gpt1 mcp topology", "mcp current topology", "91-159-12-133", "mcp 3036", "mcp 3037", "mcp 3028", "mcp 3029", "mcp connector url", "mcp local edge"],
        "entrypoints": [str(MCP_CURRENT_TOPOLOGY_PATH), "python tools\\stack_atlas.py lookup mcp_minimal_clone"],
        "boundary": "mcp-current-topology.v1 is the sole named current GPT1 serving-topology authority. Atlas lookup/inventory attaches that contract at read time and fails closed when it is missing or invalid; mcp-recovery-state.json is recovery metadata, not current serving identity. Verify live Caddy/backend health separately before making a live/current claim.",
    },
    "mcp.chatgpt_plugin_surface": {
        "owner_components": ["mcp_minimal_clone"],
        "triggers": ["chatgpt plugin tools", "chatgpt plugin command", "mcp plugin tools", "process tool profile", "plugin tool contract", "image metadata", "library upload", "CHATGPT_LIBRARY_UPLOAD", "busy_list plugin", "view_image plugin", "open_visual_proof"],
        "entrypoints": ["python tools\\stack_atlas.py lookup mcp_minimal_clone", MCP_ROOT + r"\config\process-tool-contract.json", MCP_CURRENT_FROZEN_ROOT + r"\runtime\src\lib\file-transfer.ts", str(MCP_CURRENT_TOPOLOGY_PATH)],
        "boundary": "The GPT1 ChatGPT connector exposes exactly five process-profile tools: start_process, read_output, kill_process, upload_local_file, and download_chatgpt_file. upload_local_file returns a same-turn exact-original image resource for native vision while its inline thumbnail is UI-only. busy_*, view_image, and visual-proof actions remain excluded. An already-open chat may retain a cached three-tool schema; verify live backend identity before changing OAuth or routing.",
    },
    "mcp.recovery_state": {
        "owner_components": ["agent_rules", "mcp_minimal_clone", "vps_edge_ingress"],
        "triggers": ["known good", "known-good", "freeze", "refreeze", "working boundary", "recovery baseline"],
        "entrypoints": [str(MCP_RECOVERY_STATE_PATH), r"python tools\stack_atlas.py bootstrap-glance", r"C:\Users\Lauri\.agents\RULES.md"],
        "boundary": "Canonical MCP recovery state. Deployment identity, selected recovery target, and observed health/effect conditions are separate facts. Conditions use True/False/Unknown and are tied to the observed generation; never infer global health from recovery-target selection or recreate candidate/proven promotion labels.",
    },
    "mcp.regression_recovery": {
        "owner_components": ["agent_rules", "mcp_minimal_clone", "vps_edge_ingress", "busy_coordinator"],
        "triggers": ["restore working MCP", "rollback working MCP", "MCP regression after change", "restore last working", "regression recovery"],
        "entrypoints": [str(MCP_RECOVERY_STATE_PATH), str(MCP_SECURITY_ROUTING_LOG_PATH), "python tools\\\\stack_atlas.py production-change-gate mcp_minimal_clone --actor <actor> --busy-scope mcp_minimal_clone:local-home-direct-caddy --routine-scoped-advance --independent-rollback-verified --offpath-proof-verified", r"%LOCALAPPDATA%\\ChatGPTMcpFrozen\\1100969\\switch-routes.ps1"],
        "boundary": "Restore-first for severe regressions caused by our production MCP change: preserve rollback evidence and active work, then restore the canonical known-working production behavior and topology before speculative fixes. Persist platform-reroute/security event details only when the user explicitly asks for that analysis or incident tracking. A source SHA alone is insufficient when topology differs; only minimal proven replacement compatibility may be layered onto the frozen behavior. After restore, a reroute observed between successful MCP calls with no MCP request in flight is above-MCP/platform evidence and must not trigger more MCP/edge mutation without new MCP-local evidence. When restoration is already the established scoped objective, use the routine-scoped production-change gate path and do not request redundant per-cutover approval; scope-widening or destructive/topology changes still require explicit authorization.",
    },
    "mcp.security_reroute_log": {
        "owner_components": ["agent_rules", "mcp_minimal_clone", "vps_edge_ingress", "memory_bank"],
        "triggers": ["security reroute", "security routing", "security rerouting", "reroute happened", "routing happened"],
        "entrypoints": [str(MCP_SECURITY_ROUTING_LOG_PATH), str(MCP_RECOVERY_STATE_PATH), r"C:\Users\Lauri\.agents\RULES.md"],
        "boundary": "This is a mixed historical evidence log, not a single event class: preserve each record's explicit classification and never treat membership in this file as proof of a platform reroute. When the user explicitly asks for platform-reroute/security analysis or incident tracking, a user-reported reroute must be logged with report/event time semantics, preceding actions/changes, serving identifiers, and bounded live evidence before related MCP/edge mutation; otherwise treat platform security events as external and do not persist them. Tool-policy rejection, MCP/transport failure, process execution outcome, and user/preserved platform reroute evidence remain non-interchangeable. Never infer an unknown occurrence time or use server-only arrivals as a complete denominator for client-side reroutes.",
    },
    "vault.overview": {
        "owner_components": ["memory_bank"],
        "triggers": ["vault", "overview", "digest", "summary", "aggregate", "aggregation", "automatic aggregation", "useful", "usefulness", "navigation", "discover", "search vault"],
        "entrypoints": ["python tools\\memory_bank.py overview", "python tools\\memory_bank.py digest", "python tools\\stack_atlas.py find <natural-language-query>"],
        "boundary": "Default bounded Vault orientation: aggregate durable/historical memory evidence into useful themes and recent items without treating Vault as current repo/runtime/scheduler truth. Use targeted context/timeline only after the overview identifies a relevant thread.",
    },
    "vault.history": {
        "owner_components": ["memory_bank"],
        "triggers": ["history", "timeline", "chronology", "incident", "past decision", "context", "recent titles"],
        "entrypoints": ["python tools\\stack_atlas.py find <natural-language-query>", "drill-down only: python tools\\memory_bank.py context <query>", "drill-down only: python tools\\memory_bank.py timeline <query>", "exact-known-memory only: python tools\\memory_bank.py recent-titles"],
        "boundary": "Unified discovery starts with Stack Atlas find. Memory/timeline commands are second-stage historical drill-down only; never recursive Vault scans or current-state inference.",
    },
    "runtime.deployment_graph": {
        "owner_components": ["stack_atlas", "bootstrap_snapshot", "vault_checkout_sync", "worktree_hygiene", "timeline_materializer"],
        "triggers": [
            "runtime graph", "deployment graph", "dependency graph", "runtime dependency",
            "deployed script", "runtime copy", "scheduled task", "scheduler task",
            "runtime drift", "deployment drift", "what actually runs", "what runs this",
        ],
        "entrypoints": [
            "python tools\\stack_atlas.py find <natural-language-query>",
            "exact owner drill-down: python tools\\stack_atlas.py lookup <component-or-feature>",
            "node evidence: python tools\\stack_atlas.py runtime-explain <node-id-or-term>",
            "directed dependency path: python tools\\stack_atlas.py runtime-path <from> <to>",
        ],
        "boundary": "Runtime/deployment structure is an evidence class inside the one unified find surface, not a second search system. It maps bounded declared source -> deployed artifact -> exact scheduler/task entrypoint -> output/consumer relationships and labels observed drift. Edges carry provenance separately from live verification; runtime-explain/runtime-path require explicit disambiguation instead of silently selecting ambiguous nodes. No recursive scan, broad Scheduled Task enumeration, clustering, or separate runtime registry service; current liveness and mutation truth remain with the returned named owner/runtime evidence.",
    },
    "project.current_truth": {
        "owner_components": ["agent_rules", "north_star", "local_git", "github"],
        "triggers": ["current truth", "project state", "repo state", "direction", "north star", "git", "github", "runtime"],
        "entrypoints": ["shared .agents RULES.md + AGENTS.md", "organicoverlords/agents@main docs/repos/<repo>/ product direction", "git status/HEAD + relevant branch/commit history", "exact GitHub issue/PR/check/runtime evidence"],
        "boundary": "Current project truth comes from the smallest relevant live authority, not Atlas, memory, reports, or dashboards.",
    },
    "project.nexus_navigation": {
        "owner_components": ["north_star", "local_git", "github"],
        "triggers": ["nexus", "devboard", "dev progress board", "nexus canvas", "nexus board", "nexus repo"],
        "entrypoints": [
            os.path.expandvars(r"%LOCALAPPDATA%\nexus"),
            "organicoverlords/agents@main docs/repos/dev-progress-board/NORTH_STAR.md",
            "git -C %LOCALAPPDATA%\\nexus status --short --branch",
            "gh issue list -R organicoverlords/nexus",
            "gh pr list -R organicoverlords/nexus",
        ],
        "boundary": "Navigation only. Nexus product direction lives in organicoverlords/agents@main under docs/repos/dev-progress-board; current Nexus repo/worktree state, exact GitHub issue/PR state, and repo-owned runtime evidence remain implementation/runtime authority. Atlas must not infer Nexus liveness, progress, or delivery state from static paths or old board snapshots.",
    },
    "project.tiny3d_asset_library": {
        "owner_components": ["local_git", "visual_proof"],
        "triggers": [
            "tiny3d library", "tiny3d_library", "asset library", "asset catalogue", "catalogue",
            "showroom", "showroom status", "visual proof library", "visual_proof_library",
            "durable proof", "proof transport", "android proof",
        ],
        "entrypoints": [
            TINY3D_LIBRARY,
            TINY3D_LIBRARY_INDEX,
            TINY3D_SHOWROOM_CATALOGUE,
            TINY3D_LIBRARY_SEARCH,
            TINY3D_LIBRARY_SHOW,
            r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup tiny3d_library --query <asset-or-name>",
        ],
        "boundary": "Navigation only; Tiny3D repo/library data remain product authority. Use the canonical production workspace, bounded library search/show, and receipt-declared proof paths. Do not recursively scan, fetch LFS, unzip, regenerate previews, re-encode media, or hunt producer paths merely to inspect evidence. Producer/runtime PASS and independent visual review are separate states.",
        "workspace": TINY3D_LIBRARY,
        "catalogue_sources": {"unified_inventory": TINY3D_LIBRARY_INDEX, "showroom": TINY3D_SHOWROOM_CATALOGUE},
        "proof_contract": {
            "receipt": r"<asset-dir>\receipts\p3_test_result.json",
            "bundle": r"<asset-dir>\receipts\p3_proof_bundles\<result-sha256>\bundle.json",
            "media": r"<asset-dir>\receipts\p3_proof_bundles\<result-sha256>\media\<sha256>.<ext>",
            "runtime_gate": "P3_RUNTIME_PROVEN requires a valid hash-verified durable proof bundle and durable_visual_proof; path-only media references fail closed with p3_visual_proof_durable_media",
            "visual_review": "proof_bundle.independent_review_state is separate from producer/runtime PASS; NOT_RECORDED is not visual acceptance",
            "legacy_gap": r"C:\P3Proofs and other producer paths are capture staging only; missing original bytes must be surfaced as a durability gap rather than searched for recursively",
        },
        "operator_fields": ["proof.strongest_state", "proof.proof_bundle.state", "proof.latest_visual_proof.durable_path", "proof.latest_visual_proof.durable_motion_sequence_path", "proof.independent_review_state", "proof.metadata_gaps"],
    },
    "project.p3_visual_evidence": {
        "owner_components": ["visual_proof", "local_git"],
        "triggers": ["p3 visual evidence", "p3_visual_evidence", "p3 proof library", "p3_proof_library", "spell proof", "meteor proof", "lane war proof", "lanewar proof", "combat proof", "map proof"],
        "entrypoints": [P3_VISUAL_EVIDENCE_INDEX, P3_VISUAL_EVIDENCE_QUERY],
        "boundary": "Navigation only; the durable P3 root index remains the producer/operator lookup source for screenshots/videos. Query the single index, select one exact run/media identity, and preserve its original bytes/hash. If those pixels are not already exposed and the selected original image is reachable through the normal machine route, call upload_local_file on the exact original path, consume its same-turn exact-original resource_link, and inspect those full-resolution pixels with native vision. The inline thumbnail is UI-only and transport is not visual acceptance. Do not prefer base64, re-encoding, regeneration, or a thumbnail-only path when upload_local_file can carry the original bytes. Independent visual review must be reported exactly as indexed, including NOT_RECORDED and REJECTED.",
        "archive_root": P3_VISUAL_EVIDENCE_ROOT,
        "index": P3_VISUAL_EVIDENCE_INDEX,
        "query": P3_VISUAL_EVIDENCE_QUERY,
        "index_schema": "p3.visual-evidence-index.v1",
        "operator_fields": ["run_id", "date", "claim", "independent_review_state", "media.path", "media.declared_sha256", "gaps"],
    },
    "project.shared_visual_library_integration": {
        "owner_components": ["memory_bank", "visual_proof", "local_git"],
        "triggers": [
            "shared visual library", "chatgpt visual library", "visual library integration",
            "shared chat proof", "stored proof picture", "show same stored proof",
            "same picture here", "proof picture", "12-view", "12 view",
            "turnaround sheet", "multiview sheet", "standardized 12-view", "standardized 12 views", "canonical 12-view set", "review contact sheet",
        ],
        "entrypoints": [
            r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py context <current-task>",
            r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup tiny3d_library --query <asset-or-name>",
            P3_VISUAL_EVIDENCE_INDEX,
            "default chat visual route: upload_local_file(<absolute original image path>) -> exact-original resource_link -> ui://process/file-transfer-v1.html thumbnail + native full-resolution vision",
            "12-view review route: original/highest-resolution producer sheet -> one upload_local_file transfer -> native inspection of all twelve panels; if no producer sheet exists but canonical standardized per-view originals do, package those exact originals once as transient ZIP+manifest and inspect the originals after transfer; never create a reviewer-authored contact sheet merely for transport convenience",
            r"historical/non-canonical review lineage only: C:\LowVRAMProofs",
            "historical/non-canonical model-review transport only: organicoverlords/p3#1936 / PR #1244",
            "historical/non-canonical MCP Apps transport only: organicoverlords/chatgpt-mcp-clean#158 / PR #159",
        ],
        "boundary": "Cross-project navigation only; source libraries/indexes remain proof authority and this feature does not create another registry. After resolving one exact original image identity, every worker/project uses upload_local_file as the default chat-visible retrieval path when the pixels are not already exposed: send the absolute original path, consume the same-turn exact-original resource_link, and inspect the full-resolution pixels with native vision. The widget thumbnail is UI-only and transport is not acceptance. For a complete 12-view asset review, the original/highest-resolution producer 12-view sheet is one transfer/review unit: transfer that sheet once and inspect all twelve panels thoroughly in the same native-vision exposure. Do not substitute thumbnails, reduced per-view previews, a recomposed lower-resolution contact sheet, or 12 separate crop/transfer operations merely to review the asset. If no original producer sheet exists but a complete standardized 12-view set already exists as canonical individual images, those exact images remain the review source: transfer them once as the approved transient ZIP+manifest payload and inspect the manifest-declared originals after transfer. Never create a reviewer-authored contact sheet or change background, exposure, lighting, crop, scale/resolution, tone/color, or panel layout merely for review convenience. A combined/recomposed sheet is valid only when it is the owning renderer/grid builder's canonical standardized output or an explicit acceptance artifact. A per-view crop/transfer is exception-only when a panel in the original sheet is unreadable at delivered resolution or the owning acceptance contract explicitly requires a per-view derivative/artifact. Do not prefer Drive/Library, open_visual_proof/view_image, base64, custom HTTP, Git/LFS, re-encoding, C:\\LowVRAMProofs, or a second proof store merely to expose an image when upload_local_file can carry the exact original bytes. Use the smallest faithful project-owned fallback only when the explicit transfer tool cannot reach or support the exact media.",
        "related_features": {
            "task_history": "vault.history",
            "tiny3d_library": "project.tiny3d_asset_library",
            "p3_visual_evidence": "project.p3_visual_evidence",
            "chatgpt_visual_transport": "mcp.chatgpt_plugin_surface",
        },
        "shared_chat_display_state": "MCP_EXACT_ORIGINAL_UPLOAD_THEN_NATIVE_INSPECTION",
    },
    "project.p3_unreal_navigation": {
        "owner_components": ["local_git", "github"],
        "triggers": ["p3", "unreal", "unreal editor", "p3 repo", "ue mcp", "ue_mcp_bridge", "unreal mcp", "editor endpoint", "bridge endpoint"],
        "entrypoints": [
            r"C:\Users\Lauri\Documents\Unreal Projects\p3",
            r"C:\Users\Lauri\Documents\Unreal Projects\p3\scripts\v2\verification\p3_bridge_guard.py",
            r"C:\Users\Lauri\Documents\Unreal Projects\p3\scripts\Test-P3WorkerEditorPreflight.ps1",
        ],
        "boundary": "Navigation only. P3 product direction lives in organicoverlords/agents@main under docs/repos/p3; current P3 repo/main, repo-owned machine contracts, and live editor/runtime evidence remain implementation/runtime authority. Atlas must not become P3 product state. Validate UE_MCP_Bridge endpoint identity through the repo-owned live guard/preflight rather than trusting Saved/UE_MCP_Bridge/port.json alone; a configured UnrealMCPBridge port is not liveness or ownership proof.",
    },
    "coordination.ownership": {
        "owner_components": ["busy_coordinator"],
        "triggers": ["busy", "busycoordinator", "busy coordinator", "ownership", "claim", "collision", "mutation scope", "release", "recover"],
        "entrypoints": [f"{BUSY_CMD} inspect <scope>", f"{BUSY_CMD} claim", f"{BUSY_CMD} heartbeat", f"{BUSY_CMD} release", f"{BUSY_CMD} recover", f"{BUSY_CMD} snapshot"],
        "boundary": "Exact mutation collision/ownership only; never infer backlog, liveness, priority, capacity, or progress.",
    },
    "coordination.checkpoint_context": {
        "owner_components": ["busy_coordinator"],
        "triggers": ["checkpoint", "resume", "live scope context", "why is this scope claimed"],
        "entrypoints": [f"{BUSY_CMD} inspect <scope>", f"{BUSY_CMD} claim --checkpoint", f"{BUSY_CMD} heartbeat --checkpoint"],
        "boundary": "Live exact-scope ownership context only; never retained after release/recovery/expiry and never backlog, priority, handoff scheduling, liveness, or reassignment. Durable continuation belongs in the project issue/PR.",
    },
    "worker.reports": {
        "owner_components": ["worker_reports"],
        "triggers": ["worker report", "worker status", "worker progress", "worker utilization", "stop reason", "tool drop", "liveness", "cedar", "alder", "juniper"],
        "entrypoints": [r"C:\Users\Lauri\Desktop\vault\worker-reports\current\<automation-id>.md", r"C:\Users\Lauri\Desktop\vault\worker-reports\history\_reports\*.json"],
        "boundary": "Run-lifecycle self-report/navigation surface, not live progress telemetry. A current RUNNING report starts as the run-start snapshot and may be updated at material natural checkpoints; never infer in-run activity or progress from checkpoint cadence, fields, or mtime. Visual proof pointers are PENDING_REVIEW until independent reviewed.json exists; use repo/runtime/CI/artifact evidence for actual execution and liveness.",
    },
    "worker.swarm_topology": {
        "owner_components": ["swarm_topology"],
        "triggers": ["swarm topology", "five recurring workers", "max five recurring workers", "s1", "s2", "manual workers", "primary operator", "timed runs", "timed workers", "recurring workers", "worker recovery", "sibling recovery", "scheduler recovery", "who fixes workers", "who takes care of workers"],
        "entrypoints": [r"C:\Users\Lauri\Desktop\vault\04 Operating Contracts\chatgpt-swarm-topology.json", r"python C:\Users\Lauri\Desktop\vault\tools\recurring_slot_registry.py list", r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup swarm_topology", r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>", r"python C:\Users\Lauri\Desktop\vault\tools\worker_recovery_guard.py --supervising-chat-partition <S1-or-S2> --target-worker-id <target-worker-id>", r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance"],
        "boundary": "The canonical recurring topology is S1/1..S1/5 plus S2/1..S2/5: ten stable capacity slots. Worker names and ChatGPT automation IDs are mutable slot bindings, not permanent topology identities, and an unbound slot is not a liveness alarm or scheduler authority. Activity in one partition never authorizes scheduler mutation in the other. The scheduler provides recurrence only. A recurring worker may never administer itself and may only perform one targeted idempotent is_enabled=true on the exact current binding of a same-partition sibling after the bounded fleet-watch plus corroborating live-scheduler recovery gate. All other scheduler administration remains supervising/manual or explicit operator fallback. Fleet-watch local lifecycle gaps are scheduler-probe navigation only, never worker liveness or swarm-health verdicts. Current activity/liveness remains live MCP/runtime evidence.",
    },
    "execution.linux_omen_node": {
        "owner_components": ["linux_omen_node"],
        "triggers": ["linux omen", "omen laptop", "linux laptop", "linux execution node", "remote linux", "ssh linux", "ue linux", "linux build node"],
        "entrypoints": [
            "python tools\\stack_atlas.py lookup linux_omen_node",
            r"python C:\Users\Lauri\Desktop\vault\tools\swarm_route.py route --work-id <stable-task-id> --kind <work-kind>",
            LINUX_OMEN_CONTRACT,
            SWARM_ROUTING_CONTRACT,
        ],
        "boundary": "Default execution node under the shared swarm routing cohort for substantive work that is not LowVRAM or genuinely Windows-only. Windows remains MCP/control transport and takes ordinary execution only after fresh cohort evidence that OMEN is saturated/unavailable for that work class; the VPS may take supported portable-light overflow. OMEN is not an MCP endpoint, worker scheduler, repository queue, product authority, or public route; preserve user data and do not expose TCP 22 publicly.",
    },
    "execution.transport": {
        "owner_components": ["vps_edge_ingress", "mcp_minimal_clone", "mcp_front_door"],
        "triggers": ["process execution", "shell", "file access", "mcp", "mcpv3", "vps", "commander", "desktop commander", "fallback", "tool route"],
        "entrypoints": [
            "preferred MCPv3 binding when healthy and exposed",
            "Remote Desktop Commander approved standby break-glass fallback whenever preferred MCPv3 is unavailable; fallback-only/not primary, not forbidden; retry failed routes only on changed state or new evidence",
        ],
        "boundary": "Routing precedence is governed by shared RULES.md. Transport only; tool availability does not confer ownership, scheduling, or product authority. MCPv3 health does not retire, obsolete, or authorize deletion of the Commander fallback; preserve its recovery path unless current user/live authority explicitly changes that contract.",
    },
}

def _expand_env(value: str) -> str:
    return os.path.expandvars(value)


def build_bootstrap_atlas() -> dict[str, Any]:
    """Compact directory for the on-demand Atlas CLI."""
    return {
        "schema": "atlas.v1",
        "must": "Stack work: load canonical inventory before reasoning/answer/change; lookup touched components for live proof; unknown blast radius blocks disruption.",
        "entrypoint": r"python tools\stack_atlas.py",
        "inventory": "inventory",
        "find": "find <query>",
        "lookup": "lookup <id-or-alias>",
        "blast": "blast-radius --pid <pid>",
    }

BOOTSTRAP_OBSERVATION_PATH = Path(os.path.expandvars(r"%LOCALAPPDATA%\ChatGPTMcpClean\.state\bootstrap-observations.jsonl"))


def _bootstrap_disk_trend(current_free_gb: float, observation: dict[str, Any] | None = None) -> dict[str, Any]:
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
                row: dict[str, Any] = {"at": now.isoformat(), "free_gb": round(current_free_gb, 2)}
                for key, value in (observation or {}).items():
                    if key in {"at", "free_gb"} or value is None or isinstance(value, (dict, list, tuple, set)):
                        continue
                    row[str(key)] = value
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        pass
    return result


def _cwd_uses_worktree(cwd: str | os.PathLike[str] | None, worktree: str | os.PathLike[str] | None) -> bool:
    """Return True only when the session cwd is the worktree or is inside it.

    Direction matters: a broad parent cwd (for example C:\\Users\\Lauri) must
    never claim every descendant worktree.
    """
    if not cwd or not worktree:
        return False
    try:
        cwd_path = Path(os.path.abspath(os.path.expandvars(os.fspath(cwd))))
        worktree_path = Path(os.path.abspath(os.path.expandvars(os.fspath(worktree))))
        cwd_path.relative_to(worktree_path)
    except (OSError, ValueError):
        return False
    return True


def _bootstrap_execution_node_topology() -> dict[str, Any]:
    """Canonical execution-machine identity for bootstrap; routing labels are not identity."""
    path = ATLAS_LIVE_ROOT / EXECUTION_NODE_TOPOLOGY_RELATIVE_PATH
    observed_hostname = (platform.node() or os.environ.get("COMPUTERNAME") or "").strip() or None
    base = {
        "authority": "CANONICAL_EXECUTION_NODE_IDENTITY",
        "path": str(path),
        "local_observed_hostname": observed_hostname,
        "local_node_id": None,
    }
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {**base, "available": False, "status": "MISSING", "nodes": {}}
    except (OSError, json.JSONDecodeError):
        return {**base, "available": False, "status": "INVALID", "nodes": {}}
    nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if payload.get("schema") != EXECUTION_NODE_TOPOLOGY_SCHEMA or not isinstance(nodes, dict):
        return {**base, "available": False, "status": "INVALID", "nodes": {}}

    projected: dict[str, dict[str, Any]] = {}
    local_matches: list[str] = []
    for raw_node_id, raw_node in nodes.items():
        if not isinstance(raw_node_id, str) or not isinstance(raw_node, dict):
            continue
        hostnames = [str(value) for value in raw_node.get("hostnames", []) if str(value).strip()]
        projected[raw_node_id] = {
            key: raw_node.get(key)
            for key in (
                "display_name", "user_alias", "route_label", "machine_class", "os_family",
                "system_model", "gpu", "roles",
            )
            if raw_node.get(key) is not None
        }
        projected[raw_node_id]["hostnames"] = hostnames
        if observed_hostname and observed_hostname.casefold() in {value.casefold() for value in hostnames}:
            local_matches.append(raw_node_id)

    if len(local_matches) == 1:
        status = "OK"
        local_node_id = local_matches[0]
    elif len(local_matches) > 1:
        status = "LOCAL_NODE_AMBIGUOUS"
        local_node_id = None
    else:
        status = "LOCAL_NODE_UNRESOLVED"
        local_node_id = None
    return {
        **base,
        "available": True,
        "status": status,
        "schema": EXECUTION_NODE_TOPOLOGY_SCHEMA,
        "contract": payload.get("contract"),
        "local_node_id": local_node_id,
        "nodes": projected,
    }


def _bind_pc_node_identity(pc: dict[str, Any], topology: dict[str, Any]) -> dict[str, Any]:
    """Wrap local PC telemetry with its canonical physical-node identity."""
    result = dict(pc)
    node_id = topology.get("local_node_id") if isinstance(topology, dict) else None
    nodes = topology.get("nodes") if isinstance(topology, dict) and isinstance(topology.get("nodes"), dict) else {}
    node = nodes.get(node_id) if isinstance(node_id, str) and isinstance(nodes.get(node_id), dict) else {}
    topology_status = str(topology.get("status") or "UNAVAILABLE") if isinstance(topology, dict) else "UNAVAILABLE"
    identity = {
        "authority": "CANONICAL_EXECUTION_NODE_IDENTITY",
        "status": "VERIFIED_CANONICAL" if node_id and topology_status == "OK" else f"UNRESOLVED_{topology_status}",
        "node_id": node_id,
        "observed_hostname": topology.get("local_observed_hostname") if isinstance(topology, dict) else None,
    }
    for key in ("display_name", "user_alias", "route_label", "machine_class", "os_family", "system_model", "gpu"):
        if node.get(key) is not None:
            identity[key] = node.get(key)
    result["node_identity"] = identity
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
    gpu_cache, gpu_cache_age = _bootstrap_cache_read("gpu.json", BOOTSTRAP_GPU_CACHE_SECONDS)
    gpu = None
    nvml_initialized = False
    try:
        nvml = ctypes.WinDLL("nvml.dll")
        class NvmlMemory(ctypes.Structure):
            _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]
        class NvmlUtilization(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]
        nvml.nvmlInit_v2.restype = ctypes.c_int
        nvml.nvmlDeviceGetHandleByIndex_v2.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
        nvml.nvmlDeviceGetHandleByIndex_v2.restype = ctypes.c_int
        nvml.nvmlDeviceGetMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(NvmlMemory)]
        nvml.nvmlDeviceGetMemoryInfo.restype = ctypes.c_int
        nvml.nvmlDeviceGetUtilizationRates.argtypes = [ctypes.c_void_p, ctypes.POINTER(NvmlUtilization)]
        nvml.nvmlDeviceGetUtilizationRates.restype = ctypes.c_int
        if nvml.nvmlInit_v2() != 0:
            raise OSError("nvml init failed")
        nvml_initialized = True
        handle = ctypes.c_void_p()
        memory = NvmlMemory()
        utilization = NvmlUtilization()
        if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
            raise OSError("nvml device lookup failed")
        if nvml.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(memory)) != 0:
            raise OSError("nvml memory query failed")
        if nvml.nvmlDeviceGetUtilizationRates(handle, ctypes.byref(utilization)) != 0:
            raise OSError("nvml utilization query failed")
        fresh_gpu = {
            "vram_used_mb": round(memory.used / 2**20),
            "vram_total_mb": round(memory.total / 2**20),
            "vram_free_mb": round(memory.free / 2**20),
            "utilization_pct": round(utilization.gpu),
        }
        _bootstrap_cache_write("gpu.json", fresh_gpu)
        gpu = {**fresh_gpu, "sample_status": "LIVE", "sample_age_seconds": 0.0}
    except Exception:
        if gpu_cache is not None:
            gpu = {**gpu_cache, "sample_status": "CACHED_RECENT", "sample_age_seconds": round(gpu_cache_age or 0.0, 1)}
        else:
            gpu = {"available": False, "sample_status": "FAST_PROBE_UNAVAILABLE"}
    finally:
        if nvml_initialized:
            try:
                nvml.nvmlShutdown()
            except Exception:
                pass
    memory_view = {
        "physical_total_gb": round(physical_total,1), "physical_free_gb": round(physical_free,1), "physical_free_pct": round(physical_free_pct,1),
        "commit_used_gb": round(commit_used,1), "commit_limit_gb": round(commit_limit,1), "commit_headroom_gb": round(commit_headroom,1), "commit_used_pct": round(commit_used_pct,1),
        "status": memory_status,
        "interpretation": "physical free RAM alone is not commit exhaustion; judge memory pressure from commit used/limit/headroom together",
    }
    disk_view = {
        "drive": "C:", "total_gb": round(disk.total/2**30,1), "used_gb": round(disk.used/2**30,1),
        "free_gb": round(disk_free_gb,1), "used_pct": round(disk.used*100/disk.total,1),
        "status": disk_status, "reserve_25gb_ok": disk_free_gb >= 25,
    }
    observation = {
        "drive": disk_view["drive"],
        "disk_total_gb": disk_view["total_gb"],
        "disk_used_gb": disk_view["used_gb"],
        "disk_used_pct": disk_view["used_pct"],
        "disk_status": disk_view["status"],
        "physical_free_gb": memory_view["physical_free_gb"],
        "physical_free_pct": memory_view["physical_free_pct"],
        "commit_used_gb": memory_view["commit_used_gb"],
        "commit_limit_gb": memory_view["commit_limit_gb"],
        "commit_headroom_gb": memory_view["commit_headroom_gb"],
        "commit_used_pct": memory_view["commit_used_pct"],
        "memory_status": memory_view["status"],
    }
    if isinstance(gpu, dict):
        for source_key, target_key in (
            ("vram_used_mb", "vram_used_mb"), ("vram_free_mb", "vram_free_mb"),
            ("vram_total_mb", "vram_total_mb"), ("utilization_pct", "gpu_utilization_pct"),
            ("sample_status", "gpu_sample_status"),
        ):
            if gpu.get(source_key) is not None:
                observation[target_key] = gpu.get(source_key)
    disk_view["trend"] = _bootstrap_disk_trend(disk_free_gb, observation=observation)
    return {"memory": memory_view, "disk": disk_view, "gpu": gpu}



def _bootstrap_manual_current_status(now: datetime) -> dict[str, Any]:
    """Bounded purpose/freshness hints from manual current reports; never liveness authority."""
    current_root = ATLAS_LIVE_ROOT / "worker-reports" / "manual" / "current"
    semantics = "manual_current_report_state_and_purpose_only_not_process_liveness_or_scheduler_membership"
    if not current_root.exists():
        return {"available": False, "path": str(current_root), "evidence_semantics": semantics}
    try:
        from tools.worker_report_history import _fields, _parse_time
        from tools.manual_work_disposition import load_binding
    except ImportError:
        from worker_report_history import _fields, _parse_time
        from manual_work_disposition import load_binding

    try:
        report_paths = sorted(
            (path for path in current_root.glob("*.md") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError as exc:
        return {"available": False, "path": str(current_root), "evidence_semantics": semantics, "error": str(exc)}

    scan_paths = report_paths[:BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT]
    running_reports: list[dict[str, Any]] = []
    malformed_running_reports = 0
    malformed_running_sample: list[dict[str, Any]] = []

    def clipped(value: Any, limit: int) -> str:
        raw = str(value or "").strip()
        if len(raw) <= limit:
            return raw
        return raw[: max(0, limit - 3)] + "..."

    def record_malformed(report_path: Path, reason: str, fields: dict[str, str] | None = None, value: Any = None) -> None:
        nonlocal malformed_running_reports
        malformed_running_reports += 1
        if len(malformed_running_sample) >= BOOTSTRAP_MANUAL_MALFORMED_DETAIL_LIMIT:
            return
        item = {"filename": report_path.name, "reason": reason}
        run_id = str((fields or {}).get("run_id") or "").strip()
        if run_id:
            item["run_id"] = clipped(run_id, 120)
        if value is not None:
            item["value"] = clipped(value, 120)
        malformed_running_sample.append(item)

    for report_path in scan_paths:
        try:
            stat = report_path.stat()
            with report_path.open("rb") as handle:
                raw = handle.read(BOOTSTRAP_MANUAL_REPORT_READ_BYTES)
            fields = _fields(raw)
            if str(fields.get("state") or "").strip().upper() != "RUNNING":
                continue
            run_id = str(fields.get("run_id") or "").strip()
            if not run_id:
                record_malformed(report_path, "missing_run_id", fields)
                continue
            if report_path.stem.casefold() != run_id.casefold():
                record_malformed(report_path, "run_id_filename_mismatch", fields)
                continue
            raw_last_activity = fields.get("last_activity_at")
            last_activity = _parse_time(raw_last_activity)
            if last_activity is None:
                record_malformed(report_path, "invalid_last_activity_at", fields, raw_last_activity)
                continue
            last_activity_utc = last_activity.astimezone(timezone.utc)
            if last_activity_utc > now + timedelta(seconds=60):
                record_malformed(report_path, "future_last_activity_at", fields, raw_last_activity)
                continue
            report_mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            age_minutes = max(
                0.0,
                max(
                    (now - last_activity_utc).total_seconds(),
                    (now - report_mtime).total_seconds(),
                ) / 60.0,
            )
            binding = None
            try:
                binding = load_binding(current_root.parent, run_id)
            except ValueError:
                binding = None
            identity = None
            if isinstance(binding, dict):
                identity = {
                    "authority": binding.get("authority"),
                    "caller_id": binding.get("caller_id"),
                    "create_process_id": binding.get("create_process_id"),
                    "create_started_at": binding.get("create_started_at"),
                }
            running_reports.append({
                "run_id": clipped(run_id, 120),
                "display_label": clipped(fields.get("display_label"), 120),
                "repo": clipped(fields.get("repo"), 180),
                "scope": clipped(fields.get("scope"), 280),
                "state": "RUNNING",
                "last_activity_at": str(fields.get("last_activity_at") or "").strip(),
                "_age_minutes": age_minutes,
                "_identity": identity,
            })
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            record_malformed(report_path, f"read_or_parse_error:{type(exc).__name__}")

    running_reports.sort(key=lambda item: item["_age_minutes"])
    recent_running = [
        item for item in running_reports
        if item["_age_minutes"] <= BOOTSTRAP_MANUAL_RUNNING_RECENT_MINUTES
    ]
    sample: list[dict[str, Any]] = []
    for item in recent_running[:BOOTSTRAP_MANUAL_RUNNING_DETAIL_LIMIT]:
        visible = dict(item)
        visible["age_minutes"] = round(float(visible.pop("_age_minutes")), 1)
        identity = visible.pop("_identity", None)
        if isinstance(identity, dict):
            visible["identity"] = identity
        sample.append(visible)

    scan_truncated = len(report_paths) > len(scan_paths)
    # The content-read cap and the recent-count completeness boundary are not
    # the same thing. Reports are ordered newest-mtime-first, and recent
    # eligibility already requires report mtime to be inside the freshness
    # window. If the bounded scan has reached an mtime older than that window,
    # every unscanned report is necessarily too old to affect the recent count.
    recent_scan_cutoff_reached = not scan_truncated
    if scan_truncated and scan_paths:
        try:
            oldest_scanned_mtime = datetime.fromtimestamp(scan_paths[-1].stat().st_mtime, timezone.utc)
            oldest_scanned_age_minutes = max(0.0, (now - oldest_scanned_mtime).total_seconds() / 60.0)
            recent_scan_cutoff_reached = oldest_scanned_age_minutes > BOOTSTRAP_MANUAL_RUNNING_RECENT_MINUTES
        except OSError:
            # A stat race means we cannot prove that unscanned reports are too
            # old, so retain the conservative lower-bound classification.
            recent_scan_cutoff_reached = False
    return {
        "available": True,
        "path": str(current_root),
        "evidence_semantics": semantics,
        "recent_window_minutes": BOOTSTRAP_MANUAL_RUNNING_RECENT_MINUTES,
        "scan_limit": BOOTSTRAP_MANUAL_CURRENT_SCAN_LIMIT,
        "current_report_file_count": len(report_paths),
        "scanned_report_file_count": len(scan_paths),
        "scan_truncated": scan_truncated,
        "running_reports_in_scan": len(running_reports),
        "recent_running_report_count": len(recent_running),
        "recent_running_report_count_status": "COMPLETE" if recent_scan_cutoff_reached else "LOWER_BOUND",
        "recent_scan_cutoff_reached": recent_scan_cutoff_reached,
        "recent_running_reports": sample,
        "recent_running_reports_truncated": len(recent_running) > len(sample),
        "malformed_running_reports_in_scan": malformed_running_reports,
        "malformed_running_reports": malformed_running_sample,
        "malformed_running_reports_truncated": malformed_running_reports > len(malformed_running_sample),
    }



def _bootstrap_active_manual_run_identities(manual_current: dict[str, Any], live_swarm: dict[str, Any]) -> dict[str, Any]:
    """Annotate live MCP caller activity with the newest exact bound manual run; reports never create liveness."""
    live_callers: dict[str, dict[str, Any]] = {}
    for lane in live_swarm.get("lanes", []) if isinstance(live_swarm, dict) else []:
        if not isinstance(lane, dict):
            continue
        for caller in lane.get("callers", []) if isinstance(lane.get("callers"), list) else []:
            if not isinstance(caller, dict):
                continue
            caller_id = str(caller.get("caller_id") or "").strip()
            if not caller_id:
                continue
            previous = live_callers.get(caller_id)
            current_age = float(caller.get("last_activity_age_seconds") or 1e9)
            previous_age = float(previous.get("last_activity_age_seconds") or 1e9) if isinstance(previous, dict) else 1e9
            if previous is None or current_age < previous_age:
                live_callers[caller_id] = caller

    selected: dict[str, tuple[datetime, dict[str, str]]] = {}
    reports = manual_current.get("recent_running_reports", []) if isinstance(manual_current, dict) else []
    for report in reports if isinstance(reports, list) else []:
        if not isinstance(report, dict):
            continue
        identity = report.get("identity") if isinstance(report.get("identity"), dict) else None
        caller_id = str((identity or {}).get("caller_id") or "").strip()
        run_id = str(report.get("run_id") or "").strip()
        create_process_id = str((identity or {}).get("create_process_id") or "").strip()
        create_started_at = _parse_event_time((identity or {}).get("create_started_at"))
        if not (caller_id and run_id and create_process_id and create_started_at and caller_id in live_callers):
            continue
        row = {"run_id": run_id, "caller_id": caller_id, "create_process_id": create_process_id}
        previous = selected.get(caller_id)
        if previous is None or create_started_at > previous[0]:
            selected[caller_id] = (create_started_at, row)

    rows = [item[1] for item in selected.values()]
    rows.sort(key=lambda item: float(live_callers[item["caller_id"]].get("last_activity_age_seconds") or 1e9))
    return {"runs": rows[:BOOTSTRAP_MANUAL_LIVE_IDENTITY_LIMIT]}


def _bootstrap_swarm_topology(now: datetime | None = None, manual_current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Current user-declared slot topology plus bounded manual-worker context."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    topology_path = ATLAS_LIVE_ROOT / "04 Operating Contracts" / "chatgpt-swarm-topology.json"
    payload: dict[str, Any] = {}
    read_state = "MISSING"
    try:
        candidate = json.loads(topology_path.read_text(encoding="utf-8-sig"))
        if isinstance(candidate, dict):
            payload = candidate
            read_state = "OK"
        else:
            read_state = "INVALID"
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        read_state = "ERROR"

    manual = manual_current if isinstance(manual_current, dict) else _bootstrap_manual_current_status(current_time)
    subscriptions = payload.get("subscriptions") if isinstance(payload.get("subscriptions"), dict) else {}
    handoff = payload.get("handoff") if isinstance(payload.get("handoff"), dict) else {}
    routine_recovery = payload.get("routine_recurring_recovery") if isinstance(payload.get("routine_recurring_recovery"), dict) else {}
    manual_contract = payload.get("manual_workers") if isinstance(payload.get("manual_workers"), dict) else {}
    slot_snapshot = load_slot_snapshot(ATLAS_LIVE_ROOT)
    binding_partitions = {
        name: {
            "slot_capacity": data.get("slot_capacity"),
            "bound_count": data.get("bound_count"),
            "unbound_count": data.get("unbound_count"),
            "slots": data.get("slots"),
        }
        for name, data in slot_snapshot.get("partitions", {}).items()
        if isinstance(data, dict)
    }
    return {
        "authority": payload.get("authority") or "stable_recurring_worker_slots",
        "read_state": read_state,
        "topology_path": str(topology_path),
        "chatgpt_subscription_count": len(RECURRING_WORKER_SLOTS),
        "recurring_worker_partition_count": len(RECURRING_WORKER_SLOTS),
        "recurring_worker_partitions": {name: len(slot_ids) for name, slot_ids in RECURRING_WORKER_SLOTS.items()},
        "recurring_workers_total": RECURRING_WORKER_SLOT_CAPACITY_TOTAL,
        "recurring_workers_total_semantics": "stable_slot_capacity_not_bound_worker_count",
        "slot_bindings": {
            "status": slot_snapshot.get("status"),
            "path": slot_snapshot.get("path"),
            "bound_count": slot_snapshot.get("bound_count"),
            "slot_capacity_total": slot_snapshot.get("slot_capacity_total"),
            "partitions": binding_partitions,
            "semantics": slot_snapshot.get("semantics"),
        },
        "scheduler_boundary": payload.get("recurring_worker_partition_rule") or "five stable recurring slots per partition; bindings may change",
        "subscriptions": subscriptions,
        "routine_recurring_recovery": {
            "authority": routine_recovery.get("authority") or "SUPERVISING_CHAT_OR_OPERATOR_HANDOFF",
            "scheduler_role": routine_recovery.get("scheduler_role") or "RECURRENCE_ONLY",
            "operator_handoff_role": routine_recovery.get("operator_handoff_role") or "ADMINISTRATIVE_FALLBACK_WHEN_SUPERVISING_CHAT_CANNOT_RECOVER",
            "user_role": routine_recovery.get("user_role") or "SETS_TOPOLOGY_AND_OBJECTIVES_NOT_ROUTINE_WORKER_SUPERVISION",
        },
        "operator_handoff": handoff,
        "manual_workers": {
            "population": manual_contract.get("population") or "SEPARATE_ON_DEMAND",
            "counts_against_recurring_slots": bool(manual_contract.get("counts_against_recurring_slots", False)),
            "active_count_authority": manual_contract.get("active_count_authority") or "live MCP/runtime evidence",
            "total_swarm_semantics": manual_contract.get("total_swarm_semantics") or "up to 5 recurring workers in S1 plus up to 5 recurring workers in S2, plus any concurrently active manual/on-demand workers",
            "current_report_hint": {
                "available": manual.get("available") if isinstance(manual, dict) else False,
                "recent_running_report_count": manual.get("recent_running_report_count") if isinstance(manual, dict) else None,
                "recent_running_report_count_status": manual.get("recent_running_report_count_status") if isinstance(manual, dict) else None,
                "evidence_semantics": manual.get("evidence_semantics") if isinstance(manual, dict) else None,
            },
        },
    }

def _bootstrap_manual_sanity() -> dict[str, Any]:
    path = ATLAS_LIVE_ROOT / "worker-reports" / "manual" / "metrics.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {"available": False, "status": "MISSING", "path": str(path)}
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "status": "ERROR", "path": str(path), "error": str(exc)}
    sanity = payload.get("sanity") if isinstance(payload, dict) else None
    if not isinstance(sanity, dict):
        return {"available": False, "status": "NOT_PROJECTED", "path": str(path)}
    return {
        "available": bool(sanity.get("available", True)),
        "path": str(path),
        "baseline_id": sanity.get("baseline_id"),
        "boundary_at": sanity.get("boundary_at"),
        "status": sanity.get("status"),
        "score_delta": sanity.get("score_delta"),
        "descriptive_delta": sanity.get("descriptive_delta"),
        "direction": sanity.get("direction"),
        "post_run_count": sanity.get("post_run_count"),
        "minimum_post_runs_for_provisional": sanity.get("minimum_post_runs_for_provisional"),
        "minimum_post_runs_for_comparable": sanity.get("minimum_post_runs_for_comparable"),
        "axes": sanity.get("axes", {}),
        "guardrails": sanity.get("guardrails", {}),
        "continuation": sanity.get("continuation", {}),
        "components": sanity.get("components", {}),
        "semantics": sanity.get("semantics"),
    }


def _bootstrap_fleet_watch(
    now: datetime | None = None,
    *,
    partition: str | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    """Compact scheduler-probe navigation from local run-lifecycle evidence only.

    Bootstrap uses the canonical partition-local recurring-worker view. Timed workers pass their own automation id
    so scheduler-probe candidates remain inside that worker's subscription partition. Local reports/start receipts are
    run-lifecycle navigation evidence only: they do not provide worker liveness/swarm health and never authorize scheduler mutation.
    """
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    slot_snapshot = load_slot_snapshot(ATLAS_LIVE_ROOT)
    if slot_snapshot.get("status") != "OK":
        return {
            "status": "SLOT_REGISTRY_UNAVAILABLE",
            "authority": "stable_recurring_slots_plus_local_binding_registry",
            "slot_registry_status": slot_snapshot.get("status"),
            "slot_registry_path": slot_snapshot.get("path"),
            "slot_registry_error": slot_snapshot.get("error"),
            "scheduler_probe": "not_performed",
            "local_evidence_scheduler_mutation_authorized": False,
            "same_partition_peer_reenable_after_live_scheduler_confirmation": False,
            "semantics": "missing_or_invalid_slot_binding_registry_is_not_liveness_failure_and_never_authorizes_scheduler_mutation",
        }
    CANONICAL_RECURRING_WORKER_PARTITIONS = {
        name: tuple(
            (row["binding"]["automation_id"], row["binding"].get("label") or row["slot_id"])
            for row in slot_snapshot["partitions"][name]["slots"]
            if row.get("binding") is not None
        )
        for name in RECURRING_WORKER_SLOTS
    }
    CANONICAL_RECURRING_WORKERS = tuple(worker for workers in CANONICAL_RECURRING_WORKER_PARTITIONS.values() for worker in workers)
    CANONICAL_RECURRING_WORKER_PARTITION_BY_ID = {
        worker_id: name
        for name, workers in CANONICAL_RECURRING_WORKER_PARTITIONS.items()
        for worker_id, _label in workers
    }
    SLOT_BY_WORKER_ID = {
        binding["automation_id"]: binding["slot_id"]
        for binding in slot_snapshot.get("bound_workers", [])
    }

    requested_partition = str(partition or "").strip().upper() or None
    worker_key = str(worker_id or "").strip().lower() or None
    if worker_key is not None:
        worker_partition = CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(worker_key)
        if worker_partition is None:
            return {
                "status": "UNBOUND_WORKER_ID",
                "authority": "stable_recurring_slots_plus_local_binding_registry",
                "worker_id": worker_key,
                "scheduler_probe": "not_performed",
            }
        if requested_partition is not None and requested_partition != worker_partition:
            return {
                "status": "PARTITION_MISMATCH",
                "authority": "stable_recurring_slots_plus_local_binding_registry",
                "worker_id": worker_key,
                "requested_partition": requested_partition,
                "worker_partition": worker_partition,
                "scheduler_probe": "not_performed",
            }
        requested_partition = worker_partition
    if requested_partition is not None and requested_partition not in CANONICAL_RECURRING_WORKER_PARTITIONS:
        return {
            "status": "INVALID_PARTITION",
            "authority": "stable_recurring_slots_plus_local_binding_registry",
            "requested_partition": requested_partition,
            "scheduler_probe": "not_performed",
        }

    selected_workers = (
        CANONICAL_RECURRING_WORKER_PARTITIONS[requested_partition]
        if requested_partition is not None
        else CANONICAL_RECURRING_WORKERS
    )
    current_root = ATLAS_LIVE_ROOT / "worker-reports" / "current"
    supervision_root = ATLAS_LIVE_ROOT / "worker-reports" / ".supervision"
    first_expected_start_by_id: dict[str, str] = {
        binding["automation_id"]: str(binding.get("first_expected_start_at") or "").strip()
        for binding in slot_snapshot.get("bound_workers", [])
        if str(binding.get("first_expected_start_at") or "").strip()
    }
    partition_summary = {
        name: {
            "slot_capacity": len(RECURRING_WORKER_SLOTS[name]),
            "expected_recurring_workers": len(RECURRING_WORKER_SLOTS[name]),
            "bound_recurring_workers": len(partition_workers),
            "unbound_slots": [
                row["slot_id"] for row in slot_snapshot["partitions"][name]["slots"] if not row.get("bound")
            ],
            "observed_worker_reports": sum(
                1 for candidate_id, _ in partition_workers
                if (current_root / f"{candidate_id}.md").is_file()
            ) if current_root.is_dir() else 0,
        }
        for name, partition_workers in CANONICAL_RECURRING_WORKER_PARTITIONS.items()
    }
    if not current_root.is_dir():
        return {
            "status": "UNAVAILABLE",
            "authority": "local_worker_reports_and_machine_start_receipts",
            "subscription_scope": requested_partition or "ALL",
            "subscription_count": len(CANONICAL_RECURRING_WORKER_PARTITIONS),
            "worker_partitions": partition_summary,
            "recurring_slot_capacity": len(RECURRING_WORKER_SLOTS[requested_partition]) if requested_partition else RECURRING_WORKER_SLOT_CAPACITY_TOTAL,
            "expected_recurring_workers": len(RECURRING_WORKER_SLOTS[requested_partition]) if requested_partition else RECURRING_WORKER_SLOT_CAPACITY_TOTAL,
            "expected_recurring_workers_total": RECURRING_WORKER_SLOT_CAPACITY_TOTAL,
            "bound_recurring_workers": len(selected_workers),
            "bound_recurring_workers_total": len(CANONICAL_RECURRING_WORKERS),
            "scheduler_probe": "not_performed",
        }

    canonical_ids = {worker_id for worker_id, _ in selected_workers}
    report_cache: dict[str, str] = {}
    recent_recoveries: dict[str, dict[str, Any]] = {}
    recovery_pattern = re.compile(
        r"Peer recovery:\s*sibling=(?P<sibling>[0-9a-f]{32})\s+"
        r"action=is_enabled=true\s+result=success\s+at=(?P<at>[^\s;,]+)",
        re.IGNORECASE,
    )
    legacy_recovery_pattern = re.compile(
        r"Peer recovery:\s*re-enabled canonical sibling .*?"
        r"\((?P<sibling>[0-9a-f]{32})\).*?targeted is_enabled=true succeeded",
        re.IGNORECASE,
    )

    def remember_recovery(sibling_id: str, recovered_at: datetime, actor_id: str, actor_label: str) -> None:
        if sibling_id not in canonical_ids or sibling_id == actor_id:
            return
        if CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(sibling_id) != CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(actor_id):
            return
        recovery_age_minutes = max(0.0, (current_time - recovered_at).total_seconds() / 60.0)
        existing = recent_recoveries.get(sibling_id)
        existing_at = _parse_event_time(existing.get("recovered_at")) if isinstance(existing, dict) else None
        if existing_at is not None and existing_at >= recovered_at:
            return
        recent_recoveries[sibling_id] = {
            "actor": actor_label,
            "actor_id": actor_id,
            "recovered_at": recovered_at.isoformat(),
            "age_minutes": round(recovery_age_minutes, 1),
        }
    for actor_id, actor_label in selected_workers:
        report_path = current_root / f"{actor_id}.md"
        if not report_path.is_file():
            continue
        try:
            raw = report_path.read_text(encoding="utf-8-sig", errors="replace")[:16 * 1024]
        except OSError:
            continue
        report_cache[actor_id] = raw
        for match in recovery_pattern.finditer(raw):
            recovered_at = _parse_event_time(match.group("at"))
            if recovered_at is not None:
                remember_recovery(match.group("sibling").lower(), recovered_at, actor_id, actor_label)

        actor_started_at = None
        for line in raw.splitlines():
            if line.startswith("started_at:"):
                actor_started_at = _parse_event_time(line.split(":", 1)[1].strip())
                break
        if actor_started_at is not None:
            for match in legacy_recovery_pattern.finditer(raw):
                # Legacy findings have no explicit recovery timestamp. Use the acting run's
                # immutable start as a conservative lower bound; last_activity moves and
                # would otherwise extend recovery suppression every time the report updates.
                remember_recovery(match.group("sibling").lower(), actor_started_at, actor_id, actor_label)

    workers: list[dict[str, Any]] = []
    lifecycle_gaps: list[dict[str, Any]] = []
    for worker_id, label in selected_workers:
        report_path = current_root / f"{worker_id}.md"
        fields: dict[str, str] = {}
        raw = report_cache.get(worker_id, "")
        if raw:
            for line in raw.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                if key in {"state", "started_at", "last_activity_at"}:
                    fields[key] = value.strip()

        started = _parse_event_time(fields.get("started_at"))
        last_activity = _parse_event_time(fields.get("last_activity_at"))
        state = str(fields.get("state") or "").upper() or None
        receipt_present = (supervision_root / f"{worker_id}.start.json").is_file()
        age_minutes = None
        if started is not None:
            age_minutes = max(0.0, (current_time - started).total_seconds() / 60.0)
        activity_age_minutes = None
        if last_activity is not None:
            activity_age_minutes = max(0.0, (current_time - last_activity).total_seconds() / 60.0)

        first_expected_start = _parse_event_time(first_expected_start_by_id.get(worker_id))
        if started is None:
            if first_expected_start is not None and current_time <= first_expected_start + timedelta(
                minutes=BOOTSTRAP_RECURRING_RECOVERY_START_GRACE_MINUTES
            ):
                cadence_state = "FIRST_START_PENDING"
            else:
                cadence_state = "NO_LOCAL_START_EVIDENCE"
        elif state == "RUNNING" and not receipt_present:
            cadence_state = (
                "RUNNING_REPORT_WITHOUT_START_RECEIPT"
                if age_minutes is not None and age_minutes > BOOTSTRAP_RECURRING_START_RECEIPT_GRACE_MINUTES
                else "START_RECEIPT_PENDING"
            )
        elif state == "RUNNING" and receipt_present:
            freshness_age = activity_age_minutes if activity_age_minutes is not None else age_minutes
            cadence_state = (
                "RUNNING_REPORT_WITH_START_RECEIPT"
                if freshness_age is not None and freshness_age <= BOOTSTRAP_RECURRING_CADENCE_GRACE_MINUTES
                else "STALE_RUNNING_REPORT_EVIDENCE"
            )
        elif age_minutes is not None and age_minutes > BOOTSTRAP_RECURRING_CADENCE_GRACE_MINUTES:
            cadence_state = "MISSED_EXPECTED_HOURLY_CADENCE"
        else:
            cadence_state = "RECENT_START_EVIDENCE"

        row = {
            "worker": label,
            "automation_id": worker_id,
            "slot_id": SLOT_BY_WORKER_ID.get(worker_id),
            "subscription_partition": CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(worker_id),
            "report_present": report_path.is_file(),
            "state": state,
            "started_at": started.isoformat() if started is not None else None,
            "first_expected_start_at": first_expected_start.isoformat() if first_expected_start is not None else None,
            "last_activity_at": last_activity.isoformat() if last_activity is not None else None,
            "start_age_minutes": round(age_minutes, 1) if age_minutes is not None else None,
            "activity_age_minutes": round(activity_age_minutes, 1) if activity_age_minutes is not None else None,
            "cadence_state": cadence_state,
            "start_receipt_present": receipt_present,
        }
        workers.append(row)
        if cadence_state in {"NO_LOCAL_START_EVIDENCE", "MISSED_EXPECTED_HOURLY_CADENCE", "RUNNING_REPORT_WITHOUT_START_RECEIPT", "STALE_RUNNING_REPORT_EVIDENCE"}:
            recent_recovery = recent_recoveries.get(worker_id)
            probe_actionable = recent_recovery is None
            scheduler_probe_status = "SCHEDULER_PROBE_NEEDED" if probe_actionable else "SCHEDULER_PROBE_PENDING"
            pending_until = None
            if recent_recovery is not None:
                recovered_at = _parse_event_time(recent_recovery.get("recovered_at"))
                if recovered_at is not None and started is not None and started > recovered_at:
                    # A newer local start consumed the older recovery; a later missed cadence
                    # is a fresh scheduler-probe condition and must be eligible again.
                    recent_recovery = None
                    probe_actionable = True
                    scheduler_probe_status = "SCHEDULER_PROBE_NEEDED"
                elif recovered_at is not None and started is not None:
                    elapsed = max(0.0, (recovered_at - started).total_seconds())
                    hourly_steps = int(elapsed // 3600.0) + 1
                    expected_after_recovery = started + timedelta(hours=hourly_steps)
                    pending_until = expected_after_recovery + timedelta(
                        minutes=BOOTSTRAP_RECURRING_RECOVERY_START_GRACE_MINUTES
                    )
                    if current_time > pending_until:
                        probe_actionable = True
                        scheduler_probe_status = "SCHEDULER_PROBE_RETRY_NEEDED"
                elif recovered_at is not None:
                    pending_until = recovered_at + timedelta(
                        minutes=BOOTSTRAP_RECURRING_RECOVERY_COOLDOWN_MINUTES
                    )
                    if current_time > pending_until:
                        probe_actionable = True
                        scheduler_probe_status = "SCHEDULER_PROBE_RETRY_NEEDED"

            gap = {
                "worker": label,
                "automation_id": worker_id,
                "slot_id": SLOT_BY_WORKER_ID.get(worker_id),
                "subscription_partition": CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(worker_id),
                "started_at": row["started_at"],
                "start_age_minutes": row["start_age_minutes"],
                "activity_age_minutes": row["activity_age_minutes"],
                "reason": cadence_state,
                "scheduler_probe_status": scheduler_probe_status,
                "probe_actionable": probe_actionable,
            }
            if recent_recovery is not None:
                gap["last_recovery"] = recent_recovery
            if pending_until is not None:
                gap["scheduler_probe_pending_until"] = pending_until.isoformat()
            lifecycle_gaps.append(gap)
    recovery_candidates = [
        {
            "worker": item["worker"],
            "automation_id": item["automation_id"],
            "slot_id": item.get("slot_id") or SLOT_BY_WORKER_ID.get(item["automation_id"]),
            "subscription_partition": item.get("subscription_partition") or CANONICAL_RECURRING_WORKER_PARTITION_BY_ID.get(item["automation_id"]),
            "reason": item["reason"],
            "requires_live_scheduler_probe": True,
        }
        for item in lifecycle_gaps
        if item.get("probe_actionable")
    ]
    return {
        "status": "LOCAL_RECOVERY_EVIDENCE",
        "authority": "local_run_lifecycle_evidence_over_current_slot_bindings_for_scheduler_probe_navigation",
        "evidence_semantics": "local_run_lifecycle_gaps_for_scheduler_probe_navigation_not_worker_liveness_or_swarm_health",
        "health_verdict": "NOT_PROVIDED",
        "liveness_authority": "live_swarm_runtime_evidence",
        "slot_registry_status": slot_snapshot.get("status"),
        "slot_registry_path": slot_snapshot.get("path"),
        "subscription_scope": requested_partition or "ALL",
        "subscription_count": len(CANONICAL_RECURRING_WORKER_PARTITIONS),
        "worker_partitions": partition_summary,
        "recurring_slot_capacity": len(RECURRING_WORKER_SLOTS[requested_partition]) if requested_partition else RECURRING_WORKER_SLOT_CAPACITY_TOTAL,
        "expected_recurring_workers": len(RECURRING_WORKER_SLOTS[requested_partition]) if requested_partition else RECURRING_WORKER_SLOT_CAPACITY_TOTAL,
        "expected_recurring_workers_total": RECURRING_WORKER_SLOT_CAPACITY_TOTAL,
        "bound_recurring_workers": len(selected_workers),
        "bound_recurring_workers_total": len(CANONICAL_RECURRING_WORKERS),
        "observed_worker_reports": sum(1 for row in workers if row.get("report_present")),
        "running_report_with_start_receipt": sum(1 for row in workers if row.get("cadence_state") == "RUNNING_REPORT_WITH_START_RECEIPT"),
        "recent_start_evidence": sum(1 for row in workers if row.get("cadence_state") == "RECENT_START_EVIDENCE"),
        "first_start_pending": sum(1 for row in workers if row.get("cadence_state") == "FIRST_START_PENDING"),
        "start_receipt_pending": sum(1 for row in workers if row.get("cadence_state") == "START_RECEIPT_PENDING"),
        "running_report_without_start_receipt": sum(1 for row in workers if row.get("cadence_state") == "RUNNING_REPORT_WITHOUT_START_RECEIPT"),
        "lifecycle_gap_count": len(lifecycle_gaps),
        "lifecycle_gaps": lifecycle_gaps,
        "scheduler_probe_candidate_count": len(recovery_candidates),
        "scheduler_probe_candidates": recovery_candidates,
        "recovery_candidate_count": len(recovery_candidates),
        "recovery_candidates": recovery_candidates,
        "recovery_candidate_semantics": "compatibility_alias_for_scheduler_probe_candidates_not_a_liveness_or_health_verdict",
        "local_evidence_scheduler_mutation_authorized": False,
        "same_partition_peer_reenable_after_live_scheduler_confirmation": bool(recovery_candidates),
        "peer_reenable_semantics": "local candidate only; one idempotent is_enabled=true is permitted only after an exact live scheduler read confirms the same-partition target is disabled and the documented startup-failure signature still matches",
        "recovery_candidates_require_live_scheduler_probe": bool(recovery_candidates),
        "recovery_cooldown_minutes": BOOTSTRAP_RECURRING_RECOVERY_COOLDOWN_MINUTES,
        "recovery_start_grace_minutes": BOOTSTRAP_RECURRING_RECOVERY_START_GRACE_MINUTES,
        "start_receipt_grace_minutes": BOOTSTRAP_RECURRING_START_RECEIPT_GRACE_MINUTES,
        "recovery_retry_basis": "next_observed_hourly_phase_plus_grace_then_fallback_cooldown",
        "scheduler_probe": "required_before_scheduler_mutation" if recovery_candidates else "not_performed",
    }


def _bootstrap_worker_status() -> dict[str, Any]:
    """Read current archived timed-worker quality directly from the metrics owner."""
    path = ATLAS_LIVE_ROOT / "worker-reports" / "metrics.json"
    base = {
        "available": False,
        "read_mode": "DIRECT_METRICS",
        "projection_path": str(path),
        "population_scope": "timed_worker_reports_in_live_metrics_window",
        "evidence_semantics": "current_archived_timed_run_quality_not_process_liveness_or_scheduler_membership",
        "current_scheduler_membership": {
            "available": False,
            "authority": "ChatGPT Automations state",
            "reason": "current enabled scheduler membership is not derivable from worker report history",
        },
    }
    try:
        metrics = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {**base, "status": "MISSING"}
    except (OSError, json.JSONDecodeError) as exc:
        return {**base, "status": "ERROR", "error": str(exc)}
    if not isinstance(metrics, dict) or str(metrics.get("population") or "").casefold() != "timed":
        return {**base, "status": "INVALID_METRICS"}

    now = datetime.now(timezone.utc)
    latest_by_worker: dict[str, dict[str, Any]] = {}
    for raw in metrics.get("latest_reports", []) if isinstance(metrics.get("latest_reports"), list) else []:
        if not isinstance(raw, dict):
            continue
        worker_id = str(raw.get("automation_id") or "").strip().lower()
        # Archived timed-run quality is historical evidence, not current scheduler
        # membership. Replacement IDs remain valid history after a slot is rebound.
        if not worker_id or worker_id in latest_by_worker:
            continue
        finished = _parse_event_time(raw.get("finished_at") or raw.get("archived_at"))
        if finished is None:
            continue
        duration = raw.get("duration_minutes")
        utilization = raw.get("target_utilization_pct")
        if not isinstance(utilization, (int, float)) and isinstance(duration, (int, float)):
            utilization = round(float(duration) * 100.0 / 24.0, 1)
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
        age_minutes = max(0.0, (now - finished).total_seconds() / 60.0)
        latest_by_worker[worker_id] = {
            "automation_id": worker_id,
            "display_label": raw.get("display_label"),
            "finished_at": raw.get("finished_at") or raw.get("archived_at"),
            "age_minutes": round(age_minutes, 1),
            "report_freshness": "STALE" if age_minutes >= 90.0 else "RECENT",
            "duration_minutes": round(float(duration), 2) if isinstance(duration, (int, float)) else None,
            "target_minutes": 24.0,
            "target_utilization_pct": round(util, 1) if util is not None else None,
            "classification": classification,
        }

    latest_archived = list(latest_by_worker.values())[:5]
    utilization_values = [float(item["target_utilization_pct"]) for item in latest_archived if isinstance(item.get("target_utilization_pct"), (int, float))]
    duration_values = [float(item["duration_minutes"]) for item in latest_archived if isinstance(item.get("duration_minutes"), (int, float))]
    attention = [
        {
            "worker": item.get("display_label"),
            "duration_minutes": item.get("duration_minutes"),
            "target_minutes": item.get("target_minutes"),
            "utilization_pct": item.get("target_utilization_pct"),
            "classification": item.get("classification"),
            "age_minutes": item.get("age_minutes"),
        }
        for item in latest_archived
        if item.get("report_freshness") == "RECENT" and item.get("classification") in {"SHORT", "PREMATURE", "SEVERELY_PREMATURE"}
    ]
    stale_reports = [
        {"worker": item.get("display_label"), "age_minutes": item.get("age_minutes"), "last_archived_classification": item.get("classification")}
        for item in latest_archived if item.get("report_freshness") == "STALE"
    ]
    result = {
        **base,
        "available": True,
        "status": "CURRENT",
        "generated_at": metrics.get("generated_at"),
        "window_hours": metrics.get("window_hours"),
        "archive_sample": {
            "selection": "five_most_recent_latest_timed_archives_from_live_metrics",
            "sample_limit": 5,
            "sampled_worker_count": len(latest_archived),
            "worker_ids_in_metrics_sample": len(latest_by_worker),
            "population_scope": base["population_scope"],
            "average_latest_duration_minutes": round(sum(duration_values) / len(duration_values), 2) if duration_values else None,
            "average_latest_utilization_pct": round(sum(utilization_values) / len(utilization_values), 1) if utilization_values else None,
            "on_target_count": sum(1 for item in latest_archived if item.get("classification") == "ON_TARGET"),
            "short_or_worse_count": len(attention),
            "stale_report_count": len(stale_reports),
        },
        "attention": attention,
        "stale_reports": stale_reports,
        "classification": {"ON_TARGET": ">=80%", "SHORT": "60-79%", "PREMATURE": "25-59%", "SEVERELY_PREMATURE": "<25%"},
        "historical_timeline_semantics": "timeline worker reports are historical context only and are not used for this current worker-quality block",
    }
    result["manual_sanity"] = _bootstrap_manual_sanity()
    return result


def _read_jsonl_tail(path: Path, max_lines: int, *, max_bytes: int = 8 * 1024 * 1024, chunk_bytes: int = 256 * 1024) -> list[Any]:
    """Parse only the bounded tail of an append-only JSONL file."""
    data = b""
    size = path.stat().st_size
    position = size
    with path.open("rb") as handle:
        while position > 0 and data.count(b"\n") <= max_lines and len(data) < max_bytes:
            take = min(chunk_bytes, position, max_bytes - len(data))
            if take <= 0:
                break
            position -= take
            handle.seek(position)
            data = handle.read(take) + data

    rows: list[Any] = []
    for raw in data.splitlines()[-max_lines:]:
        try:
            rows.append(json.loads(raw.decode("utf-8-sig")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    return rows


def _bootstrap_cache_path(name: str) -> Path:
    root = Path(os.path.expandvars(r"%LOCALAPPDATA%\StackAtlas\bootstrap-cache"))
    return root / name


def _bootstrap_cache_read_any(name: str) -> tuple[dict[str, Any] | None, float | None]:
    path = _bootstrap_cache_path(name)
    try:
        age = max(0.0, datetime.now(timezone.utc).timestamp() - path.stat().st_mtime)
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        return (payload, age) if isinstance(payload, dict) else (None, age)
    except (OSError, json.JSONDecodeError):
        return None, None


def _bootstrap_cache_read(name: str, max_age_seconds: float) -> tuple[dict[str, Any] | None, float | None]:
    payload, age = _bootstrap_cache_read_any(name)
    if payload is None or age is None or age > max_age_seconds:
        return None, age
    return payload, age


def _bootstrap_refresh_lease_path(name: str) -> Path:
    return _bootstrap_cache_path(name).with_name(f"{name}.refresh")


def _bootstrap_try_refresh_lease(name: str, lease_seconds: float) -> bool:
    """Elect one nonblocking refresher; stale readers keep serving the prior snapshot."""
    path = _bootstrap_refresh_lease_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = max(0.0, time.time() - path.stat().st_mtime)
            except OSError:
                continue
            if age > lease_seconds:
                try:
                    path.unlink()
                except OSError:
                    return False
                continue
            return False
        except OSError:
            return True  # Cache acceleration must never block the normal refresh path.
        try:
            os.write(fd, f"{os.getpid()} {time.time():.6f}\n".encode("ascii"))
        finally:
            os.close(fd)
        return True
    return False


def _bootstrap_cache_refresh_view(
    name: str, payload: dict[str, Any] | None, age: float | None, *, max_age_seconds: float, lease_seconds: float,
) -> tuple[dict[str, Any] | None, bool]:
    if payload is not None and age is not None and age <= max_age_seconds:
        return payload, False
    owns_refresh = _bootstrap_try_refresh_lease(name, lease_seconds)
    if payload is not None and not owns_refresh:
        return payload, True
    return None, False


def _bootstrap_cache_write(name: str, payload: dict[str, Any]) -> None:
    path = _bootstrap_cache_path(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _bootstrap_busy_claims_direct() -> list[dict[str, Any]]:
    path = Path(os.path.expandvars(r"%LOCALAPPDATA%\ChatGPTMcpClean\.state\busy-claims.json"))
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    claims = payload.get("claims", []) if isinstance(payload, dict) else []
    return [item for item in claims if isinstance(item, dict)]


def _parse_event_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bootstrap_mcp_source_health(source: dict[str, Any]) -> dict[str, Any]:
    """Probe one backend using identity observed on that MCPv4 transport source."""
    started = time.perf_counter()
    instance = str(source.get("instance") or "") or None
    try:
        observed_port = int(source.get("local_port"))
    except (TypeError, ValueError):
        observed_port = 0
    try:
        observed_pid = int(source.get("server_pid"))
    except (TypeError, ValueError):
        observed_pid = 0
    base = {
        "instance": instance,
        "observed_local_port": observed_port or None,
        "observed_server_pid": observed_pid or None,
    }
    if not (0 < observed_port <= 65535):
        return {
            **base,
            "available": False,
            "status": "IDENTITY_INCOMPLETE",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    url = f"http://127.0.0.1:{observed_port}/health"
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=BOOTSTRAP_MCP_HEALTH_TIMEOUT_SECONDS) as response:
            http_status = int(getattr(response, "status", response.getcode()))
            raw = response.read(8192)
        payload = json.loads(raw.decode("utf-8"))
        runtime_identity = payload.get("runtime_identity") if isinstance(payload.get("runtime_identity"), dict) else {}
        payload_port = int(payload.get("port") or 0)
        payload_pid = int(payload.get("pid") or 0)
        instance_matches = not instance or not runtime_identity.get("instance_id") or runtime_identity.get("instance_id") == instance
        pid_matches = not observed_pid or payload_pid == observed_pid
        healthy = (
            http_status == 200
            and payload.get("status") == "ok"
            and payload.get("name") == "shell-mcp"
            and payload.get("role") == "backend"
            and payload_port == observed_port
            and instance_matches
            and pid_matches
        )
        return {
            **base,
            "available": bool(healthy),
            "status": "LIVE" if healthy else "IDENTITY_MISMATCH",
            "http_status": http_status,
            "backend_generation": payload.get("backend_generation"),
            "pid": payload.get("pid"),
            "port": payload.get("port"),
            "runtime_identity": runtime_identity or None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:
        return {
            **base,
            "available": False,
            "status": "UNAVAILABLE",
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }


def _bootstrap_mcp_backend_health(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Bounded health proof for backends identified by current MCPv4 transport evidence."""
    started = time.perf_counter()
    sources = snapshot.get("transport_sources") if isinstance(snapshot, dict) else None
    now = datetime.now(timezone.utc)
    source_rows = []
    for item in sources if isinstance(sources, list) else []:
        if not isinstance(item, dict):
            continue
        event_at = _parse_event_time(item.get("latest_event_at"))
        if event_at is None or (now - event_at).total_seconds() > BOOTSTRAP_MCP_SOURCE_FRESH_SECONDS:
            continue
        source_rows.append(item)
    if not source_rows:
        return {
            "available": False,
            "status": "IDENTITY_UNKNOWN",
            "authority": "live_transport_source_health",
            "source_count": 0,
            "live_source_count": 0,
            "sources": [],
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    with ThreadPoolExecutor(max_workers=min(4, len(source_rows))) as pool:
        results = list(pool.map(_bootstrap_mcp_source_health, source_rows))
    live = [item for item in results if item.get("status") == "LIVE"]
    probed = [item for item in results if item.get("status") != "IDENTITY_INCOMPLETE"]
    return {
        "available": bool(live),
        "status": "LIVE" if live else ("UNHEALTHY" if probed else "IDENTITY_UNKNOWN"),
        "authority": "live_transport_source_health",
        "source_count": len(source_rows),
        "live_source_count": len(live),
        "sources": results,
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }

def _bootstrap_mcp_status_from_live_swarm(
    snapshot: dict[str, Any], service_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine transport activity with health bound to the observed MCPv4 sources."""
    status = _bootstrap_mcp_from_live_swarm(snapshot)
    had_live_swarm = bool(status.get("available"))
    if service_health is None:
        service_health = _bootstrap_mcp_backend_health(snapshot)
    status["service_health"] = service_health
    if status.get("status") != "LIVE" and service_health.get("status") == "LIVE":
        status["available"] = True
        status["status"] = "LIVE"
    status.setdefault("activity_evidence_status", "BOUNDED" if had_live_swarm else "MISSING")
    status.setdefault("active_session_count_status", "LOWER_BOUND")
    status.setdefault("active_session_count_semantics", MCP_ACTIVE_SESSION_COUNT_SEMANTICS)
    status.setdefault("active_session_count", 0)
    status.setdefault("active_sessions", [])
    status.setdefault("workspace_counts", {})
    status["authority"] = "live_swarm_runtime_evidence"
    return status


def _bootstrap_mcp_status() -> dict[str, Any]:
    """Compatibility status with live activity plus source-bound backend health."""
    snapshot = build_live_swarm_snapshot()
    return _bootstrap_mcp_status_from_live_swarm(snapshot)


def _compact_worker_findings(report: dict[str, Any], limit: int = 3) -> dict[str, Any]:
    findings = report.get("worker_findings") if isinstance(report, dict) else None
    if not isinstance(findings, dict):
        return {}
    populations = []
    for item in findings.get("populations", []) if isinstance(findings.get("populations"), list) else []:
        if not isinstance(item, dict):
            continue
        populations.append({
            key: item.get(key)
            for key in ("population", "status", "generated_at", "source_age_hours", "window_hours", "reports")
        })
    return {
        "contract": findings.get("contract"),
        "top_tags": list(findings.get("top_tags") or [])[:limit],
        "populations": populations[:2],
    }


def _compact_incident_rollups(report: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    rollups = report.get("incident_rollups") if isinstance(report, dict) else None
    if not isinstance(rollups, list):
        return []
    fields = (
        "thread_id", "thread_source", "scope", "observations", "latest_event_at",
        "latest_event_id", "latest_title", "latest_disposition", "drilldown",
    )
    return [
        {key: item.get(key) for key in fields if item.get(key) not in (None, [], "")}
        for item in rollups[: max(0, limit)]
        if isinstance(item, dict)
    ]


def _compact_json_bytes(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _bound_bootstrap_mcp_service_health_sources(
    glance: dict[str, Any], limit: int = BOOTSTRAP_MCP_SERVICE_HEALTH_SOURCE_LIMIT,
) -> bool:
    """Keep MCP source detail useful but bounded while preserving aggregate health counts."""
    mcp = glance.get("mcp")
    service_health = mcp.get("service_health") if isinstance(mcp, dict) else None
    sources = service_health.get("sources") if isinstance(service_health, dict) else None
    if not isinstance(sources, list):
        return False
    detail_limit = max(0, int(limit))
    service_health["source_detail_limit"] = detail_limit
    service_health["sources_truncated"] = len(sources) > detail_limit
    if len(sources) <= detail_limit:
        return False
    service_health["sources"] = sources[:detail_limit]
    return True


def _fit_bootstrap_glance_budget(
    glance: dict[str, Any],
    max_bytes: int = BOOTSTRAP_GLANCE_MAX_BYTES,
    compaction_target_bytes: int = BOOTSTRAP_GLANCE_COMPACTION_TARGET_BYTES,
) -> dict[str, Any]:
    """Compact toward the legacy target while enforcing a larger hard payload ceiling."""
    budget = max(2_048, int(max_bytes))
    compaction_target = max(2_048, min(budget, int(compaction_target_bytes)))
    source = json.loads(json.dumps(glance, ensure_ascii=False))
    source.pop("bootstrap_warning", None)
    source.pop("bootstrap_end", None)
    bounded = {
        "bootstrap_warning": BOOTSTRAP_INTEGRITY_WARNING,
        **source,
        "bootstrap_end": {"status": "COMPLETE", "schema": "bootstrap.v1"},
    }
    source_details_compacted = _bound_bootstrap_mcp_service_health_sources(bounded)
    bootstrap = bounded.setdefault("bootstrap", {})
    if isinstance(bootstrap, dict):
        bootstrap["payload_budget"] = {
            "max_bytes": budget,
            "compaction_target_bytes": compaction_target,
            "compacted": source_details_compacted,
        }

    if _compact_json_bytes(bounded) <= compaction_target:
        return bounded

    recovery = bounded.get("mcp_recovery_state")
    if isinstance(recovery, dict):
        conditions = recovery.get("conditions")
        if isinstance(conditions, list):
            recovery["conditions"] = [
                {key: item.get(key) for key in ("type", "status", "reason") if key in item}
                for item in conditions
                if isinstance(item, dict)
            ]
        invariants = recovery.get("recovery_invariants")
        if isinstance(invariants, list):
            recovery["recovery_invariants"] = [_clip_bootstrap_text(item, 96) for item in invariants]
        for key in ("preservation_rule", "authorization_rule"):
            if isinstance(recovery.get(key), str):
                recovery[key] = _clip_bootstrap_text(recovery[key], 96)
        safety_rules = recovery.get("replacement_safety_rules")
        if isinstance(safety_rules, list):
            recovery["replacement_safety_rules"] = [_clip_bootstrap_text(item, 96) for item in safety_rules]
        latest_restore = recovery.get("latest_topology_restore")
        if isinstance(latest_restore, dict):
            recovery["latest_topology_restore"] = {
                key: latest_restore.get(key)
                for key in ("incident_id", "before_transport", "after_transport", "backend_artifact_matches_selected_recovery", "failed_replacement_status", "fresh_mcp_process_call")
                if key in latest_restore
            }


    if _compact_json_bytes(bounded) > compaction_target:
        freshness = bounded.get("source_freshness")
        if isinstance(freshness, dict):
            freshness.pop("meaning", None)
            freshness.pop("cache", None)
            sources = freshness.get("sources")
            if isinstance(sources, dict):
                for item in sources.values():
                    if not isinstance(item, dict):
                        continue
                    for key in ("path", "last_update_commit", "last_updated_at", "local_last_committed_at", "local_matches_remote_main"):
                        item.pop(key, None)

    workers = bounded.get("workers")
    if _compact_json_bytes(bounded) > compaction_target and isinstance(workers, dict):
        sanity = workers.get("manual_sanity")
        if isinstance(sanity, dict):
            workers["manual_sanity"] = {
                key: sanity.get(key)
                for key in (
                    "available", "baseline_id", "status", "score_delta", "direction", "post_run_count",
                    "minimum_post_runs_for_provisional", "minimum_post_runs_for_comparable",
                )
                if key in sanity
            }

    mcp = bounded.get("mcp")
    if _compact_json_bytes(bounded) > compaction_target and isinstance(mcp, dict):
        activity = mcp.get("activity_summary")
        if isinstance(activity, dict):
            mcp["activity_summary"] = {
                key: activity.get(key)
                for key in ("activity_window_seconds", "activity_window_complete", "starts", "reads", "exits", "kills", "nonzero_exits", "last_event_at")
                if key in activity
            }
        mcp.pop("cache", None)

    # Active-session detail is an intentionally bounded work/status view.
    # Preserve the configured sample while the payload remains under the hard budget.

    if _compact_json_bytes(bounded) > compaction_target and isinstance(bounded.get("workers"), dict):
        for key in ("attention", "stale_reports"):
            items = bounded["workers"].get(key)
            if isinstance(items, list) and len(items) > 1:
                bounded["workers"][key] = items[:1]

    if _compact_json_bytes(bounded) > compaction_target and isinstance(bounded.get("workers"), dict):
        workers = bounded["workers"]
        workers.pop("archive_sample", None)
        workers.pop("attention", None)
        workers.pop("stale_reports", None)

    if _compact_json_bytes(bounded) > compaction_target and isinstance(bounded.get("swarm_topology"), dict):
        topo = bounded["swarm_topology"]
        handoff = topo.get("operator_handoff") if isinstance(topo.get("operator_handoff"), dict) else {}
        routine_recovery = topo.get("routine_recurring_recovery") if isinstance(topo.get("routine_recurring_recovery"), dict) else {}
        manual = topo.get("manual_workers") if isinstance(topo.get("manual_workers"), dict) else {}
        execution_nodes = topo.get("execution_nodes") if isinstance(topo.get("execution_nodes"), dict) else {}
        raw_nodes = execution_nodes.get("nodes") if isinstance(execution_nodes.get("nodes"), dict) else {}
        compact_nodes = {
            node_id: {
                key: node.get(key)
                for key in ("display_name", "user_alias", "route_label", "machine_class", "gpu")
                if isinstance(node, dict) and node.get(key) is not None
            }
            for node_id, node in raw_nodes.items()
            if isinstance(node_id, str) and isinstance(node, dict)
        }
        compact_execution_nodes = {
            key: execution_nodes.get(key)
            for key in ("authority", "available", "status", "local_node_id", "local_observed_hostname")
            if key in execution_nodes
        }
        if compact_nodes:
            compact_execution_nodes["nodes"] = compact_nodes
        bounded["swarm_topology"] = {
            key: topo.get(key) for key in ("authority", "chatgpt_subscription_count", "recurring_worker_partitions", "recurring_workers_total") if key in topo
        }
        bounded["swarm_topology"]["routine_recurring_recovery"] = {
            key: routine_recovery.get(key)
            for key in ("authority", "scheduler_role", "operator_handoff_role", "user_role")
            if key in routine_recovery
        }
        bounded["swarm_topology"]["operator_handoff"] = {"primary_operator_subscription": handoff.get("primary_operator_subscription")}
        bounded["swarm_topology"]["manual_workers"] = {key: manual.get(key) for key in ("population", "active_count_authority", "total_swarm_semantics") if key in manual}
        bounded["swarm_topology"]["execution_nodes"] = compact_execution_nodes

    # Live-swarm lanes are a bounded work/status view, not an evidence-completeness signal.
    # Preserve the configured recent lane sample while the payload remains under the hard budget.

    if _compact_json_bytes(bounded) > compaction_target and isinstance(bounded.get("commands"), dict):
        commands = bounded["commands"]
        compact_commands = {
            "bootstrap": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance",
            "live_swarm": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py live-swarm",
            "fleet_watch": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>",
            "stack_owner": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup <id-or-alias>",
            "stack_find": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py find <query>",
            "production_change_gate": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py production-change-gate <component> --actor <actor> --busy-scope <exact-scope>",
            "memory_overview": r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py overview",
            "tiny3d_asset_library": "lookup tiny3d_library",
        }
        bounded["commands"] = {key: compact_commands[key] for key in compact_commands if key in commands}

    if _compact_json_bytes(bounded) > compaction_target and isinstance(bounded.get("paths"), dict):
        paths = bounded["paths"]
        bounded["paths"] = {key: paths.get(key) for key in ("rules", "agents", "vault", "mcp", "mcp_current_topology", "mcp_recovery_state", "mcp_security_routing_log", "issue_first_work_intake") if key in paths}

    if _compact_json_bytes(bounded) > compaction_target and isinstance(bounded.get("mcp_recovery_state"), dict):
        recovery = bounded["mcp_recovery_state"]
        bounded["mcp_recovery_state"] = {
            key: recovery.get(key)
            for key in (
                "available", "read_state", "authority", "recovery_target_deployment_id",
                "recovery_target_generation", "recovery_selected_at", "scope", "details_path",
                "status", "path", "selected_recovery_target", "conditions",
            )
            if recovery.get(key) not in (None, "", [], {})
        }

    final_bytes = _compact_json_bytes(bounded)
    if final_bytes > budget:
        raise ValueError(
            f"BOOTSTRAP_BUDGET_EXCEEDED_WITH_MEMORY_GLANCE_PRESERVED "
            f"bytes={final_bytes} target={compaction_target} budget={budget}"
        )

    if isinstance(bootstrap, dict):
        bootstrap["payload_budget"]["compacted"] = True
    return bounded


def _clip_bootstrap_text(value: Any, limit: int) -> Any:
    if not isinstance(value, str) or len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3] + "..."


def _compact_timeline_snapshots(report: dict[str, Any]) -> dict[str, Any]:
    """Project timeline history into shallow urgency/recurrence signals only."""
    raw = report.get("timeline_snapshots")
    if not isinstance(raw, dict):
        return {}

    def short_at(value: Any) -> Any:
        value_text = str(value or "")
        match = re.match(r"^\d{4}-(\d{2}-\d{2})T(\d{2}:\d{2})", value_text)
        return f"{match.group(1)} {match.group(2)}" if match else value

    def compact_signal_summary(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        keys = ("total", "red", "slopwall", "asshole", "incident", "regression", "security_incident")
        return {key: value.get(key) for key in keys if value.get(key) not in (None, 0)}

    windows: list[dict[str, Any]] = []
    for window in raw.get("windows", []) if isinstance(raw.get("windows"), list) else []:
        if not isinstance(window, dict):
            continue
        label = str(window.get("window") or "")
        case_counts = window.get("cases") if isinstance(window.get("cases"), dict) else window.get("continuity_case_summary")
        density = window.get("evidence_density") if isinstance(window.get("evidence_density"), dict) else window.get("signal_observation_summary")
        raw_examples = window.get("case_examples")
        if not isinstance(raw_examples, list):
            raw_examples = window.get("continuity_case_examples")
        if not isinstance(raw_examples, list):
            raw_examples = window.get("continuity_cases") if isinstance(window.get("continuity_cases"), list) else []
        ordered_examples = sorted(
            (case for case in raw_examples if isinstance(case, dict)),
            key=lambda case: (
                1 if case.get("severity") == "RED" else 0,
                1 if str(case.get("id") or case.get("case_id") or "").casefold().startswith("incident:") else 0,
                str(case.get("at") or case.get("latest_signal_at") or ""),
                str(case.get("id") or case.get("case_id") or ""),
            ),
            reverse=True,
        )
        examples = []
        for case in ordered_examples[: (3 if label == "24h" else 1)]:
            compact = {
                "id": _clip_bootstrap_text(case.get("id") or case.get("case_id"), 120),
                "severity": case.get("severity") if case.get("severity") == "RED" else None,
                "traits": case.get("traits"),
                "observations": case.get("observations") or case.get("observation_count"),
                "at": short_at(case.get("at") or case.get("latest_signal_at")),
                "title": _clip_bootstrap_text(case.get("title") or case.get("latest_title"), 96),
            }
            examples.append({key: value for key, value in compact.items() if value not in (None, {}, [], "")})
        windows.append({
            key: value for key, value in {
                "window": label,
                "cases": compact_signal_summary(case_counts),
                "evidence_density": compact_signal_summary(density),
                "observations": window.get("observations") if window.get("observations") is not None else window.get("event_count"),
                "case_examples": examples,
            }.items() if value not in (None, {}, [], "")
        })

    raw_coverage = raw.get("coverage") if isinstance(raw.get("coverage"), dict) else {}
    if any(key in raw_coverage for key in ("repo_saturated", "artifacts_saturated", "workers_bounded")):
        coverage = {
            key: raw_coverage.get(key)
            for key in ("repo_saturated", "artifacts_saturated", "workers_bounded")
            if raw_coverage.get(key) not in (None, [], {})
        }
    else:
        repos = raw_coverage.get("repos") if isinstance(raw_coverage.get("repos"), dict) else {}
        coverage = {
            "repo_saturated": sorted(name for name, item in repos.items() if isinstance(item, dict) and item.get("saturated")),
            "artifacts_saturated": bool(isinstance(raw_coverage.get("artifacts"), dict) and raw_coverage["artifacts"].get("saturated")),
            "workers_bounded": (raw_coverage.get("workers") or {}).get("bounded") if isinstance(raw_coverage.get("workers"), dict) else None,
        }
        coverage = {key: value for key, value in coverage.items() if value not in (None, [], {})}

    memory_history = raw.get("memory_history") if isinstance(raw.get("memory_history"), dict) else raw.get("preserved_memory_history")
    memory_history = memory_history if isinstance(memory_history, dict) else {}
    memory_history = {
        "red_observations": memory_history.get("red_observations"),
        "cases": compact_signal_summary(memory_history.get("cases") if isinstance(memory_history.get("cases"), dict) else memory_history.get("continuity_case_summary")),
    }
    memory_history = {key: value for key, value in memory_history.items() if value not in (None, {}, [], "")}
    return {
        "authority": raw.get("authority"),
        "memory_history": memory_history,
        "coverage": coverage,
        "windows": windows,
    }


def _fit_memory_overview_budget(overview: dict[str, Any], max_bytes: int = BOOTSTRAP_MEMORY_OVERVIEW_MAX_BYTES) -> dict[str, Any]:
    """Enforce the shallow startup-memory schema; detail requires explicit memory retrieval."""
    budget = max(512, int(max_bytes))
    raw = json.loads(json.dumps(overview, ensure_ascii=False))
    materialized = raw.get("timeline_materialized") if isinstance(raw.get("timeline_materialized"), dict) else {}
    correction_triggers = raw.get("correction_triggers") if isinstance(raw.get("correction_triggers"), dict) else {}
    recent_source = raw.get("recent_source") if isinstance(raw.get("recent_source"), dict) else {}
    recent = []
    for item in raw.get("recent", []) if isinstance(raw.get("recent"), list) else []:
        if not isinstance(item, dict):
            continue
        recent.append({
            key: value for key, value in {
                "id": item.get("id"),
                "timestamp": item.get("timestamp"),
                "title": _clip_bootstrap_text(item.get("title"), 96),
            }.items() if value not in (None, "")
        })
        if len(recent) >= 3:
            break
    projects = [
        {key: item.get(key) for key in ("name", "count") if item.get(key) not in (None, "")}
        for item in raw.get("projects", [])[:3]
        if isinstance(item, dict)
    ] if isinstance(raw.get("projects"), list) else []
    recurring_tags = [
        {key: item.get(key) for key in ("name", "count") if item.get(key) not in (None, "")}
        for item in raw.get("recurring_tags", [])[:3]
        if isinstance(item, dict)
    ] if isinstance(raw.get("recurring_tags"), list) else []
    bounded = {
        "contract": "BOOTSTRAP_MEMORY_GLANCE_ONLY; shallow urgency/state/recurrence orientation; use memory context/timeline for detail",
        "eligible_entries": raw.get("eligible_entries", 0),
        "timeline_snapshots": _compact_timeline_snapshots(raw),
        "incident_rollups": _compact_incident_rollups(raw, 3),
        "recent": recent,
        "projects": projects,
        "recurring_tags": recurring_tags,
    }
    if correction_triggers:
        bounded["correction_triggers"] = {
            key: correction_triggers.get(key)
            for key in ("authority", "status")
            if correction_triggers.get(key) not in (None, "")
        }
    if recent_source:
        bounded["recent_source"] = {
            key: recent_source.get(key)
            for key in ("authority", "read_mode", "status", "generated_at")
            if recent_source.get(key) not in (None, "")
        }
    if materialized:
        bounded["timeline_materialized"] = {
            key: materialized.get(key)
            for key in (
                "status", "as_of", "coverage_status", "absence_semantics", "age_seconds", "backfill_incomplete_sources",
                "retry_sources", "timeline_truncated", "live_truth_required", "read_mode", "refresh_command",
            )
            if materialized.get(key) not in (None, "", [], {})
        }

    if _compact_json_bytes(bounded) <= budget:
        return bounded

    for key in ("projects", "recurring_tags", "recent"):
        items = bounded.get(key)
        if isinstance(items, list):
            bounded[key] = items[:1]
    snapshots = bounded.get("timeline_snapshots")
    windows = snapshots.get("windows") if isinstance(snapshots, dict) else None
    if isinstance(windows, list):
        for window in windows:
            if not isinstance(window, dict):
                continue
            if window.get("window") != "24h":
                window.pop("case_examples", None)
            elif isinstance(window.get("case_examples"), list):
                window["case_examples"] = window["case_examples"][:1]
    if _compact_json_bytes(bounded) <= budget:
        return bounded

    rollups = bounded.get("incident_rollups")
    if isinstance(rollups, list):
        bounded["incident_rollups"] = rollups[:1]
    if isinstance(windows, list):
        for window in windows:
            if isinstance(window, dict) and window.get("window") != "24h":
                window.pop("evidence_density", None)
    if _compact_json_bytes(bounded) <= budget:
        return bounded

    for key in ("projects", "recurring_tags", "recent"):
        bounded[key] = []
    if isinstance(windows, list):
        for window in windows:
            if isinstance(window, dict):
                window.pop("case_examples", None)
                window.pop("evidence_density", None)
    if _compact_json_bytes(bounded) <= budget:
        return bounded

    raise ValueError(f"BOOTSTRAP_MEMORY_GLANCE_BUDGET_EXCEEDED bytes={_compact_json_bytes(bounded)} budget={budget}")


def _compact_memory_overview(report: dict[str, Any], limit: int = 3) -> dict[str, Any]:
    effective_limit = max(0, int(limit))
    raw_rollups = [item for item in report.get("incident_rollups", []) if isinstance(item, dict)][:effective_limit]
    covered_ids = {str(memory_id) for item in raw_rollups for memory_id in item.get("member_ids", [])}
    compact_rollups = _compact_incident_rollups({"incident_rollups": raw_rollups}, effective_limit)
    recent = [
        {k: item.get(k) for k in ("id", "timestamp", "title")}
        for item in report.get("recent", [])
        if str(item.get("id")) not in covered_ids
    ][:effective_limit]
    overview = {
        "contract": report.get("contract"),
        "eligible_entries": report.get("eligible_entries", 0),
        "timeline_snapshots": _compact_timeline_snapshots(report),
        "incident_rollups": compact_rollups,
        "recent": recent,
        "projects": report.get("projects", [])[:effective_limit],
        "recurring_tags": report.get("recurring_tags", [])[:effective_limit],
    }
    return _fit_memory_overview_budget(overview)


def _bootstrap_memory_overview() -> dict[str, Any]:
    """Read the periodic Vault timeline projection; never rebuild timeline sources here."""
    try:
        from tools.timeline_materializer import BOOTSTRAP_PATH, materialized_health, timeline_read_state_root
    except ImportError:
        from timeline_materializer import BOOTSTRAP_PATH, materialized_health, timeline_read_state_root
    path = timeline_read_state_root(ATLAS_LIVE_ROOT) / BOOTSTRAP_PATH.name
    base_missing = {
        "contract": "Periodic Vault timeline projection only; bootstrap never scans Git, GitHub, workers, reports, MCP logs, or artifact history to rebuild it.",
        "eligible_entries": 0,
        "timeline_snapshots": {},
        "incident_rollups": [],
        "recent": [],
        "projects": [],
        "recurring_tags": [],
    }
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {
            **base_missing,
            "timeline_materialized": {
                "status": "MISSING",
                "projection_path": str(path),
                "refresh_command": f'python "{ATLAS_LIVE_ROOT / "tools" / "timeline_materializer.py"}" refresh',
            },
        }
    except (OSError, json.JSONDecodeError) as exc:
        return {
            **base_missing,
            "timeline_materialized": {
                "status": "ERROR",
                "projection_path": str(path),
                "error": str(exc),
            },
        }
    if not isinstance(raw, dict) or not isinstance(raw.get("overview"), dict):
        return {
            **base_missing,
            "timeline_materialized": {
                "status": "ERROR",
                "projection_path": str(path),
                "error": "materialized bootstrap projection has invalid shape",
            },
        }

    # Copy so bootstrap annotation never mutates the persisted projection. Freshness
    # and evidence-completeness semantics are owned by the materializer so overview,
    # timeline queries, and bootstrap cannot drift apart.
    overview = json.loads(json.dumps(raw["overview"], ensure_ascii=False))
    materialized = overview.get("timeline_materialized")
    materialized = dict(materialized) if isinstance(materialized, dict) else {}
    materialized.update(materialized_health(raw, now=datetime.now().astimezone()))
    materialized["projection_path"] = str(path)
    overview["timeline_materialized"] = materialized

    # Recent memory has a separate immediate projection. Timeline/history stays on
    # the periodic materializer, while fresh-chat orientation reads current titles.
    seed_path = ATLAS_LIVE_ROOT / "memory" / "memory-bank.jsonl"
    overlay_path = default_local_bank_path()
    recent_projection = read_current_projection(seed_path=seed_path, overlay_path=overlay_path)
    if isinstance(recent_projection, dict) and isinstance(recent_projection.get("recent"), list):
        overview["recent"] = recent_projection["recent"]
        overview["recent_source"] = {
            "authority": "DIRECT_LOCAL_EFFECTIVE_MEMORY_PROJECTION",
            "read_mode": "fingerprint_validated_recent_titles_projection",
            "status": "CURRENT_FOR_EFFECTIVE_MEMORY_FILES",
            "generated_at": recent_projection.get("generated_at"),
        }
    return _fit_memory_overview_budget(overview)


def _bootstrap_memory_titles() -> list[dict[str, Any]]:
    """Backward-compatible accessor for callers that only need recent titles."""
    return list(_bootstrap_memory_overview().get("recent", []))


def _bootstrap_mcp_current_topology() -> dict[str, Any]:
    path = MCP_CURRENT_TOPOLOGY_PATH
    if not path.exists():
        return {"available": False, "read_state": "MISSING", "path": str(path)}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "read_state": "ERROR", "path": str(path), "error": str(exc)}
    if not isinstance(raw, dict) or raw.get("schema") != "mcp-current-topology.v1":
        return {"available": False, "read_state": "ERROR", "path": str(path), "error": "invalid mcp-current-topology.v1 contract"}
    serving = raw.get("serving", {}) if isinstance(raw.get("serving"), dict) else {}
    backend = serving.get("backend", {}) if isinstance(serving.get("backend"), dict) else {}
    serving_path = serving.get("path")
    backend_listen = backend.get("listen")
    if not isinstance(serving_path, list) or not serving_path or not isinstance(backend_listen, str) or serving_path[-1] != backend_listen:
        return {
            "available": False,
            "read_state": "ERROR",
            "path": str(path),
            "error": "mcp-current-topology.v1 serving.path/backend.listen mismatch",
        }
    surface = raw.get("chatgpt_surface", {}) if isinstance(raw.get("chatgpt_surface"), dict) else {}
    recovery = raw.get("recovery", {}) if isinstance(raw.get("recovery"), dict) else {}
    image_delivery = surface.get("image_delivery", {}) if isinstance(surface.get("image_delivery"), dict) else {}
    return {
        "available": True,
        "read_state": "OK",
        "authority": raw.get("authority"),
        "connector_url": serving.get("connector_url"),
        "public_origin": serving.get("public_origin"),
        "authorization_endpoint": serving.get("authorization_endpoint"),
        "serving_path": serving.get("path"),
        "tool_count": surface.get("tool_count"),
        "tools": surface.get("tools"),
        "image_delivery_adds_tool": image_delivery.get("adds_tool"),
        "excluded_actions": surface.get("excluded_actions"),
        "not_in_gpt1_path": raw.get("not_in_gpt1_path"),
        "independent_local_control": recovery.get("independent_local_control"),
        "details_path": str(path),
    }


def _bootstrap_mcp_recovery_state() -> dict[str, Any]:
    path = MCP_RECOVERY_STATE_PATH
    if not path.exists():
        return {"available": False, "read_state": "MISSING", "path": str(path)}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "read_state": "ERROR", "path": str(path), "error": str(exc)}
    if not isinstance(raw, dict):
        return {"available": False, "read_state": "ERROR", "path": str(path), "error": "recovery state is not an object"}
    deployment = raw.get("deployment", {}) if isinstance(raw.get("deployment"), dict) else {}
    recovery_target = raw.get("recovery_target", {}) if isinstance(raw.get("recovery_target"), dict) else {}
    policy = recovery_target.get("policy", {}) if isinstance(recovery_target.get("policy"), dict) else {}
    evidence = raw.get("evidence", {}) if isinstance(raw.get("evidence"), dict) else {}
    observation = evidence.get("latest_restore_observation", {}) if isinstance(evidence.get("latest_restore_observation"), dict) else {}
    topology_restore = evidence.get("latest_topology_restore_observation", {}) if isinstance(evidence.get("latest_topology_restore_observation"), dict) else {}
    known_transients = evidence.get("known_transients", []) if isinstance(evidence.get("known_transients"), list) else []
    replacement_safety_rules = [
        str(item.get("rule"))
        for item in known_transients
        if isinstance(item, dict) and str(item.get("rule") or "").strip()
    ]
    recovery_lanes = recovery_target.get("recovery_lanes", {}) if isinstance(recovery_target.get("recovery_lanes"), dict) else {}
    recovery_invariants = [
        str(item) for item in policy.get("recovery_invariants", [])
        if str(item or "").strip()
    ] if isinstance(policy.get("recovery_invariants"), list) else []
    before_restore = topology_restore.get("before_restore", {}) if isinstance(topology_restore.get("before_restore"), dict) else {}
    failed_replacement = topology_restore.get("failed_replacement_attempt", {}) if isinstance(topology_restore.get("failed_replacement_attempt"), dict) else {}
    restore = topology_restore.get("restore", {}) if isinstance(topology_restore.get("restore"), dict) else {}
    conditions = raw.get("conditions", []) if isinstance(raw.get("conditions"), list) else []
    bounded_conditions = [
        {
            key: condition.get(key)
            for key in ("type", "status", "last_transition_at")
            if key in condition
        }
        for condition in conditions
        if isinstance(condition, dict)
    ]
    return {
        "available": True,
        "read_state": "OK",
        "authority": "recovery_target_not_live_serving_identity",
        "recovery_target_deployment_id": recovery_target.get("deployment_id") or deployment.get("id"),
        "recovery_target_generation": deployment.get("generation"),
        "recovery_selected_at": recovery_target.get("selected_at"),
        "automatic_routing": recovery_lanes.get("automatic_routing"),
        "ssh_role": recovery_lanes.get("ssh_role"),
        "conditions": bounded_conditions,
        "restore_first_on_regression": bool(policy.get("restore_first_on_regression")),
        "recovery_invariants": recovery_invariants,
        "preservation_rule": policy.get("preservation_rule"),
        "authorization_rule": policy.get("authorization_rule"),
        "replacement_safety_rules": replacement_safety_rules,
        "latest_topology_restore": {
            "observed_at": topology_restore.get("observed_at"),
            "incident_id": topology_restore.get("incident_id"),
            "before_transport": before_restore.get("caddy_transport"),
            "after_transport": "wireguard" if restore else None,
            "backend_generation": restore.get("backend_generation") or before_restore.get("backend_generation"),
            "backend_artifact_matches_selected_recovery": before_restore.get("backend_artifact_matches_selected_recovery"),
            "failed_replacement_status": failed_replacement.get("status"),
            "public_health_statuses": restore.get("public_health_statuses"),
            "fresh_mcp_process_call": restore.get("fresh_mcp_process_call"),
        } if topology_restore else None,
        "post_restore_no_mcp_request_in_flight": bool(observation.get("post_restore_no_mcp_request_in_flight")),
    }


def _bootstrap_mcp_recovery_orientation(state: dict[str, Any]) -> dict[str, Any]:
    """Keep recovery metadata visible without projecting historical topology as startup truth."""
    if not isinstance(state, dict):
        return {"available": False, "read_state": "ERROR", "scope": "recovery_only_not_live_topology"}
    result = {
        key: state.get(key)
        for key in (
            "available", "read_state", "authority", "recovery_target_deployment_id",
            "recovery_target_generation", "recovery_selected_at",
        )
        if key in state
    }
    result["scope"] = "recovery_only_not_live_topology"
    result["details_path"] = str(MCP_RECOVERY_STATE_PATH)
    if state.get("error"):
        result["error"] = state.get("error")
    return result

def _bootstrap_vault_status() -> dict[str, Any]:
    """Bounded local Vault health; no fetches, history scans, or repo-wide status walk."""
    started = time.perf_counter()
    root = ROOT
    memory_path = root / "memory" / "memory-bank.jsonl"
    result: dict[str, Any] = {
        "available": root.exists(),
        "status": "OK",
        "root_exists": root.exists(),
        "bootstrap_file_exists": (root / "tools" / "stack_atlas.py").is_file(),
        "memory_bank_exists": memory_path.is_file(),
    }
    if not root.exists():
        result.update({"available": False, "status": "UNAVAILABLE", "latency_ms": round((time.perf_counter() - started) * 1000, 1)})
        return result

    git = shutil.which("git")
    result["git_cli_available"] = bool(git)
    result["attention_required"] = False
    if git:
        # Observation only: the dedicated sync owner refreshes origin/main. Bootstrap never fetches.
        git_deadline = time.monotonic() + 2.0
        cached_remote_main = None
        timeout = _remaining_bootstrap_git_timeout(git_deadline)
        if timeout is not None:
            try:
                remote_proc = _run_process(
                    [git, "-C", str(root), "rev-parse", "--verify", "refs/remotes/origin/main"],
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                )
                if remote_proc.returncode == 0:
                    cached_remote_main = remote_proc.stdout.strip() or None
            except (OSError, subprocess.TimeoutExpired):
                cached_remote_main = None
        checkout = _git_checkout_state(root, cached_remote_main, deadline=git_deadline)
        result["checkout"] = checkout
        result["git_worktree"] = bool(checkout.get("available"))
        if checkout.get("local_head"):
            result["head"] = checkout.get("local_head")
        result["attention_required"] = not bool(checkout.get("coherent"))
        if not checkout.get("coherent"):
            result["status"] = "DEGRADED"
    else:
        result["git_worktree"] = False
        result["attention_required"] = True
        result["status"] = "DEGRADED"

    if memory_path.is_file():
        try:
            stat = memory_path.stat()
            result["memory_bank_bytes"] = stat.st_size
            result["memory_bank_age_seconds"] = round(max(0.0, time.time() - stat.st_mtime), 1)
            tail = _read_jsonl_tail(memory_path, 1)
            result["memory_bank_tail_readable"] = bool(tail)
            if not tail and stat.st_size > 0:
                result["status"] = "DEGRADED"
        except OSError:
            result["memory_bank_tail_readable"] = False
            result["status"] = "DEGRADED"
    else:
        result["memory_bank_tail_readable"] = False
        result["status"] = "DEGRADED"

    if not result["bootstrap_file_exists"]:
        result["status"] = "DEGRADED"
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


def _bootstrap_github_status() -> dict[str, Any]:
    """Bounded cached GitHub health; never lists issues, PRs, checks, or workflows."""
    started = time.perf_counter()
    cached_raw, cache_age = _bootstrap_cache_read_any("github-status.json")
    cached_status = str((cached_raw or {}).get("status") or "")
    cache_max_age = (
        BOOTSTRAP_GITHUB_CACHE_SECONDS
        if cached_status in {"OK", "WATCH", ""}
        else BOOTSTRAP_GITHUB_FAILURE_CACHE_SECONDS
    )
    cached, stale_while_refresh = _bootstrap_cache_refresh_view(
        "github-status.json", cached_raw, cache_age, max_age_seconds=cache_max_age, lease_seconds=4.0
    )
    if cached is not None:
        cached = dict(cached)
        cached["cache"] = {
            "used": True,
            "age_seconds": round(cache_age or 0.0, 3),
            "max_age_seconds": cache_max_age,
            **({"stale_while_refresh": True} if stale_while_refresh else {}),
        }
        cached["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return cached

    gh = shutil.which("gh")
    result: dict[str, Any] = {
        "available": False,
        "status": "UNAVAILABLE",
        "cli_available": bool(gh),
        "authenticated": False,
        "api_reachable": False,
    }

    if gh:
        api: subprocess.CompletedProcess[str] | None = None
        try:
            api = _run_process(
                [gh, "api", "rate_limit"],
                text=True,
                capture_output=True,
                timeout=BOOTSTRAP_GITHUB_API_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

        if api is not None and api.returncode == 0:
            # A successful authenticated API call proves both auth and reachability;
            # avoid the redundant `gh auth status` subprocess on the normal path.
            result.update({"available": True, "authenticated": True, "api_reachable": True})
            try:
                payload = json.loads(api.stdout)
                core = payload.get("resources", {}).get("core", {}) if isinstance(payload, dict) else {}
                limit = int(core.get("limit") or 0)
                remaining = int(core.get("remaining") or 0)
                used = int(core.get("used") or 0)
                reset = int(core.get("reset") or 0)
                remaining_pct = round((remaining / limit) * 100, 1) if limit > 0 else None
                result["rate_limit"] = {
                    "limit": limit,
                    "remaining": remaining,
                    "used": used,
                    "remaining_pct": remaining_pct,
                    "reset_at": datetime.fromtimestamp(reset, timezone.utc).isoformat() if reset > 0 else None,
                }
                result["status"] = "WATCH" if limit > 0 and remaining_pct is not None and remaining_pct < 10 else "OK"
            except (json.JSONDecodeError, TypeError, ValueError, OverflowError):
                result["status"] = "DEGRADED"
        else:
            # Only pay for the secondary auth probe when the API probe fails. This
            # distinguishes missing/invalid auth from transient API reachability loss.
            auth: subprocess.CompletedProcess[str] | None = None
            try:
                auth = _run_process(
                    [gh, "auth", "status", "--active", "--hostname", "github.com"],
                    text=True,
                    capture_output=True,
                    timeout=BOOTSTRAP_GITHUB_AUTH_FALLBACK_TIMEOUT_SECONDS,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            result["authenticated"] = bool(auth is not None and auth.returncode == 0)
            result["status"] = "DEGRADED" if result["authenticated"] else "UNAVAILABLE"

    cache_max_age = (
        BOOTSTRAP_GITHUB_CACHE_SECONDS
        if result["status"] in {"OK", "WATCH"}
        else BOOTSTRAP_GITHUB_FAILURE_CACHE_SECONDS
    )
    result["cache"] = {"used": False, "age_seconds": 0.0, "max_age_seconds": cache_max_age}
    result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    cache_payload = dict(result)
    cache_payload.pop("cache", None)
    cache_payload.pop("latency_ms", None)
    _bootstrap_cache_write("github-status.json", cache_payload)
    return result


def _git_blob_sha_for_file(path: Path) -> str | None:
    try:
        data = path.read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        return None
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _remaining_bootstrap_git_timeout(deadline: float | None = None) -> float | None:
    if deadline is None:
        return BOOTSTRAP_GIT_COMMAND_TIMEOUT_SECONDS
    remaining = deadline - time.monotonic()
    if remaining <= 0.01:
        return None
    return min(BOOTSTRAP_GIT_COMMAND_TIMEOUT_SECONDS, remaining)


def _git_last_committed_at(repo_root: Path, relative_path: str, *, deadline: float | None = None) -> str | None:
    git = shutil.which("git")
    timeout = _remaining_bootstrap_git_timeout(deadline)
    if not git or timeout is None:
        return None
    try:
        proc = _run_process(
            [git, "-C", str(repo_root), "log", "-1", "--format=%cI", "--", relative_path],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = proc.stdout.strip() if proc.returncode == 0 else ""
    return value or None


def _git_checkout_state(
    repo_root: Path,
    remote_main: Any,
    expected_branch: str = "main",
    *,
    deadline: float | None = None,
) -> dict[str, Any]:
    """Bounded local serving-checkout coherence; never fetches or reads policy bodies."""
    git = shutil.which("git")
    remote_head = str(remote_main or "").strip() or None
    result: dict[str, Any] = {
        "available": False,
        "branch": None,
        "local_head": None,
        "remote_main": remote_head,
        "head_matches_remote_main": False,
        "local_tracking_main": None,
        "head_matches_local_tracking_main": False,
        "cached_remote_is_ancestor_of_local": False,
        "remote_metadata_lags_local_tracking": False,
        "coherence_basis": "unavailable",
        "dirty": None,
        "coherent": False,
    }
    timeout = _remaining_bootstrap_git_timeout(deadline)
    if not git or timeout is None:
        if git and timeout is None:
            result["coherence_basis"] = "git_budget_exhausted"
        return result
    try:
        proc = _run_process(
            [git, "-C", str(repo_root), "status", "--porcelain=v2", "--branch", "--untracked-files=normal"],
            text=True, capture_output=True, timeout=timeout,
        )
    except OSError:
        return result
    except subprocess.TimeoutExpired:
        result["coherence_basis"] = "git_probe_timeout"
        return result
    if proc.returncode != 0:
        return result
    branch = None
    local_head = None
    dirty = False
    for raw_line in proc.stdout.splitlines():
        if raw_line.startswith("# branch.oid "):
            value = raw_line[len("# branch.oid "):].strip()
            local_head = value if value and value != "(initial)" else None
        elif raw_line.startswith("# branch.head "):
            value = raw_line[len("# branch.head "):].strip()
            branch = value or None
        elif raw_line and not raw_line.startswith("# "):
            dirty = True

    tracking_head = None
    timeout = _remaining_bootstrap_git_timeout(deadline)
    if timeout is not None:
        try:
            tracking_proc = _run_process(
                [git, "-C", str(repo_root), "rev-parse", "--verify", f"refs/remotes/origin/{expected_branch}"],
                text=True, capture_output=True, timeout=timeout,
            )
            if tracking_proc.returncode == 0:
                tracking_head = tracking_proc.stdout.strip() or None
        except (OSError, subprocess.TimeoutExpired):
            tracking_head = None

    exact_head = bool(local_head and remote_head and local_head == remote_head)
    cached_remote_is_ancestor = exact_head
    remote_relation_known = exact_head
    if local_head and remote_head and not exact_head:
        timeout = _remaining_bootstrap_git_timeout(deadline)
        if timeout is not None:
            try:
                ancestor_proc = _run_process(
                    [git, "-C", str(repo_root), "merge-base", "--is-ancestor", remote_head, local_head],
                    text=True, capture_output=True, timeout=timeout,
                )
                cached_remote_is_ancestor = ancestor_proc.returncode == 0
                remote_relation_known = True
            except (OSError, subprocess.TimeoutExpired):
                cached_remote_is_ancestor = False
                remote_relation_known = False

    tracking_matches = bool(local_head and tracking_head and local_head == tracking_head)
    metadata_lags_tracking = bool(tracking_matches and cached_remote_is_ancestor and not exact_head)
    if tracking_head:
        coherent_head = bool(tracking_matches and cached_remote_is_ancestor)
    else:
        # Without a local canonical tracking ref, only exact cached metadata is enough evidence.
        coherent_head = exact_head
    coherent = bool(coherent_head and branch == expected_branch and not dirty)
    if coherent:
        coherence_basis = "cached_remote_exact" if exact_head else "local_tracking_descends_cached_remote"
    elif branch != expected_branch:
        coherence_basis = "wrong_branch"
    elif dirty:
        coherence_basis = "dirty"
    elif tracking_head and not tracking_matches:
        coherence_basis = "local_head_differs_tracking_main"
    elif remote_head and remote_relation_known and not cached_remote_is_ancestor:
        coherence_basis = "cached_remote_not_ancestor"
    else:
        coherence_basis = "remote_relation_unknown"
    result.update({
        "available": bool(local_head),
        "branch": branch,
        "local_head": local_head,
        "head_matches_remote_main": exact_head,
        "local_tracking_main": tracking_head,
        "head_matches_local_tracking_main": tracking_matches,
        "cached_remote_is_ancestor_of_local": cached_remote_is_ancestor,
        "remote_metadata_lags_local_tracking": metadata_lags_tracking,
        "coherence_basis": coherence_basis,
        "dirty": dirty,
        "coherent": coherent,
    })
    return result


def _git_remote_update_already_applied(
    repo_root: Path,
    relative_path: str,
    remote_commit: Any,
    *,
    deadline: float | None = None,
) -> bool:
    """Detect a fetched remote file delta already present in a locally divergent working file."""
    git = shutil.which("git")
    commit = str(remote_commit or "").strip()
    if not git or not commit:
        return False
    try:
        timeout = _remaining_bootstrap_git_timeout(deadline)
        if timeout is None:
            return False
        exists = _run_process(
            [git, "-C", str(repo_root), "cat-file", "-e", f"{commit}^{{commit}}"],
            text=True, capture_output=True, timeout=timeout,
        )
        if exists.returncode != 0:
            return False
        timeout = _remaining_bootstrap_git_timeout(deadline)
        if timeout is None:
            return False
        base_proc = _run_process(
            [git, "-C", str(repo_root), "merge-base", "HEAD", commit],
            text=True, capture_output=True, timeout=timeout,
        )
        base = base_proc.stdout.strip() if base_proc.returncode == 0 else ""
        if not base:
            return False
        timeout = _remaining_bootstrap_git_timeout(deadline)
        if timeout is None:
            return False
        patch_proc = _run_process(
            [git, "-C", str(repo_root), "diff", "--no-ext-diff", "--unified=0", base, commit, "--", relative_path],
            capture_output=True, timeout=timeout,
        )
        if patch_proc.returncode != 0:
            return False
        if not patch_proc.stdout:
            return True
        timeout = _remaining_bootstrap_git_timeout(deadline)
        if timeout is None:
            return False
        reverse_check = _run_process(
            [git, "-C", str(repo_root), "apply", "--reverse", "--check", "--unidiff-zero", "--whitespace=nowarn"],
            input=patch_proc.stdout, capture_output=True, timeout=timeout,
        )
        return reverse_check.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _remote_is_newer(remote_at: Any, local_at: Any) -> bool:
    if not isinstance(remote_at, str) or not remote_at.strip() or not isinstance(local_at, str) or not local_at.strip():
        return False
    try:
        remote_dt = datetime.fromisoformat(remote_at.replace("Z", "+00:00"))
        local_dt = datetime.fromisoformat(local_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    return remote_dt > local_dt


def _bootstrap_source_freshness() -> dict[str, Any]:
    """Compact freshness signal for behavior sources; hashes only, no body parsing."""
    cached_raw, cache_age = _bootstrap_cache_read_any("source-freshness.json")
    cached, stale_while_refresh = _bootstrap_cache_refresh_view(
        "source-freshness.json", cached_raw, cache_age,
        max_age_seconds=BOOTSTRAP_SOURCE_FRESHNESS_CACHE_SECONDS, lease_seconds=4.0,
    )
    remote: dict[str, Any] | None = cached if isinstance(cached, dict) else None
    if remote is not None:
        checkout_meta = remote.get("canonical_agents_checkout")
        if not isinstance(checkout_meta, dict) or not str(checkout_meta.get("remote_main") or "").strip():
            remote = None
    cache_used = remote is not None
    if remote is None:
        gh = shutil.which("gh")
        if not gh:
            return {"available": False, "attention_required": True, "reason": "gh_unavailable"}
        query = (
            'query {'
            ' agents: repository(owner:"organicoverlords", name:"agents") {'
            '  ref(qualifiedName:"refs/heads/main") { target { ... on Commit {'
            '   oid'
            '   agentsHistory: history(first:1, path:"AGENTS.md") { nodes { oid committedDate } }'
            '   rulesHistory: history(first:1, path:"RULES.md") { nodes { oid committedDate } }'
            '  } } }'
            '  agentsBlob: object(expression:"main:AGENTS.md") { ... on Blob { oid } }'
            '  rulesBlob: object(expression:"main:RULES.md") { ... on Blob { oid } }'
            ' }'
            ' vault: repository(owner:"organicoverlords", name:"regression-research") {'
            '  ref(qualifiedName:"refs/heads/main") { target { ... on Commit {'
            '   workerHistory: history(first:1, path:"04 Operating Contracts/fresh-worker-generation-launch.md") { nodes { oid committedDate } }'
            '  } } }'
            '  workerBlob: object(expression:"main:04 Operating Contracts/fresh-worker-generation-launch.md") { ... on Blob { oid } }'
            ' }'
            '}'
        )
        try:
            proc = _run_process(
                [gh, "api", "graphql", "-f", f"query={query}"],
                text=True,
                capture_output=True,
                timeout=BOOTSTRAP_GITHUB_API_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            proc = None
        if proc is None or proc.returncode != 0:
            return {"available": False, "attention_required": True, "reason": "github_metadata_unavailable"}
        try:
            payload = json.loads(proc.stdout)
            data = payload.get("data", {})
            agents = data.get("agents", {})
            vault_repo = data.get("vault", {})
            agent_target = ((agents.get("ref") or {}).get("target") or {})
            vault_target = ((vault_repo.get("ref") or {}).get("target") or {})

            def first_history(target: dict[str, Any], key: str) -> dict[str, Any]:
                nodes = ((target.get(key) or {}).get("nodes") or [])
                return nodes[0] if nodes and isinstance(nodes[0], dict) else {}

            remote = {
                "canonical_agents_checkout": {"remote_main": agent_target.get("oid")},
                "AGENTS.md": {
                    "remote_blob": (agents.get("agentsBlob") or {}).get("oid"),
                    "last_updated_at": first_history(agent_target, "agentsHistory").get("committedDate"),
                    "last_update_commit": first_history(agent_target, "agentsHistory").get("oid"),
                },
                "RULES.md": {
                    "remote_blob": (agents.get("rulesBlob") or {}).get("oid"),
                    "last_updated_at": first_history(agent_target, "rulesHistory").get("committedDate"),
                    "last_update_commit": first_history(agent_target, "rulesHistory").get("oid"),
                },
                "worker_report_contract": {
                    "remote_blob": (vault_repo.get("workerBlob") or {}).get("oid"),
                    "last_updated_at": first_history(vault_target, "workerHistory").get("committedDate"),
                    "last_update_commit": first_history(vault_target, "workerHistory").get("oid"),
                },
            }
            _bootstrap_cache_write("source-freshness.json", remote)
            cache_age = 0.0
        except (json.JSONDecodeError, AttributeError, TypeError):
            return {"available": False, "attention_required": True, "reason": "github_metadata_invalid"}

    git_deadline = time.monotonic() + BOOTSTRAP_SOURCE_FRESHNESS_LOCAL_GIT_BUDGET_SECONDS
    checkout_remote = dict((remote or {}).get("canonical_agents_checkout") or {})
    canonical_checkout = _git_checkout_state(
        Path(AGENT_RULES_ROOT), checkout_remote.get("remote_main"), deadline=git_deadline
    )

    local_sources = {
        "AGENTS.md": (Path(AGENT_RULES_ROOT) / "AGENTS.md", Path(AGENT_RULES_ROOT), "AGENTS.md"),
        "RULES.md": (Path(AGENT_RULES_ROOT) / "RULES.md", Path(AGENT_RULES_ROOT), "RULES.md"),
        "worker_report_contract": (
            ROOT / "04 Operating Contracts" / "fresh-worker-generation-launch.md",
            ROOT,
            "04 Operating Contracts/fresh-worker-generation-launch.md",
        ),
    }
    sources: dict[str, Any] = {}
    checkout_incoherent = not bool(canonical_checkout.get("coherent"))
    attention = checkout_incoherent
    any_updates_pending = checkout_incoherent
    for key, (path, repo_root, relative_path) in local_sources.items():
        item = dict((remote or {}).get(key) or {})
        local_blob = _git_blob_sha_for_file(path)
        remote_blob = item.pop("remote_blob", None)
        matches = bool(local_blob and remote_blob and local_blob == remote_blob)
        local_last_committed_at = _git_last_committed_at(repo_root, relative_path, deadline=git_deadline)
        remote_newer = (not matches) and _remote_is_newer(item.get("last_updated_at"), local_last_committed_at)
        remote_update_already_applied = remote_newer and _git_remote_update_already_applied(
            repo_root, relative_path, item.get("last_update_commit"), deadline=git_deadline
        )
        updates_pending = remote_newer and not remote_update_already_applied
        sources[key] = {
            "last_updated_at": item.get("last_updated_at"),
            "updates_pending": updates_pending,
            **({"remote_update_already_applied": True} if remote_update_already_applied else {}),
        }
        attention = attention or not matches
        any_updates_pending = any_updates_pending or updates_pending
    return {
        "available": True,
        "attention_required": attention,
        "updates_pending": any_updates_pending,
        "canonical_checkout": canonical_checkout,
        "sources": sources,
        "cache": {
            "used": cache_used,
            "age_seconds": round(float(cache_age or 0.0), 3),
            "max_age_seconds": BOOTSTRAP_SOURCE_FRESHNESS_CACHE_SECONDS,
            **({"stale_while_refresh": True} if stale_while_refresh else {}),
        },
    }


def _bootstrap_mcp_from_live_swarm(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compatibility bootstrap MCP projection from the MCPv4-backed live-swarm evidence."""
    if not isinstance(snapshot, dict) or not snapshot.get("available"):
        return {"available": False, "status": "MISSING", "active_session_count": 0, "active_sessions": [], "workspace_counts": {}}
    evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), dict) else {}
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    complete = bool(evidence.get("activity_window_complete", evidence.get("observation_window_complete")))
    sessions = []
    for lane in snapshot.get("lanes", []) if isinstance(snapshot.get("lanes"), list) else []:
        if not isinstance(lane, dict): continue
        owners = [str(item.get("owner")) for item in lane.get("busy", []) if isinstance(item, dict) and item.get("owner")]
        worktree = lane.get("worktree") if isinstance(lane.get("worktree"), dict) else {}
        for caller in lane.get("callers", []) if isinstance(lane.get("callers"), list) else []:
            if not isinstance(caller, dict): continue
            sessions.append({
                "caller_id": caller.get("caller_id"),
                "activity_age_seconds": caller.get("last_activity_age_seconds"),
                "cwd": worktree.get("path"),
                "workspace": caller.get("workspace"),
                "mode": caller.get("mode"),
                "action_class": caller.get("action_class"),
                "activity_target": caller.get("activity_target"),
                "busy_titles": owners,
            })
    sessions.sort(key=lambda item: float(item.get("activity_age_seconds") or 1e9))
    activity = evidence.get("activity_summary") if isinstance(evidence.get("activity_summary"), dict) else {}
    return {
        "available": True,
        "status": "LIVE" if float(evidence.get("source_age_seconds") or 0) <= 60 else "STALE",
        "source_age_seconds": evidence.get("source_age_seconds"),
        "transport": evidence.get("transport"),
        "transport_source_count": evidence.get("transport_source_count"),
        "service_health": {"available": None, "status": "NOT_PROBED_FRESH_TRANSPORT"},
        "activity_evidence_status": "FRESH" if complete else "BOUNDED",
        "active_session_count": int(summary.get("recent_callers") or 0),
        "active_session_count_status": "COMPLETE" if complete else "LOWER_BOUND",
        "active_session_count_semantics": MCP_ACTIVE_SESSION_COUNT_SEMANTICS,
        "active_sessions": sessions[:BOOTSTRAP_ACTIVE_SESSION_DETAIL_LIMIT],
        "active_session_details": {
            "policy": "most_recent",
            "limit": BOOTSTRAP_ACTIVE_SESSION_DETAIL_LIMIT,
            "returned": min(len(sessions), BOOTSTRAP_ACTIVE_SESSION_DETAIL_LIMIT),
            "total": len(sessions),
            "bounded": len(sessions) > BOOTSTRAP_ACTIVE_SESSION_DETAIL_LIMIT,
            "semantics": "bootstrap_detail_bound_not_evidence_truncation",
        },
        "workspace_counts": summary.get("workspace_counts", {}),
        "caller_modes": summary.get("caller_modes", {}),
        "activity_buckets": summary.get("activity_buckets", {}),
        "activity_summary": {
            **activity,
            "activity_window_seconds": 300,
            "activity_window_complete": complete,
        },
    }

_SHARED_CONTRACT_VERSION_RE = re.compile(r"(?m)^Shared contract version:\s*([1-9][0-9]*)\s*$")


def _bootstrap_agent_contract_version(agent_rules_root: Path | str = AGENT_RULES_ROOT) -> dict[str, Any]:
    """Read the logical shared-contract version from the serving RULES/AGENTS pair."""
    root = Path(agent_rules_root)

    def read_one(name: str) -> int | None:
        path = root / name
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        matches = _SHARED_CONTRACT_VERSION_RE.findall(text)
        return int(matches[0]) if len(matches) == 1 else None

    rules_version = read_one("RULES.md")
    agents_version = read_one("AGENTS.md")
    if rules_version is not None and agents_version is not None and rules_version == agents_version:
        return {"status": "COHERENT", "version": rules_version, "rules_version": rules_version, "agents_version": agents_version}
    if rules_version is None or agents_version is None:
        return {"status": "MISSING", "version": None, "rules_version": rules_version, "agents_version": agents_version}
    return {"status": "MISMATCH", "version": None, "rules_version": rules_version, "agents_version": agents_version}


_SLOPWALL_V2_RULES_INVARIANTS = {
    "investigation": "response/task-quality regression investigation",
    "failed_boundary": "Treat the immediately preceding assistant reply/action or repair attempt as the failed boundary",
    "guidance": "which governing user/system/shared rules or evidence were loaded or otherwise available",
    "divergence": "the first supported divergence",
    "classification": "rule violation, rule missed/not loaded, rule gap/conflict, authority selection, or ordinary reasoning/action selection",
    "diagnosis": "Expose a bounded useful diagnosis to the user",
    "repair": "materially answer/execute the inherited objective better",
    "durability": "incident record, replay fixture, bounded score/confidence",
    "memory_contract": "searchable memory pointer, and behavior-contract review",
    "capture": "Capture is visible-context only",
    "no_backfill": "never load, reconstruct, export, or backfill the whole conversation",
    "incident_report": "`incident report`, when the user uses it as a command about the preceding assistant/system failure, starts the **same V2 behavior-incident loop**",
    "meta_not_trigger": "A meta-reference or question about the phrase `incident report` is not a trigger",
}
_SLOPWALL_V2_AGENTS_INVARIANTS = {
    "loop": "explicit `slopwall` and command-form `incident report` enter the V2 behavior-incident loop",
    "failed_boundary": "first establish the immediately preceding failed reply/action/repair as the failure boundary",
    "diagnosis": "Give the user the bounded useful diagnosis",
    "repair": "then materially repair/resume the inherited objective",
    "durability": "incident record/report, replay fixture, bounded score/confidence or `UNSCORABLE`",
    "capture": "Raw capture is `VISIBLE_CONTEXT_ONLY`",
    "no_backfill": "Never load/reconstruct/backfill the whole conversation just to complete an incident",
    "retrigger": "If another corrective trigger arrives before closure, make the failed repair a linked child event",
}

# Temporary rollout compatibility: Vault can land before the shared V2 rules without
# degrading bootstrap or projecting semantics that are not yet canonical.
_SLOPWALL_LEGACY_RULES_INVARIANTS = {
    "incident": "`slopwall` is a **mandatory correction-and-learning incident**",
    "reread": "re-read this canonical Slopwall rule and the matching AGENTS.md correction owner before finalizing the correction",
    "compare": "compare the failed reply/action directly against the inherited objective",
    "lost_core": "identify the concrete core proposition, decision, action, or evidence the user needed foregrounded",
    "displacement": "identify what displaced that core",
    "mechanism": "infer the best-supported mechanism or decision failure",
    "lesson": "derive one reusable prevention lesson",
    "durability": "persist one compact durable correction",
    "mandatory": "The durable correction is mandatory for literal `slopwall`",
    "lost_core_record": "The durable correction must name the lost core and the displacement",
    "not_length": "A slopwall is not defined by length",
}
_SLOPWALL_LEGACY_AGENTS_INVARIANTS = {
    "learning_loop": "literal `slopwall` additionally requires a bounded durable learning loop",
    "reread": "re-read the canonical Slopwall rule plus this correction owner",
    "lost_core": "identify the lost core proposition/decision/action/evidence and what displaced it",
    "record": "The Slopwall record is mandatory",
    "specific": "do not store merely `be concise`, `answer better`",
    "uncertainty": "bounded uncertainty instead of fabricating a root cause",
    "inherit": "after durability is secured, continue or finish the inherited task",
}


def _missing_behavior_invariants(rules: str, agents: str, rules_invariants: dict[str, str], agents_invariants: dict[str, str]) -> list[str]:
    return [
        *(f"RULES:{key}" for key, phrase in rules_invariants.items() if phrase not in rules),
        *(f"AGENTS:{key}" for key, phrase in agents_invariants.items() if phrase not in agents),
    ]


def _bootstrap_slopwall_contract(agent_rules_root: Path | str = AGENT_RULES_ROOT) -> dict[str, Any]:
    """Project only the behavior-incident semantics actually present in serving shared rules."""
    root = Path(agent_rules_root)
    try:
        rules = (root / "RULES.md").read_text(encoding="utf-8")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    except OSError:
        return {"status": "MISSING", "trigger": "behavior_incident", "missing": ["serving_rules_unreadable"]}

    v2_missing = _missing_behavior_invariants(rules, agents, _SLOPWALL_V2_RULES_INVARIANTS, _SLOPWALL_V2_AGENTS_INVARIANTS)
    if not v2_missing:
        return {
            "status": "ENFORCED",
            "version": "V2",
            "triggers": ["slopwall", "incident_report"],
            "capture": "VISIBLE_CONTEXT_ONLY + verbatim + no_full_conversation_reload_or_backfill",
            "process": "failed_boundary > inspect_governing_guidance_and_evidence > supported_failure_class > bounded_user_visible_diagnosis > repair_inherited_objective > persist_incident_replay_score_memory_contract_review; repeated_trigger_links_failed_repair",
        }

    legacy_missing = _missing_behavior_invariants(rules, agents, _SLOPWALL_LEGACY_RULES_INVARIANTS, _SLOPWALL_LEGACY_AGENTS_INVARIANTS)
    if not legacy_missing:
        return {
            "status": "ENFORCED",
            "version": "LEGACY_V84",
            "triggers": ["slopwall"],
            "process": "reread_canonical_rule > compare_failed_answer_to_objective > recover_lost_core > identify_displacement > best_supported_mechanism > condition/action_prevention > repair_task > mandatory_durable_correction; not brevity/apology",
            "transition": "legacy accepted only until serving shared rules expose the V2 behavior-incident contract",
        }

    v2_rules_missing = [
        f"RULES:{key}" for key, phrase in _SLOPWALL_V2_RULES_INVARIANTS.items() if phrase not in rules
    ]
    legacy_rules_missing = [
        f"RULES:{key}" for key, phrase in _SLOPWALL_LEGACY_RULES_INVARIANTS.items() if phrase not in rules
    ]
    if not v2_rules_missing:
        return {
            "status": "DRIFTED",
            "version": "V2",
            "missing": v2_missing,
            "legacy_missing": legacy_missing,
        }
    if not legacy_rules_missing:
        return {
            "status": "DRIFTED",
            "version": "LEGACY_V84",
            "missing": legacy_missing,
            "v2_missing": v2_missing,
        }
    return {
        "status": "DRIFTED",
        "version": "UNKNOWN",
        "missing": v2_missing,
        "legacy_missing": legacy_missing,
    }


def _bootstrap_critical_guidance(agent_rules_root: Path | str = AGENT_RULES_ROOT) -> dict[str, Any]:
    """Project compact hints that follow the behavior contract actually present in serving shared rules."""
    root = Path(agent_rules_root)
    try:
        rules = (root / "RULES.md").read_text(encoding="utf-8")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    except OSError:
        return {"mode": "UNAVAILABLE", "missing": ["serving_rules_unreadable"]}

    v2_active = not _missing_behavior_invariants(rules, agents, _SLOPWALL_V2_RULES_INVARIANTS, _SLOPWALL_V2_AGENTS_INVARIANTS)
    guidance = {
        "mode": "HINT_ONLY",
        "behavior_incident_version": "V2" if v2_active else "LEGACY_V84",
        "eli5": "fact/live truth/error/next action; keep material data/constraints/uncertainty; strip jargon/process; no analogy unless asked | RULES:ELI5",
        "asshole": "corrected result first; no apology/self-analysis/process substitute | RULES/AGENTS:asshole; then mandatory lightweight marker",
        "stack_find": "unknown owner/WIP/runtime/history => one decision-relevant unknown; no guess/fanout | AGENTS:stack/MCP/infra; find once; narrow same unknown once if noisy; use resolved owner",
        "shared_correction": "shared/swarm correction: RULE_GAP vs RULE_VIOLATION; no 'this chat/from now on' promise; claim fixed only after durable canonical proof; if infra/orchestration/scheduler intent is still being shaped, discuss first/no mutation | RULES:shared-behavior-correction + swarm-direction",
        "security_evidence": {
            "mode": "CLASSIFY_BEFORE_CAUSALITY",
            "source": "RULES:platform-security-boundary",
            "classes": {
                "platform_security_reroute": "user report or preserved platform evidence",
                "tool_policy_rejection": "tool invocation rejected before MCP dispatch",
                "mcp_transport_failure": "connector/MCP transport failure such as HTTP 5xx",
                "process_execution": "local process receipt/outcome only",
            },
            "non_equivalence": [
                "tool_policy_rejection != platform_security_reroute",
                "mcp_transport_failure != platform_security_reroute",
                "process_execution != platform_security_reroute",
            ],
            "causality_gate": "Cross-class causality requires explicit correlated evidence; a shared log path/name is not a classification.",
        },
    }
    if v2_active:
        guidance.update({
            "slopwall": "failed boundary first; inspect governing guidance/evidence and classify supported failure; bounded diagnosis > repair inherited objective > incident/replay/score/memory/contract review; capture visible context verbatim only, never reload/backfill whole chat; repeated corrective trigger links the failed repair | RULES:slopwall + AGENTS:correction",
            "incident_report": "command-form trigger uses the same V2 loop even when failure is not Slopwall; meta-reference is not a trigger; visible-context-only verbatim capture; no unrelated mutation authority | RULES:incident report + AGENTS:correction",
        })
    else:
        guidance.update({
            "slopwall": "keep inherited objective/core foregrounded; no filler/process/proxy displacement | RULES:slopwall + AGENTS:correction; repair first; mandatory correction before final",
            "incident_report": "not a canonical trigger under the currently serving legacy behavior contract; do not infer V2 semantics before shared rules land",
        })
    return guidance


def build_live_bootstrap_glance() -> dict[str, Any]:
    """Single compact factual session bootstrap."""
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=9) as pool:
        f_execution_nodes = pool.submit(_bootstrap_execution_node_topology)
        f_pc = pool.submit(_bootstrap_pc_status)
        f_workers = pool.submit(_bootstrap_worker_status)
        f_live_swarm = pool.submit(build_live_swarm_snapshot)
        f_memory = pool.submit(_bootstrap_memory_overview)
        f_vault = pool.submit(_bootstrap_vault_status)
        f_github = pool.submit(_bootstrap_github_status)
        f_source_freshness = pool.submit(_bootstrap_source_freshness)
        f_yard_messages = pool.submit(_yard_inbox_check)
        execution_nodes, pc, workers, live_swarm, memory_overview, vault, github, source_freshness, yard_messages = (
            f_execution_nodes.result(), f_pc.result(), f_workers.result(), f_live_swarm.result(), f_memory.result(), f_vault.result(), f_github.result(), f_source_freshness.result(), f_yard_messages.result()
        )
    pc = _bind_pc_node_identity(pc, execution_nodes)
    bootstrap_now = datetime.now(timezone.utc)
    manual_current = _bootstrap_manual_current_status(bootstrap_now)
    swarm_topology = _bootstrap_swarm_topology(bootstrap_now, manual_current=manual_current)
    if isinstance(swarm_topology, dict):
        swarm_topology["execution_nodes"] = execution_nodes
    mcp = _bootstrap_mcp_status_from_live_swarm(live_swarm)
    mcp_current_topology = _bootstrap_mcp_current_topology()
    mcp_recovery_state = _bootstrap_mcp_recovery_orientation(_bootstrap_mcp_recovery_state())
    agent_contract = _bootstrap_agent_contract_version()
    slopwall_contract = _bootstrap_slopwall_contract()
    critical_guidance = _bootstrap_critical_guidance()
    notable_conditions: list[str] = []
    if agent_contract["status"] != "COHERENT":
        notable_conditions.append(f"agent_contract_version_{str(agent_contract['status']).casefold()}")
    if slopwall_contract["status"] != "ENFORCED":
        notable_conditions.append(f"slopwall_contract_{str(slopwall_contract['status']).casefold()}")
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
    worker_glance = {
        key: workers.get(key) for key in (
            "available", "generated_at", "read_mode", "population_scope", "evidence_semantics",
            "archive_sample", "attention", "stale_reports", "manual_sanity",
        ) if key in workers
    } if isinstance(workers, dict) else workers
    if isinstance(worker_glance, dict):
        sanity = worker_glance.get("manual_sanity")
        if isinstance(sanity, dict):
            worker_glance["manual_sanity"] = {
                key: sanity.get(key)
                for key in ("available", "status", "score_delta", "direction", "post_run_count")
                if key in sanity
            }
        live_summary = live_swarm.get("summary") if isinstance(live_swarm, dict) and isinstance(live_swarm.get("summary"), dict) else {}
        live_evidence = live_swarm.get("evidence") if isinstance(live_swarm, dict) and isinstance(live_swarm.get("evidence"), dict) else {}
        worker_glance["current_activity"] = {
            "authority": "live_swarm_runtime_evidence",
            "population_scope": "unified_recurring_and_manual_on_demand_activity",
            "recent_callers": live_summary.get("recent_callers"),
            "lanes": live_summary.get("lanes"),
            "busy_owners": live_summary.get("busy_owners"),
            "activity_window_seconds": live_evidence.get("activity_window_seconds"),
            "observation_window_complete": live_evidence.get("observation_window_complete"),
            "source_age_seconds": live_evidence.get("source_age_seconds"),
            "identity": live_summary.get("identity"),
        }
        manual_live_identity = _bootstrap_active_manual_run_identities(manual_current, live_swarm)
        if manual_live_identity.get("runs"):
            worker_glance["current_activity"]["manual_run"] = manual_live_identity["runs"][0]

    mcp_health = "OK" if isinstance(mcp, dict) and mcp.get("available") and mcp.get("status") == "LIVE" else "DEGRADED"
    vault_health = str(vault.get("status") or "UNAVAILABLE") if isinstance(vault, dict) else "UNAVAILABLE"
    github_health = str(github.get("status") or "UNAVAILABLE") if isinstance(github, dict) else "UNAVAILABLE"
    if mcp_health != "OK":
        notable_conditions.append(f"mcp_{mcp_health.casefold()}")
    if vault_health != "OK":
        notable_conditions.append(f"vault_{vault_health.casefold()}")
    if github_health != "OK":
        notable_conditions.append(f"github_{github_health.casefold()}")
    timeline_materialized = memory_overview.get("timeline_materialized", {}) if isinstance(memory_overview, dict) else {}
    if isinstance(timeline_materialized, dict):
        timeline_status = str(timeline_materialized.get("status") or "").upper()
        if timeline_status and timeline_status != "FRESH":
            notable_conditions.append(f"timeline_materialization_{timeline_status.casefold()}")
        incomplete = [str(value) for value in timeline_materialized.get("backfill_incomplete_sources", []) if str(value).strip()]
        if incomplete:
            notable_conditions.append("timeline_history_incomplete_" + "_".join(sorted(incomplete)))
        retry = [str(value) for value in timeline_materialized.get("retry_sources", []) if str(value).strip()]
        if retry:
            notable_conditions.append("timeline_delta_retry_" + "_".join(sorted(retry)))
        if timeline_materialized.get("timeline_truncated"):
            notable_conditions.append("timeline_materialized_event_cap_truncated")

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    bootstrap_status = "OK" if (
        mcp_health == vault_health == github_health == "OK"
        and agent_contract["status"] == "COHERENT"
        and slopwall_contract["status"] == "ENFORCED"
    ) else "DEGRADED"
    if elapsed_ms >= 5000:
        notable_conditions.append(f"bootstrap_slow_{round(elapsed_ms)}ms")
    bootstrap = {
        "status": bootstrap_status,
        "self_check": "OK" if (ROOT / "tools" / "stack_atlas.py").is_file() else "DEGRADED",
        "elapsed_ms": elapsed_ms,
        "bounded_contract": "no_git_fetch_or_github_issue_pr_listing_or_busy_enumeration",
        "agent_contract": agent_contract,
        "slopwall_contract": slopwall_contract,
        "critical_guidance": critical_guidance,
        "visual_acceptance": {
            "status": "HARD_GATE",
            "rule": "Inspect the exact candidate pixels/frames before visual success or user handoff.",
            "metrics": "Metrics/logs/tests/file existence/hashes/point counts/reprojection error are supporting only and never substitute for pixel inspection.",
            "failure": "Visible defect => REJECTED/NOT_PROVEN; unavailable pixels/frames => UNKNOWN/NOT_PROVEN.",
            "source": r"C:\Users\Lauri\.agents\RULES.md",
        },
    }
    glance = {
        "schema": "bootstrap.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paths": {
            "bootstrap": str(ROOT / "tools" / "stack_atlas.py"),
            "rules": r"C:\Users\Lauri\.agents\RULES.md",
            "agents": r"C:\Users\Lauri\.agents\AGENTS.md",
            "issue_first_work_intake": r"C:\Users\Lauri\.agents\RULES.md",
            "vault": str(ROOT),
            "worker_reports": str(ROOT / "worker-reports"),
            "p3": r"C:\Users\Lauri\Documents\Unreal Projects\p3",
            "tiny3d": r"C:\Users\Lauri\Desktop\tiny3d",
            "lowvram": r"C:\Users\Lauri\Desktop\lowvram3d-repo",
            "tiny3d_library": r"C:\Users\Lauri\Desktop\Tiny3D_LIBRARY",
            "mcp": MCP_HOME_DIRECT_RUNTIME_ROOT,
            "mcp_source_repo": r"%LOCALAPPDATA%\ChatGPTMcpClean",
            "mcp_current_topology": str(MCP_CURRENT_TOPOLOGY_PATH),
            "mcp_recovery_state": str(MCP_RECOVERY_STATE_PATH),
            "mcp_security_routing_log": str(MCP_SECURITY_ROUTING_LOG_PATH),
            "execution_node_topology": str(ATLAS_LIVE_ROOT / EXECUTION_NODE_TOPOLOGY_RELATIVE_PATH),
        },
        "swarm_topology": swarm_topology,
        "commands": {
            "bootstrap": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py bootstrap-glance",
            "live_swarm": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py live-swarm",
            "fleet_watch": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py fleet-watch --worker-id <own-automation-id>",
            "stack_owner": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py lookup <id-or-alias>",
            "stack_find": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py find <query>",
            "tiny3d_asset_library": "lookup tiny3d_library",
            "process_blast_radius": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py blast-radius --pid <pid>",
            "production_change_gate": r"python C:\Users\Lauri\Desktop\vault\tools\stack_atlas.py production-change-gate <component> --actor <actor> --busy-scope <exact-scope>",
            "cleanup_converge": r"python C:\Users\Lauri\Desktop\vault\tools\cleanup_converger.py --apply --operator-ack",
            "memory_overview": r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py overview",
            "memory_context": r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py context <query>",
            "memory_timeline": r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py timeline <query>",
            "timeline_refresh": r"python C:\Users\Lauri\Desktop\vault\tools\timeline_materializer.py refresh",
            "timeline_task_status": r"python C:\Users\Lauri\Desktop\vault\tools\timeline_materializer.py task-status",
        },
        "bootstrap": bootstrap,
        "live_swarm": compact_for_bootstrap(live_swarm, lane_limit=4),
        "mcp": mcp,
        "vault": vault,
        "github": github,
        "source_freshness": source_freshness,
        "yard_messages": yard_messages,
        "pc": pc,
        "workers": worker_glance,
        "mcp_current_topology": mcp_current_topology,
        "mcp_recovery_state": mcp_recovery_state,
        "memory_overview": memory_overview,
    }
    return _fit_bootstrap_glance_budget(glance)


def _bootstrap_worker_activity_from_mcp(mcp: dict[str, Any] | Any) -> dict[str, Any]:
    """Current execution activity from MCP/runtime evidence only; never from reports."""
    if not isinstance(mcp, dict):
        return {"authority": "live_mcp_runtime_evidence", "status": "UNAVAILABLE"}
    activity_status = str(mcp.get("activity_evidence_status") or "")
    if not activity_status:
        activity_status = "FRESH" if mcp.get("active_session_count_status") == "COMPLETE" else "PARTIAL"
    return {
        "authority": "live_mcp_runtime_evidence",
        "status": activity_status,
        "observed_session_count": int(mcp.get("active_session_count") or 0),
        "observed_session_count_status": mcp.get("active_session_count_status"),
        "workspace_counts": mcp.get("workspace_counts", {}),
        "session_details": mcp.get("active_session_details"),
    }


FEATURE_LOOKUP_ALIASES = {
    "nexus": "project.nexus_navigation",
    "devboard": "project.nexus_navigation",
    "dev progress board": "project.nexus_navigation",
    "tiny3d_library": "project.tiny3d_asset_library",
    "tiny3d library": "project.tiny3d_asset_library",
    "asset_catalogue": "project.tiny3d_asset_library",
    "asset catalogue": "project.tiny3d_asset_library",
    "showroom": "project.tiny3d_asset_library",
    "visual_proof_library": "project.tiny3d_asset_library",
    "visual proof library": "project.tiny3d_asset_library",
    "p3_visual_evidence": "project.p3_visual_evidence",
    "p3 visual evidence": "project.p3_visual_evidence",
    "p3_proof_library": "project.p3_visual_evidence",
    "p3 proof library": "project.p3_visual_evidence",
    "shared_visual_library": "project.shared_visual_library_integration",
    "shared visual library": "project.shared_visual_library_integration",
    "chatgpt_visual_library": "project.shared_visual_library_integration",
    "chatgpt visual library": "project.shared_visual_library_integration",
    "shared_chat_proof": "project.shared_visual_library_integration",
    "shared chat proof": "project.shared_visual_library_integration",
    "12-view": "project.shared_visual_library_integration",
    "12 view": "project.shared_visual_library_integration",
    "turnaround sheet": "project.shared_visual_library_integration",
    "multiview sheet": "project.shared_visual_library_integration",
    "standardized 12-view": "project.shared_visual_library_integration",
    "standardized 12 views": "project.shared_visual_library_integration",
    "canonical 12-view set": "project.shared_visual_library_integration",
    "review contact sheet": "project.shared_visual_library_integration",
}


def _mcp_component_current_topology_projection() -> dict[str, Any]:
    current = _bootstrap_mcp_current_topology()
    source = current.get("details_path") or current.get("path") or str(MCP_CURRENT_TOPOLOGY_PATH)
    if not current.get("available") or current.get("read_state") != "OK":
        result: dict[str, Any] = {
            "status": "UNKNOWN_SOURCE_UNAVAILABLE",
            "authority": "CURRENT_TOPOLOGY_UNAVAILABLE",
            "source": source,
            "read_state": current.get("read_state"),
            "boundary": "Fail closed: static Atlas metadata must not masquerade as current MCP serving topology when mcp-current-topology.v1 is missing or invalid.",
        }
        if current.get("error"):
            result["error"] = current.get("error")
        return result
    serving_path = current.get("serving_path")
    if isinstance(serving_path, list):
        serving_path = " -> ".join(str(item) for item in serving_path if item is not None)
    return {
        "status": "OK",
        "authority": current.get("authority"),
        "source": source,
        "connector_url": current.get("connector_url"),
        "public_origin": current.get("public_origin"),
        "authorization_endpoint": current.get("authorization_endpoint"),
        "serving_path": serving_path,
        "independent_local_control": current.get("independent_local_control"),
        "excluded_from_gpt1_path": current.get("not_in_gpt1_path"),
    }


def component_details(name: str) -> dict[str, Any]:
    requested = name
    name = COMPONENT_ALIASES.get(name.casefold(), name)
    if name in COMPONENTS:
        spec = dict(COMPONENTS[name])
        if name == "mcp_minimal_clone":
            spec["current_topology"] = _mcp_component_current_topology_projection()
        return {"id": name, "requested_as": requested, **spec, "authority": ATLAS_CONTRACT["authority"]}
    raise KeyError(requested)


def _tiny3d_lookup_projection(query: str) -> dict[str, Any]:
    """Attach bounded current Tiny3D evidence without turning Atlas into product authority."""
    try:
        return project_tiny3d_current(query, TINY3D_LIBRARY, limit=8)
    except (OSError, ValueError) as exc:
        return {
            "schema": "stack-atlas.tiny3d-current.v1",
            "authority": "READ_ONLY_MATERIALIZED_TINY3D_ORIENTATION",
            "query": query,
            "status": "UNKNOWN_SOURCE_UNAVAILABLE",
            "error": str(exc),
            "boundary": "Fail closed: no current asset/proof claim is made when bounded materialized sources cannot be validated.",
        }


def _runtime_graph_for_components_safe(component_ids: Iterable[str]) -> dict[str, Any]:
    """Load deployment-graph code only for lookup/find so bootstrap-glance has no new runtime import."""
    try:
        from tools.runtime_dependency_graph import runtime_graph_for_components
    except ModuleNotFoundError:
        try:
            from runtime_dependency_graph import runtime_graph_for_components
        except ModuleNotFoundError as exc:
            return {
                "schema": "stack-atlas.runtime-deployment-graph.v1",
                "authority": "DERIVED_DEPLOYMENT_NAVIGATION",
                "surfaces": [],
                "coverage": {"status": "UNAVAILABLE", "error": str(exc)},
            }
    return runtime_graph_for_components(component_ids, root=ATLAS_LIVE_ROOT)


def _runtime_graph_search_safe(query: str, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fail-soft bounded runtime/deployment discovery; no broad scheduler enumeration."""
    try:
        from tools.runtime_dependency_graph import search_runtime_dependency_graph
    except ModuleNotFoundError:
        try:
            from runtime_dependency_graph import search_runtime_dependency_graph
        except ModuleNotFoundError as exc:
            return [], {
                "status": "UNAVAILABLE",
                "authority": "DERIVED_DEPLOYMENT_NAVIGATION",
                "error": str(exc),
                "network_fanout": False,
                "broad_task_enumeration": False,
            }
    return search_runtime_dependency_graph(query, root=ATLAS_LIVE_ROOT, limit=limit)


def _runtime_graph_explain_safe(term: str, surface_id: str | None = None) -> dict[str, Any]:
    """Bounded runtime/deployment node explanation with ambiguity-explicit resolution."""
    try:
        from tools.runtime_dependency_graph import explain_runtime_dependency_node
    except ModuleNotFoundError:
        try:
            from runtime_dependency_graph import explain_runtime_dependency_node
        except ModuleNotFoundError as exc:
            return {
                "schema": "stack-atlas.runtime-explain.v1",
                "status": "UNAVAILABLE",
                "query": term,
                "coverage": {"status": "UNAVAILABLE", "error": str(exc)},
            }
    return explain_runtime_dependency_node(term, root=ATLAS_LIVE_ROOT, surface_id=surface_id)


def _runtime_graph_path_safe(source: str, target: str, surface_id: str | None = None) -> dict[str, Any]:
    """Bounded deterministic directed path over the runtime/deployment graph."""
    try:
        from tools.runtime_dependency_graph import runtime_dependency_path
    except ModuleNotFoundError:
        try:
            from runtime_dependency_graph import runtime_dependency_path
        except ModuleNotFoundError as exc:
            return {
                "schema": "stack-atlas.runtime-path.v1",
                "status": "UNAVAILABLE",
                "source_query": source,
                "target_query": target,
                "coverage": {"status": "UNAVAILABLE", "error": str(exc)},
            }
    return runtime_dependency_path(source, target, root=ATLAS_LIVE_ROOT, surface_id=surface_id)


def atlas_lookup(name: str, *, query: str | None = None) -> dict[str, Any]:
    """Resolve a stack component or exact feature target, optionally with bounded Tiny3D evidence."""
    requested = name
    try:
        result = component_details(name)
    except KeyError:
        feature_id = FEATURE_LOOKUP_ALIASES.get(name.casefold(), name)
        if feature_id not in FEATURE_INDEX:
            raise KeyError(requested)
        result = {
            "id": feature_id,
            "requested_as": requested,
            "kind": "feature_navigation",
            **FEATURE_INDEX[feature_id],
            "authority": ATLAS_CONTRACT["authority"],
        }
    if query is not None:
        query = query.strip()
        if not query:
            raise ValueError("lookup --query must not be empty")
        if result.get("id") != "project.tiny3d_asset_library":
            raise ValueError("lookup --query is supported only for tiny3d_library/asset catalogue/showroom targets")
        result = dict(result)
        result["current_projection"] = _tiny3d_lookup_projection(query)

    component_ids = [result["id"]] if result.get("id") in COMPONENTS else list(result.get("owner_components") or [])
    runtime_graph = _runtime_graph_for_components_safe(component_ids)
    if runtime_graph.get("surfaces"):
        result = dict(result)
        result["runtime_graph"] = runtime_graph
    return result


def _busy_scope_status(scope: str) -> dict[str, Any]:
    try:
        proc = _run_process([BUSY_CMD, "inspect", scope], text=True, capture_output=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "scope": scope, "error": str(exc)}
    if proc.returncode != 0:
        return {"available": False, "scope": scope, "returncode": proc.returncode, "stderr": proc.stderr.strip()}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"available": False, "scope": scope, "error": "invalid BusyCoordinator JSON"}
    return {"available": True, "scope": scope, "job": payload.get("job"), "claim": payload.get("claim")}


def production_change_gate(
    target: str,
    *,
    actor: str,
    busy_scope: str,
    explicit_user_authorization: bool = False,
    routine_scoped_advance: bool = False,
    independent_rollback_verified: bool = False,
    offpath_proof_verified: bool = False,
    mcp_status: dict[str, Any] | None = None,
    busy_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    requested = target
    component = COMPONENT_ALIASES.get(target.casefold(), target)
    reasons: list[str] = []
    warnings: list[str] = []

    if component not in COMPONENTS:
        reasons.append("unknown_target_component")
    elif component not in SHARED_PRODUCTION_COMPONENTS:
        reasons.append("target_not_classified_shared_production")

    scope_authorization_source = (
        "EXPLICIT_USER" if explicit_user_authorization else ("ROUTINE_SCOPED_ADVANCE" if routine_scoped_advance else None)
    )
    if scope_authorization_source is None:
        reasons.append("missing_live_production_scope_basis")
    if not independent_rollback_verified:
        reasons.append("independent_rollback_control_route_not_verified")
    if not offpath_proof_verified:
        reasons.append("offpath_canary_proof_not_verified")

    busy = busy_status if busy_status is not None else _busy_scope_status(busy_scope)
    if not busy.get("available"):
        reasons.append("busy_scope_evidence_unavailable")
    else:
        claim = busy.get("claim") or {}
        claimant = str(claim.get("actor") or "")
        if not claimant:
            reasons.append("busy_scope_not_claimed")
        elif claimant != actor:
            reasons.append("busy_scope_claimed_by_other_actor")

    dependencies: dict[str, Any] = {}
    if component in MCP_SHARED_PRODUCTION_COMPONENTS:
        mcp = mcp_status if mcp_status is not None else _bootstrap_mcp_from_live_swarm(build_live_swarm_snapshot())
        dependencies["mcp"] = {
            "available": bool(mcp.get("available")),
            "status": mcp.get("status"),
            "active_session_count": int(mcp.get("active_session_count") or 0),
            "active_session_count_status": mcp.get("active_session_count_status"),
            "active_session_count_semantics": mcp.get("active_session_count_semantics"),
            "active_sessions": mcp.get("active_sessions", []),
            "authority": "live_swarm_runtime_evidence" if mcp_status is None else mcp.get("authority"),
            "transport": mcp.get("transport"),
            "transport_source_count": mcp.get("transport_source_count"),
        }
        if not mcp.get("available") or mcp.get("status") != "LIVE" or mcp.get("active_session_count_status") != "COMPLETE":
            reasons.append("mcp_dependency_evidence_incomplete")
        elif int(mcp.get("active_session_count") or 0) > 0:
            warnings.append("recent_mcp_activity_present")

    return {
        "schema": "production-change-gate.v1",
        "target": {
            "requested": requested,
            "component": component if component in COMPONENTS else None,
            "shared_production": component in SHARED_PRODUCTION_COMPONENTS,
        },
        "actor": actor,
        "busy_scope": busy_scope,
        "checks": {
            "explicit_user_authorization_for_specific_live_change": bool(explicit_user_authorization),
            "routine_scoped_reversible_advance": bool(routine_scoped_advance),
            "scope_authorization_source": scope_authorization_source,
            "independent_rollback_control_route_verified": bool(independent_rollback_verified),
            "offpath_canary_proof_verified": bool(offpath_proof_verified),
            "busy_scope": busy,
        },
        "live_dependencies": dependencies,
        "warnings": warnings,
        "reasons": reasons,
        "verdict": "PASS" if not reasons else "BLOCK",
        "semantics": {
            "routine_scoped_advance_does_not_require_redundant_user_approval": True,
            "scope_widening_or_destructive_change_requires_explicit_user_authorization": True,
            "busy_claim_is_collision_control_not_authorization": True,
            "pass_is_necessary_not_sufficient_authority": True,
        },
    }


FEATURE_QUERY_STOPWORDS = frozenset({
    "a", "an", "and", "are", "ask", "asking", "better", "do", "does", "for", "how", "i", "is",
    "it", "library", "make", "me", "more", "my", "never", "of", "please", "should", "that", "the", "this", "to",
    "what", "with", "work", "working", "works",
})
FEATURE_QUERY_SYNONYMS: dict[str, set[str]] = {
    "automatic": {"aggregate", "aggregation", "overview", "digest"},
    "automatically": {"aggregate", "aggregation", "overview", "digest"},
    "aggregate": {"aggregation", "overview", "digest", "summary"},
    "aggregation": {"aggregate", "overview", "digest", "summary"},
    "discover": {"find", "navigation", "search", "owner"},
    "navigate": {"navigation", "find", "search", "owner"},
    "navigation": {"navigate", "find", "search", "owner"},
    "useful": {"usefulness", "overview", "digest", "summary", "aggregate"},
    "usefulness": {"useful", "overview", "digest", "summary", "aggregate"},
    "where": {"find", "navigation", "owner"},
}


def _shared_query_concepts(query: str) -> list[set[str]]:
    try:
        from tools.timeline_materializer import _query_concepts
    except ImportError:
        try:
            from timeline_materializer import _query_concepts
        except ImportError:
            _query_concepts = None
    if _query_concepts is not None:
        return [set(concept) for concept in _query_concepts(query)]
    concepts: list[set[str]] = []
    for raw in re.findall(r"[a-z0-9åäö]+", query.casefold()):
        if raw in FEATURE_QUERY_STOPWORDS:
            continue
        variants = {raw}
        if len(raw) > 4 and raw.endswith("ies"):
            variants.add(raw[:-3] + "y")
        elif len(raw) > 4 and raw.endswith("s") and not raw.endswith("ss"):
            variants.add(raw[:-1])
        concepts.append(variants)
    return concepts


def _feature_query_terms(query: str) -> tuple[list[str], set[str]]:
    base = [
        term for term in re.findall(r"[a-z0-9åäö]+", query.casefold())
        if term and term not in FEATURE_QUERY_STOPWORDS
    ]
    expanded = set(base)
    for term in base:
        expanded.update(FEATURE_QUERY_SYNONYMS.get(term, set()))
    for concept in _shared_query_concepts(query):
        if concept & FEATURE_QUERY_STOPWORDS:
            continue
        expanded.update(concept)
    return base, expanded


def find_features(query: str, limit: int = 5) -> list[dict[str, Any]]:
    base_terms, expanded_terms = _feature_query_terms(query)
    if not base_terms:
        return []
    normalized_query = " ".join(base_terms)
    exact_feature_trigger = (
        any(
            " ".join(re.findall(r"[a-z0-9]+", feature_id.casefold())) == normalized_query
            for feature_id in FEATURE_INDEX
        )
        or any(
            " ".join(re.findall(r"[a-z0-9]+", trigger.casefold())) == normalized_query
            for spec in FEATURE_INDEX.values()
            for trigger in spec["triggers"]
        )
    )
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for feature_id, spec in FEATURE_INDEX.items():
        semantic = " ".join([feature_id, *spec["owner_components"], *spec["triggers"]]).casefold()
        detail = " ".join([*spec["entrypoints"], spec["boundary"]]).casefold()
        semantic_tokens = set(re.findall(r"[a-z0-9]+", semantic))
        detail_tokens = set(re.findall(r"[a-z0-9]+", detail))
        base_semantic = set(base_terms) & semantic_tokens
        base_detail = set(base_terms) & detail_tokens
        expanded_semantic = expanded_terms & semantic_tokens
        trigger_bonus = sum(4 for trigger in spec["triggers"] if trigger.casefold() in normalized_query)
        if not base_semantic and not expanded_semantic and not trigger_bonus:
            continue
        covered = sum(
            1 for term in base_terms
            if term in semantic_tokens or term in detail_tokens or any(term in trigger.casefold() for trigger in spec["triggers"])
        )
        score = (
            6 * len(base_semantic)
            + 2 * len(expanded_semantic - base_semantic)
            + len(base_detail)
            + trigger_bonus
            + 3 * covered
        )
        ranked.append((score, feature_id, {"id": feature_id, **spec, "authority": ATLAS_CONTRACT["authority"]}))

    # Natural-language `find` is also a component locator. Fill remaining slots with
    # direct component matches so callers do not need to know whether a concept was
    # modeled as a feature or a component before asking Atlas.
    for component_id, spec in COMPONENTS.items():
        semantic = " ".join([
            component_id,
            str(spec.get("role") or ""),
            *spec.get("capabilities", []),
            *spec.get("resources", []),
        ]).casefold()
        semantic_tokens = set(re.findall(r"[a-z0-9]+", semantic))
        base_matches = set(base_terms) & semantic_tokens
        expanded_matches = expanded_terms & semantic_tokens
        if not base_matches and not expanded_matches:
            continue
        if len(base_terms) > 1 and len(base_matches) < 2:
            continue
        full_component_match = len(base_matches) == len(set(base_terms))
        score = 5 * len(base_matches) + len(expanded_matches - base_matches) + (20 if full_component_match and not exact_feature_trigger else 0)
        ranked.append((
            score,
            f"component.{component_id}",
            {
                "id": f"component.{component_id}",
                "owner_components": [component_id],
                "triggers": [component_id, str(spec.get("role") or "")],
                "entrypoints": [f"python tools\\stack_atlas.py lookup {component_id}", *spec.get("canonical_sources", [])[:3]],
                "boundary": "Direct component match. Use Atlas lookup for bounded owner details, then leave Atlas and work at that owner.",
                "authority": ATLAS_CONTRACT["authority"],
            },
        ))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    for _, result_id, result in ranked:
        if result_id in seen:
            continue
        seen.add(result_id)
        results.append(result)
        if len(results) >= max(1, limit):
            break
    return results


DISCOVERY_SCHEMA = "stack-atlas.discovery.v1"
DISCOVERY_AUTHORITY = "DISCOVERY_NAVIGATION_ONLY_NOT_CURRENT_TRUTH"
_TIMELINE_QUERY_INDEX_SCHEMA = "vault.timeline.query-index.v1"
_TIMELINE_WEIGHT_CODE = {1: 0.7, 2: 1.2, 3: 2.0, 4: 2.2, 5: 4.0}
_DISCOVERY_SOURCE_BONUS = {
    "mcp_event": 7.0,
    "github_issue": 6.0,
    "github_pr": 5.5,
    "github_action": 5.0,
    "tracked_artifact": 5.0,
    "runner_log": 4.8,
    "local_artifact": 4.5,
    "library_artifact": 4.5,
    "git_commit": 3.0,
    "machine_observation": 2.0,
    "vault_memory": 2.0,
    "worker_report": 1.0,
    "coordinator_event": 0.5,
}


def _discovery_root() -> Path:
    override = os.environ.get("STACK_ATLAS_DISCOVERY_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    live_state = ATLAS_LIVE_ROOT / ".state" / "timeline"
    if live_state.is_dir():
        return ATLAS_LIVE_ROOT
    return ROOT


def _discovery_query_terms(query: str) -> list[set[str]]:
    return _shared_query_concepts(query)


def _minimum_discovery_matches(concept_count: int) -> int:
    if concept_count <= 1:
        return 1
    if concept_count <= 4:
        return 2
    if concept_count <= 7:
        return 3
    return 4


def _history_discovery_identity(
    event_id: str,
    anchors: list[str],
    source_type: str | None = None,
) -> tuple[str, str, str] | None:
    match = re.match(r"^github-issue:([^#]+)#(\d+):", event_id)
    if match:
        ref = f"{match.group(1)}#{match.group(2)}"
        return "github_issue", f"github_issue:{ref.casefold()}", ref
    match = re.match(r"^github-pr:([^#]+)#(\d+):", event_id)
    if match:
        ref = f"{match.group(1)}#{match.group(2)}"
        return "github_pr", f"github_pr:{ref.casefold()}", ref
    match = re.match(r"^git:([^:]+):([0-9a-fA-F]{7,64})$", event_id)
    if match:
        project, sha = match.groups()
        ref = f"{project}@{sha[:12]}"
        return "git_commit", f"git_commit:{project.casefold()}:{sha.casefold()}", ref
    match = re.match(r"^artifact:[^:]+:(.+)$", event_id)
    if match:
        path = match.group(1)
        return "tracked_artifact", f"artifact:{path.casefold()}", path
    match = re.match(r"^local-artifact:(.+):\d+(?:\.\d+)?$", event_id)
    if match:
        path = match.group(1)
        return "local_artifact", f"artifact:{path.casefold()}", path
    match = re.match(r"^library-artifact:(.+)$", event_id)
    if match:
        ref = match.group(1)
        return "library_artifact", f"library_artifact:{ref.casefold()}", ref
    if event_id.startswith("mem-"):
        return "vault_memory", f"vault_memory:{event_id.casefold()}", event_id
    if event_id.startswith("worker:"):
        return "worker_report", f"worker_report:{event_id.casefold()}", event_id

    source_kind = {
        "MCP_EVENT": "mcp_event",
        "GITHUB_ACTION": "github_action",
        "GITHUB_ACTION_SUMMARY": "github_action_summary",
        "RUNNER_LOG": "runner_log",
        "MACHINE_OBSERVATION": "machine_observation",
        "COORDINATOR_EVENT": "coordinator_event",
    }.get(str(source_type or "").upper())
    if source_kind:
        return source_kind, f"{source_kind}:{event_id.casefold()}", event_id

    for anchor in anchors:
        match = re.match(r"^github:([^#]+)#(\d+)$", str(anchor))
        if match:
            ref = f"{match.group(1)}#{match.group(2)}"
            return "github_ref", f"github_ref:{ref.casefold()}", ref
    if source_type:
        generic_kind = re.sub(r"[^a-z0-9]+", "_", str(source_type).casefold()).strip("_") or "history_event"
        return generic_kind, f"{generic_kind}:{event_id.casefold()}", event_id
    return None


def _discovery_event_timestamp(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def _timeline_discovery_hits(query: str, limit: int = 5, *, root: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    root = root or _discovery_root()
    try:
        from .timeline_materializer import timeline_read_state_root
    except ImportError:
        from timeline_materializer import timeline_read_state_root
    state = timeline_read_state_root(root)
    status_path = state / "status.json"
    index_path = state / "timeline-query-index.pkl"
    coverage: dict[str, Any] = {
        "authority": "DERIVED_MATERIALIZED_HISTORY_ONLY",
        "read_mode": "MATERIALIZED_QUERY_INDEX_ONLY",
        "root": str(root),
        "network_fanout": False,
        "live_truth_required": True,
    }
    try:
        status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        with index_path.open("rb") as handle:
            index = pickle.load(handle)
    except (OSError, json.JSONDecodeError, EOFError, pickle.PickleError, AttributeError, ValueError) as exc:
        coverage.update({"status": "UNAVAILABLE", "error": str(exc)})
        coverage["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return [], coverage
    generated_at = str(status.get("generated_at") or "")
    if (
        not isinstance(index, dict)
        or index.get("schema") != _TIMELINE_QUERY_INDEX_SCHEMA
        or str(index.get("generated_at") or "") != generated_at
        or not isinstance(index.get("ids"), list)
        or not isinstance(index.get("postings"), dict)
        or not isinstance(index.get("weight_codes"), dict)
        or not isinstance(index.get("anchors"), list)
        or len(index["ids"]) != len(index["anchors"])
        or (index.get("branch_refs") is not None and (not isinstance(index.get("branch_refs"), list) or len(index["ids"]) != len(index["branch_refs"])))
        or (index.get("event_meta") is not None and (not isinstance(index.get("event_meta"), list) or len(index["ids"]) != len(index["event_meta"])))
    ):
        coverage.update({"status": "INVALID_OR_STALE_INDEX", "generated_at": generated_at})
        coverage["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return [], coverage

    normalized_query = str(query).casefold()
    explicit_issue_numbers = set(re.findall(r"\bissue\s*#?\s*(\d+)\b", normalized_query))
    explicit_pr_numbers = set(re.findall(r"\b(?:pr|pull\s+request)\s*#?\s*(\d+)\b", normalized_query))
    explicit_worker_hashes = set(re.findall(r"(?<![0-9a-f])([0-9a-f]{64})(?![0-9a-f])", normalized_query))
    exact_worker_ids = {f"worker:{value}" for value in explicit_worker_hashes}
    explicit_memory_ids = set(re.findall(r"\b(mem-\d{8}-[a-z0-9]{8,})\b", normalized_query))
    concepts = _discovery_query_terms(query)
    if not concepts:
        coverage.update({"status": "OK", "generated_at": generated_at, "candidate_count": 0})
        coverage["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return [], coverage
    ids = index["ids"]
    postings = index["postings"]
    weight_codes = index["weight_codes"]
    anchors_by_position = index["anchors"]
    branch_refs_by_position = index.get("branch_refs") if isinstance(index.get("branch_refs"), list) else [[] for _ in ids]
    event_meta_by_position = index.get("event_meta") if isinstance(index.get("event_meta"), list) else [{} for _ in ids]
    opaque_labels = index.get("opaque_labels") if isinstance(index.get("opaque_labels"), dict) else {}
    best_by_concept: list[dict[int, float]] = []
    exact_worker_positions = {
        position for position, event_id in enumerate(ids) if str(event_id) in exact_worker_ids
    }
    exact_memory_positions = {
        position for position, event_id in enumerate(ids) if str(event_id).casefold() in explicit_memory_ids
    }
    exact_identity_positions = exact_worker_positions | exact_memory_positions
    candidate_positions: set[int] = set(exact_identity_positions)
    for concept in concepts:
        best: dict[int, float] = {}
        for token in concept:
            rows = postings.get(token)
            codes = weight_codes.get(token)
            if not isinstance(rows, list) or not isinstance(codes, (bytes, bytearray)) or len(rows) != len(codes):
                continue
            for position, code in zip(rows, codes):
                if not isinstance(position, int) or position < 0 or position >= len(ids):
                    continue
                weight = _TIMELINE_WEIGHT_CODE.get(int(code), 0.0)
                if weight > best.get(position, 0.0):
                    best[position] = weight
        candidate_positions.update(best)
        best_by_concept.append(best)

    minimum_matches = _minimum_discovery_matches(len(concepts))
    ranked: list[tuple[float, str, str, str, list[str], int]] = []
    label_by_stable_key: dict[str, str] = {}
    branches_by_stable_key: dict[str, list[str]] = {}
    meta_by_stable_key: dict[str, dict[str, Any]] = {}
    for position in candidate_positions:
        matched = sum(1 for weights in best_by_concept if weights.get(position, 0.0) > 0.0)
        exact_worker_match = position in exact_worker_positions
        exact_memory_match = position in exact_memory_positions
        exact_identity_match = exact_worker_match or exact_memory_match
        if matched < minimum_matches and not exact_identity_match:
            continue
        event_id = str(ids[position])
        anchors = [str(value) for value in (anchors_by_position[position] or []) if str(value).strip()][:24]
        meta = event_meta_by_position[position] if isinstance(event_meta_by_position[position], dict) else {}
        identity = _history_discovery_identity(event_id, anchors, str(meta.get("source_type") or ""))
        if identity is None:
            continue
        kind, stable_key, reference = identity
        opaque_label = str(opaque_labels.get(event_id) or meta.get("title") or "").strip()
        if opaque_label and stable_key not in label_by_stable_key:
            label_by_stable_key[stable_key] = opaque_label
        if stable_key not in meta_by_stable_key:
            meta_by_stable_key[stable_key] = meta
        branch_refs = [str(value) for value in (branch_refs_by_position[position] or []) if str(value).strip()]
        if branch_refs and stable_key not in branches_by_stable_key:
            branches_by_stable_key[stable_key] = branch_refs[:12]
        score = sum(weights.get(position, 0.0) for weights in best_by_concept)
        if exact_identity_match:
            score += 100.0
        score += _DISCOVERY_SOURCE_BONUS.get(kind, 0.0)
        score += matched / max(1, len(concepts))
        identity_text = ""
        if kind in {"github_issue", "github_pr"}:
            identity_text = reference.rsplit("#", 1)[0]
        elif kind == "git_commit":
            identity_text = reference.split("@", 1)[0]
        else:
            identity_text = str(meta.get("project") or "")
        identity_tokens = set(re.findall(r"[a-z0-9]+", identity_text.casefold()))
        score += 4.0 * sum(1 for concept in concepts if identity_tokens & concept)
        reference_number = reference.rsplit("#", 1)[-1] if "#" in reference else ""
        if kind == "github_issue" and reference_number in explicit_issue_numbers:
            score += 25.0
        if kind == "github_pr" and reference_number in explicit_pr_numbers:
            score += 25.0
        ranked.append((score, stable_key, kind, reference, anchors, position))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    effective_limit = max(1, int(limit))
    selected_rows: list[tuple[float, str, str, str, list[str], int]] = []
    selected_keys: set[str] = set()
    selected_kinds: set[str] = set()
    # Show different evidence classes before filling with multiple members from one class.
    for row in ranked:
        _, stable_key, kind, _, _, _ = row
        if stable_key in selected_keys or kind in selected_kinds:
            continue
        selected_rows.append(row)
        selected_keys.add(stable_key)
        selected_kinds.add(kind)
        if len(selected_rows) >= effective_limit:
            break
    if len(selected_rows) < effective_limit:
        for row in ranked:
            stable_key = row[1]
            if stable_key in selected_keys:
                continue
            selected_rows.append(row)
            selected_keys.add(stable_key)
            if len(selected_rows) >= effective_limit:
                break

    def render_position(position: int, *, relationship: str | None = None, time_delta_seconds: float | None = None, shared_anchors: list[str] | None = None) -> dict[str, Any] | None:
        event_id = str(ids[position])
        anchors = [str(value) for value in (anchors_by_position[position] or []) if str(value).strip()][:24]
        meta = event_meta_by_position[position] if isinstance(event_meta_by_position[position], dict) else {}
        identity = _history_discovery_identity(event_id, anchors, str(meta.get("source_type") or ""))
        if identity is None:
            return None
        kind, _, reference = identity
        item: dict[str, Any] = {
            "kind": kind,
            "reference": reference,
            "source_type": meta.get("source_type"),
            "event_at": meta.get("event_at"),
            "project": meta.get("project"),
            "source_authority": meta.get("authority"),
        }
        title = str(meta.get("title") or opaque_labels.get(event_id) or "").strip()
        if title:
            item["label"] = title
        if meta.get("summary"):
            item["summary"] = meta.get("summary")
        branches = [str(value) for value in (branch_refs_by_position[position] or []) if str(value).strip()]
        if branches:
            item["branches"] = branches[:12]
        details = meta.get("details") if isinstance(meta.get("details"), dict) else {}
        if details:
            item["details"] = details
        if relationship:
            item["relationship"] = relationship
        if time_delta_seconds is not None:
            item["time_delta_seconds"] = round(time_delta_seconds, 3)
        if shared_anchors:
            item["shared_anchors"] = shared_anchors[:8]
        return item

    hits: list[dict[str, Any]] = []
    for score, stable_key, kind, reference, anchors, position in selected_rows:
        meta = meta_by_stable_key.get(stable_key, {})
        hit = {
            "kind": kind,
            "reference": reference,
            "authority": "DERIVED_MATERIALIZED_HISTORY_ONLY",
            "live_truth_required": True,
            "score": round(score, 3),
        }
        if label_by_stable_key.get(stable_key):
            hit["label"] = label_by_stable_key[stable_key]
        if branches_by_stable_key.get(stable_key):
            hit["branches"] = branches_by_stable_key[stable_key]
        if anchors:
            hit["anchors"] = anchors[:8]
        for key in ("source_type", "event_at", "project", "authority", "summary"):
            value = meta.get(key)
            if value not in (None, "", [], {}):
                hit["source_authority" if key == "authority" else key] = value
        details = meta.get("details") if isinstance(meta.get("details"), dict) else {}
        if details:
            hit["details"] = details
        hits.append(hit)

    # Evidence windows are correlation/navigation only. They deliberately expose nearby
    # runtime/Git/GitHub/CI/worker evidence without asserting that all members are one job.
    evidence_clusters: list[dict[str, Any]] = []
    source_priority = {
        "MCP_EVENT": 0,
        "GIT_COMMIT": 1,
        "GITHUB_ISSUE": 2,
        "GITHUB_PR": 2,
        "GITHUB_ACTION": 3,
        "RUNNER_LOG": 4,
        "WORKER_REPORT": 5,
        "TRACKED_ARTIFACT": 6,
        "LOCAL_ARTIFACT": 6,
        "LIBRARY_ARTIFACT": 6,
        "MACHINE_OBSERVATION": 7,
        "COORDINATOR_EVENT": 8,
    }
    for _, _, seed_kind, seed_reference, seed_anchors, seed_position in selected_rows[:3]:
        seed_meta = event_meta_by_position[seed_position] if isinstance(event_meta_by_position[seed_position], dict) else {}
        seed_project = str(seed_meta.get("project") or "")
        seed_ts = _discovery_event_timestamp(seed_meta.get("event_at"))
        seed_anchor_set = set(seed_anchors)
        related_by_key: dict[str, tuple[tuple[int, float, str], int, str, float | None, list[str]]] = {}
        for position, raw_meta in enumerate(event_meta_by_position):
            if position == seed_position or not isinstance(raw_meta, dict):
                continue
            event_id = str(ids[position])
            anchors = [str(value) for value in (anchors_by_position[position] or []) if str(value).strip()]
            identity = _history_discovery_identity(event_id, anchors, str(raw_meta.get("source_type") or ""))
            if identity is None:
                continue
            kind, stable_key, _ = identity
            shared = sorted(seed_anchor_set & set(anchors))
            candidate_ts = _discovery_event_timestamp(raw_meta.get("event_at"))
            delta = abs(seed_ts - candidate_ts) if seed_ts is not None and candidate_ts is not None else None
            same_project = bool(seed_project and seed_project == str(raw_meta.get("project") or ""))
            if shared:
                relationship = "shared_anchor"
                relation_rank = 0
            elif same_project and delta is not None and delta <= 180.0:
                relationship = "same_project_time_window"
                relation_rank = 1
            else:
                continue
            priority = source_priority.get(str(raw_meta.get("source_type") or ""), 9)
            rank_key = (relation_rank, delta if delta is not None else 10**9, f"{priority}:{stable_key}")
            prior = related_by_key.get(stable_key)
            if prior is None or rank_key < prior[0]:
                related_by_key[stable_key] = (rank_key, position, relationship, delta, shared)
        related_rows = sorted(related_by_key.values(), key=lambda row: (row[0][0], source_priority.get(str((event_meta_by_position[row[1]] or {}).get("source_type") or ""), 9), row[0][1], row[0][2]))
        selected_related: list[tuple[tuple[int, float, str], int, str, float | None, list[str]]] = []
        seen_types: set[str] = set()
        for row in related_rows:
            source_type = str((event_meta_by_position[row[1]] or {}).get("source_type") or "")
            if source_type in seen_types:
                continue
            selected_related.append(row)
            seen_types.add(source_type)
            if len(selected_related) >= 8:
                break
        if len(selected_related) < 12:
            for row in related_rows:
                if row in selected_related:
                    continue
                selected_related.append(row)
                if len(selected_related) >= 12:
                    break
        seed_member = render_position(seed_position, relationship="seed")
        members = [seed_member] if seed_member else []
        for _, position, relationship, delta, shared in selected_related:
            rendered = render_position(position, relationship=relationship, time_delta_seconds=delta, shared_anchors=shared)
            if rendered:
                members.append(rendered)
        if len(members) > 1:
            evidence_clusters.append({
                "authority": "SEARCH_CORRELATION_ONLY_NOT_SHARED_TRUTH",
                "seed_kind": seed_kind,
                "seed_reference": seed_reference,
                "project": seed_project or None,
                "time_window_seconds": 180,
                "members": members,
            })

    materialized_memory_ids = {str(event_id).casefold() for event_id in ids if str(event_id).startswith("mem-")}
    missing_memory_ids = sorted(explicit_memory_ids - materialized_memory_ids)
    if missing_memory_ids:
        referenced_by = [
            {"kind": hit.get("kind"), "reference": hit.get("reference"), "score": hit.get("score")}
            for hit in hits[:8]
        ]
        reference_only_hits = [
            {
                "kind": "referenced_identity",
                "identity_kind": "vault_memory",
                "reference": memory_id,
                "authority": "SEARCH_REFERENCE_ONLY_NOT_OBJECT_TRUTH",
                "materialized_object_present": False,
                "note": "Exact memory identity is referenced by materialized evidence but is not present as a current materialized memory object.",
                "referenced_by": referenced_by,
                "score": 150.0,
            }
            for memory_id in missing_memory_ids
        ]
        hits = [*reference_only_hits, *hits][:effective_limit]

    source_latest_at: dict[str, str] = {}
    for meta in event_meta_by_position:
        if not isinstance(meta, dict):
            continue
        source_type = str(meta.get("source_type") or "")
        event_at = str(meta.get("event_at") or "")
        if source_type and event_at and event_at > source_latest_at.get(source_type, ""):
            source_latest_at[source_type] = event_at
    coverage.update({
        "status": "OK",
        "generated_at": generated_at,
        "candidate_count": len(candidate_positions),
        "matching_identity_count": len({row[1] for row in ranked}),
        "events": status.get("events"),
        "truncated": bool(status.get("truncated")),
        "saturated_sources": list(status.get("saturated_sources") or []),
        "source_latest_at": dict(sorted(source_latest_at.items())),
        "evidence_cluster_semantics": "SEARCH_CORRELATION_ONLY_NOT_SHARED_TRUTH",
        "evidence_clusters": evidence_clusters,
    })
    coverage["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return hits, coverage


def _live_discovery_hits(query: str, limit: int = 5, *, snapshot: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    try:
        snapshot = snapshot if snapshot is not None else build_live_swarm_snapshot()
    except (OSError, ValueError, TypeError) as exc:
        return [], {
            "status": "UNAVAILABLE",
            "authority": "MIXED_LIVE_SWARM_NAVIGATION_EVIDENCE",
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    if not isinstance(snapshot, dict) or not snapshot.get("available"):
        return [], {
            "status": "UNAVAILABLE",
            "authority": "MIXED_LIVE_SWARM_NAVIGATION_EVIDENCE",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    hits = _search_live_swarm(
        snapshot, query, limit=max(1, int(limit)), query_concepts=_shared_query_concepts(query)
    )
    evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), dict) else {}
    return hits, {
        "status": "OK",
        "authority": "MIXED_LIVE_SWARM_NAVIGATION_EVIDENCE",
        "busy_semantics": "coordination_handoff_only_not_worker_liveness_or_progress",
        "caller_semantics": "live_mcp_runtime_activity_within_snapshot_window",
        "source_age_seconds": evidence.get("source_age_seconds"),
        "busy_source_age_seconds": evidence.get("busy_source_age_seconds"),
        "activity_window_seconds": evidence.get("activity_window_seconds"),
        "observation_window_complete": evidence.get("observation_window_complete"),
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def unified_find(query: str, limit: int = 5) -> dict[str, Any]:
    query = str(query or "").strip()
    effective_limit = max(1, min(20, int(limit)))
    if not query:
        return {
            "schema": DISCOVERY_SCHEMA,
            "query": query,
            "authority": DISCOVERY_AUTHORITY,
            "atlas_hits": [],
            "live_hits": [],
            "history_hits": [],
            "git_hits": [],
            "runtime_hits": [],
            "runtime_graph_hits": [],
            "github_cache_hits": [],
            "evidence_clusters": [],
            "coverage": {},
        }
    started = time.perf_counter()
    atlas_hits = find_features(query, effective_limit)
    with ThreadPoolExecutor(max_workers=4) as pool:
        history_future = pool.submit(_timeline_discovery_hits, query, effective_limit)
        live_future = pool.submit(_live_discovery_hits, query, effective_limit)
        github_cache_future = pool.submit(_search_gh_buffer_cache, query, effective_limit)
        runtime_graph_future = pool.submit(_runtime_graph_search_safe, query, min(3, effective_limit))
        try:
            history_hits, history_coverage = history_future.result()
        except Exception as exc:  # Discovery is fail-soft; owner lookup remains usable.
            history_hits, history_coverage = [], {"status": "ERROR", "error": str(exc)}
        try:
            live_hits, live_coverage = live_future.result()
        except Exception as exc:  # Discovery is fail-soft; owner lookup remains usable.
            live_hits, live_coverage = [], {"status": "ERROR", "error": str(exc)}
        try:
            github_cache_hits, github_cache_coverage = github_cache_future.result()
        except Exception as exc:
            github_cache_hits, github_cache_coverage = [], {"status": "ERROR", "error": str(exc), "network_fanout": False}
        try:
            runtime_graph_hits, runtime_graph_coverage = runtime_graph_future.result()
        except Exception as exc:
            runtime_graph_hits, runtime_graph_coverage = [], {"status": "ERROR", "error": str(exc), "network_fanout": False, "broad_task_enumeration": False}
    git_hits = [
        hit for hit in history_hits
        if hit.get("kind") == "git_commit" or bool(hit.get("branches"))
    ]
    runtime_kinds = {"mcp_event", "runner_log", "github_action", "github_action_summary", "machine_observation", "coordinator_event"}
    runtime_hits = [hit for hit in history_hits if hit.get("kind") in runtime_kinds]
    evidence_clusters = list(history_coverage.get("evidence_clusters") or [])
    return {
        "schema": DISCOVERY_SCHEMA,
        "query": query,
        "authority": DISCOVERY_AUTHORITY,
        "atlas_hits": atlas_hits,
        "live_hits": live_hits,
        "history_hits": history_hits,
        "git_hits": git_hits,
        "runtime_hits": runtime_hits,
        "runtime_graph_hits": runtime_graph_hits,
        "github_cache_hits": github_cache_hits,
        "evidence_clusters": evidence_clusters,
        "coverage": {
            "atlas": {"status": "OK", "authority": ATLAS_CONTRACT["authority"]},
            "live": live_coverage,
            "history": history_coverage,
            "git": {
                "status": history_coverage.get("status"),
                "authority": "DERIVED_MATERIALIZED_LOCAL_GIT_HISTORY",
                "read_mode": "MATERIALIZED_QUERY_INDEX_ONLY",
                "network_fanout": False,
                "repo_content_scan": False,
            },
            "github_cache": github_cache_coverage,
            "runtime_graph": runtime_graph_coverage,
        },
        "boundary": "Discovery only. One local discovery query: no repository-content grep/recursive scan, broad Scheduled Task enumeration, or GitHub network fanout. Local Git commits/branches, MCP/runtime receipts and transport/watchdog events, CI/runner evidence, worker reports, artifacts, materialized history, and bounded deployment/runtime graph slices are searched locally. GitHub detail comes from materialized history plus the local gh-buffer cache. Evidence clusters are correlation windows only, never shared truth; runtime graph observations label exact local task/file state but do not replace the owning runtime authority.",
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
    }


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

    if (
        "mcpvpsedge" in ancestry_text
        or "vps_mcp_reverse_tunnel.py" in command
        or (
            "ssh.exe" in command
            and "tietokettu_edge" in command
            and "127.0.0.1:3011" in command
            and any(f"127.0.0.1:310{lane}:" in command for lane in range(1, 5))
        )
    ):
        component = "vps_edge_ingress"
        evidence.append("McpVpsEdge primary/fallback transport process")
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
        return "BLOCK_ACTIVE_TRANSPORT", "prove an alternate machine-execution route and preserve the serving clone before edge disruption"
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
        result = _run_process(
            ["powershell", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=LIVE_PROBE_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
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
        "features": FEATURE_INDEX,
        "components": {name: component_details(name) for name in COMPONENTS},
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
        "## Feature discovery",
        "",
        "Use `find <query>` when you know the need but not the component. Search this derived index before proposing new stack machinery.",
        "",
        "| Feature | Owner components | Entrypoints | Boundary |",
        "| --- | --- | --- | --- |",
    ]
    for feature_id, spec in inventory["features"].items():
        lines.append(f"| `{feature_id}` | {', '.join(spec['owner_components'])} | {'; '.join(spec['entrypoints'])} | {spec['boundary']} |")
    lines.extend(["", "## Components", ""])
    for name, spec in inventory["components"].items():
        lines.extend([f"### `{name}`", "", f"- Role: `{spec['role']}`", f"- Capabilities: {', '.join(spec['capabilities']) or 'none'}"])
        for label, key in (("Canonical sources", "canonical_sources"),):
            values = "; ".join(str(item) for item in spec.get(key, []))
            lines.append(f"- {label}: {values or 'none'}")
        control = spec.get("control") if isinstance(spec.get("control"), dict) else None
        if control is not None:
            actions = [str(action) for action in control.get("actions", []) if str(action).strip()]
            action_items = [f"`{action}`" for action in actions]
            if len(action_items) > 1:
                action_text = ", ".join(action_items[:-1]) + f", and {action_items[-1]}"
            else:
                action_text = action_items[0] if action_items else "none"
            entrypoint_name = Path(str(control.get("entrypoint") or "control entrypoint")).name
            autostart = str(control.get("autostart") or "").strip()
            if autostart == "explicit logon trigger; independent from enabled/running state":
                autostart = "Autostart is an explicit logon trigger and is independent from whether the task is enabled or currently running."
            elif autostart:
                autostart = f"Autostart: {autostart}."
            lines.append(f"- Control: `{entrypoint_name}` exposes {action_text}. {autostart}".rstrip())
            semantics = control.get("intent_semantics") if isinstance(control.get("intent_semantics"), dict) else {}
            semantic_phrases = {
                "task disabled intentionally": "intentionally disabled",
                "task enabled but not running": "enabled but not running",
                "task enabled and running": "enabled and running",
                "task action no longer matches the canonical launcher/root": "the task action no longer matches the canonical launcher/root",
                "no task is registered": "no task exists",
            }
            rendered_semantics = [
                f"`{state}` means {semantic_phrases.get(str(meaning), str(meaning))}"
                for state, meaning in semantics.items()
            ]
            if rendered_semantics:
                lines.append("- State semantics: " + "; ".join(rendered_semantics) + ".")
        for label, key in (("Live status", "live_status"), ("Independent recovery", "independent_recovery"), ("Resources", "resources"), ("Dependents", "dependents"), ("Runbook", "runbook")):
            items = [str(item) for item in spec.get(key, [])]
            if control is not None and key == "live_status" and items:
                items[0] = f"`{items[0]}`"
            values = "; ".join(items)
            lines.append(f"- {label}: {values or 'none'}")
        supervisor = str(spec["supervisor"])
        if control is not None:
            first, separator, rest = supervisor.partition(" ")
            if first.casefold().endswith(".ps1"):
                supervisor = f"`{first}`{separator}{rest}"
        lines.extend([f"- Supervisor: {supervisor}", f"- Self-heal: {spec['self_heal']}", ""])
    lines.extend(["## Process identity and blast radius", "", "OS PIDs are ephemeral lookup keys only. `blast-radius --pid <pid>` resolves stable identity from executable/command line, ancestry, supervisor/config/resource evidence, then reports affected control paths and a destructive verdict.", "", "MCP/VPS process identity is derived from executable, command line, ancestry, supervisor, and resource evidence; never infer safety from a tool name alone.", ""])
    return "\n".join(lines).rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Derived stack capability/dependency Atlas; never a runtime authority.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap-glance")
    sub.add_parser("live-swarm")
    identify = sub.add_parser("identify-actor")
    identify.add_argument("actor")
    fleet = sub.add_parser("fleet-watch")
    fleet.add_argument("--partition", choices=tuple(RECURRING_WORKER_SLOTS))
    fleet.add_argument("--worker-id")
    sub.add_parser("inventory")
    manual = sub.add_parser("manual")
    manual.add_argument("--output", type=Path)
    find = sub.add_parser("find")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=5)
    lookup = sub.add_parser("lookup")
    lookup.add_argument("target")
    lookup.add_argument("--query", help="bounded current Tiny3D asset/name query for tiny3d_library-style targets")
    runtime_explain = sub.add_parser("runtime-explain")
    runtime_explain.add_argument("node")
    runtime_explain.add_argument("--surface")
    runtime_path = sub.add_parser("runtime-path")
    runtime_path.add_argument("source")
    runtime_path.add_argument("target")
    runtime_path.add_argument("--surface")
    blast = sub.add_parser("blast-radius")
    blast.add_argument("--pid", type=int, required=True)
    blast.add_argument("--snapshot", type=Path)
    prod = sub.add_parser("production-change-gate")
    prod.add_argument("target")
    prod.add_argument("--actor", required=True)
    prod.add_argument("--busy-scope", required=True)
    prod.add_argument("--explicit-user-authorization", action="store_true")
    prod.add_argument("--routine-scoped-advance", action="store_true")
    prod.add_argument("--independent-rollback-verified", action="store_true")
    prod.add_argument("--offpath-proof-verified", action="store_true")
    args = parser.parse_args()

    if args.command == "bootstrap-glance":
        value = build_live_bootstrap_glance()
    elif args.command == "live-swarm":
        value = build_live_swarm_snapshot()
    elif args.command == "identify-actor":
        value = identify_current_actor(args.actor)
    elif args.command == "fleet-watch":
        value = _bootstrap_fleet_watch(partition=args.partition, worker_id=args.worker_id)
    elif args.command == "inventory":
        value = full_inventory()
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
        value = unified_find(args.query, args.limit)
    elif args.command == "lookup":
        try:
            value = atlas_lookup(args.target, query=args.query)
        except KeyError:
            parser.error(f"unknown Atlas lookup target: {args.target}")
        except ValueError as exc:
            parser.error(str(exc))
    elif args.command == "runtime-explain":
        value = _runtime_graph_explain_safe(args.node, surface_id=args.surface)
    elif args.command == "runtime-path":
        value = _runtime_graph_path_safe(args.source, args.target, surface_id=args.surface)
    elif args.command == "production-change-gate":
        value = production_change_gate(
            args.target,
            actor=args.actor,
            busy_scope=args.busy_scope,
            explicit_user_authorization=args.explicit_user_authorization,
            routine_scoped_advance=args.routine_scoped_advance,
            independent_rollback_verified=args.independent_rollback_verified,
            offpath_proof_verified=args.offpath_proof_verified,
        )
    else:
        if args.snapshot:
            processes, ports, resources = load_snapshot(args.snapshot)
        else:
            processes, ports, resources = capture_windows_processes(), capture_windows_ports(), []
        value = blast_radius(args.pid, processes, ports=ports, resource_observations=resources)
    if args.command == "bootstrap-glance":
        print(json.dumps(value, separators=(",", ":"), ensure_ascii=False))
    else:
        print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

