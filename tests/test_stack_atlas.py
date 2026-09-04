import json
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path

from tools.capability_routing import load_policy as load_capability_policy
from tools.stack_atlas import (
    ATLAS_CONTRACT,
    blast_radius,
    build_bootstrap_atlas,
    build_live_bootstrap_glance,
    classify_process,
    component_details,
    find_features,
    full_inventory,
    render_manual,
    render_library_atlas_bytes,
    atlas_publication_plan,
    _bootstrap_pc_status,
    _bootstrap_worker_status,
    _bootstrap_disk_trend,
)

ROOT = Path(__file__).resolve().parents[1]


class StackAtlasTests(unittest.TestCase):
    def test_live_bootstrap_pc_status_includes_commit_headroom(self):
        pc = _bootstrap_pc_status()
        memory = pc["memory"]
        for field in ("physical_free_gb", "commit_used_gb", "commit_limit_gb", "commit_headroom_gb", "commit_used_pct", "status"):
            self.assertIn(field, memory)
        self.assertGreaterEqual(memory["commit_headroom_gb"], 0)
        self.assertNotIn("ram_free_gb", pc)
        self.assertIn("trend", pc["disk"])
        self.assertIn("previous", pc["disk"]["trend"])
        self.assertIn("approx_24h", pc["disk"]["trend"])


    def test_disk_trend_reports_previous_and_approx_24h_observations(self):
        from datetime import datetime, timedelta, timezone
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.jsonl"
            now = datetime.now(timezone.utc)
            rows = [
                {"at": (now - timedelta(hours=24)).isoformat(), "free_gb": 115.0},
                {"at": (now - timedelta(hours=2)).isoformat(), "free_gb": 70.0},
            ]
            path.write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")
            with patch("tools.stack_atlas.BOOTSTRAP_OBSERVATION_PATH", path):
                trend = _bootstrap_disk_trend(55.0)
            self.assertEqual(trend["previous"]["lost_gb"], 15.0)
            self.assertEqual(trend["approx_24h"]["lost_gb"], 60.0)
            self.assertAlmostEqual(trend["approx_24h"]["age_hours"], 24.0, delta=0.1)

    def test_agent_rule_authority_is_single_shared_repo(self):
        details = component_details("agent_rules")
        self.assertEqual(details["canonical_sources"][0], r"C:\Users\Lauri\.agents\RULES.md")
        self.assertEqual(details["canonical_sources"][1], r"C:\Users\Lauri\.agents\AGENTS.md")
        self.assertEqual(details["canonical_sources"][2], "organicoverlords/agents@main")
        self.assertEqual(details["resources"], ["RULES.md", "AGENTS.md", "main"])
        glance = build_live_bootstrap_glance()
        self.assertEqual(glance["paths"]["rules"], r"C:\Users\Lauri\.agents\RULES.md")
        self.assertEqual(glance["paths"]["agents"], r"C:\Users\Lauri\.agents\AGENTS.md")
        self.assertNotIn("rule_contexts", glance["paths"])

    def test_live_bootstrap_glance_is_compact_and_decision_focused(self):
        glance = build_live_bootstrap_glance()
        payload = json.dumps(glance, separators=(",", ":"))
        self.assertLess(len(payload.encode("utf-8")), 12000)
        self.assertNotIn("activity", glance["mcp"])
        self.assertIn("activity_summary", glance["mcp"])
        self.assertEqual(glance["mcp"]["active_session_count"], len(glance["mcp"]["active_sessions"]))
        for caller in glance["mcp"]["active_sessions"]:
            self.assertNotIn("cwds", caller)
            self.assertTrue(caller["process_starts"] or caller["reads"])
            self.assertIn("busy_titles", caller)
            self.assertIn("workspace", caller)
            self.assertIn("activity_age_seconds", caller)
            self.assertLessEqual(caller["activity_age_seconds"], 300)
        self.assertIn("notable_conditions", glance)
        self.assertIsInstance(glance["notable_conditions"], list)
        self.assertEqual(len(glance["recent_memory_titles"]), 20)
        for item in glance["recent_memory_titles"]:
            self.assertLessEqual(set(item), {"id", "timestamp", "title"})
        for item in glance["workers"]["latest_per_worker"]:
            self.assertNotIn("scope", item)
            self.assertNotIn("stop_reason", item)

    def test_live_bootstrap_worker_status_is_actionable_per_worker(self):
        workers = _bootstrap_worker_status()
        self.assertEqual(workers["target_run_minutes"], 24.0)
        self.assertIn("latest_per_worker", workers)
        self.assertIn("attention", workers)
        self.assertIn("fleet", workers)
        seen = set()
        for item in workers["latest_per_worker"]:
            self.assertNotIn(item["automation_id"], seen)
            seen.add(item["automation_id"])
            self.assertIn(item["classification"], {"ON_TARGET", "SHORT", "PREMATURE", "SEVERELY_PREMATURE", "UNKNOWN"})
            self.assertEqual(item["target_minutes"], 24.0)
            self.assertIn("age_minutes", item)
        self.assertEqual(workers["fleet"]["workers_seen"], len(workers["latest_per_worker"]))

    def test_bootstrap_atlas_is_small_directory_not_live_status_cache(self):
        atlas = build_bootstrap_atlas()
        self.assertEqual(atlas["schema"], "atlas.v1")
        self.assertIn("Map only", atlas["must"])
        self.assertIn("leave Atlas", atlas["must"])
        self.assertIn("Product repos stay outside Atlas", atlas["must"])
        self.assertNotIn("live_overlay", atlas)
        self.assertEqual(atlas["find"], "find <query>")
        self.assertLess(len(json.dumps(atlas)), 12000)

    def test_feature_search_surfaces_existing_owner_before_archaeology(self):
        timeline = find_features("vault timeline")[0]
        self.assertEqual(timeline["id"], "vault.history")
        self.assertEqual(timeline["owner_components"], ["memory_bank"])
        self.assertIn("memory_bank.py timeline", timeline["entrypoints"])
        self.assertIn("never recursive Vault scans", timeline["boundary"])

        checkpoint = find_features("checkpoint resume")[0]
        self.assertEqual(checkpoint["id"], "coordination.checkpoint_context")
        self.assertIn("busy_coordinator", checkpoint["owner_components"])
        self.assertIn("never backlog", checkpoint["boundary"])

        reports = find_features("worker reports")[0]
        self.assertEqual(reports["id"], "worker.reports")
        self.assertIn("worker_reports", reports["owner_components"])
        self.assertIn("PENDING_REVIEW", reports["boundary"])
        self.assertIn("reviewed.json", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn(r"C:\P3Proofs", " ".join(component_details("worker_reports")["live_status"]))
        self.assertIn("worker-reports/current/<automation-id>.md", " ".join(component_details("worker_reports")["resources"]))
        self.assertIn("history/_reports", " ".join(component_details("worker_reports")["resources"]))
        self.assertNotIn("metrics.json", " ".join(component_details("worker_reports")["resources"]))

    def test_feature_search_is_bounded_and_non_authoritative(self):
        self.assertEqual(find_features(""), [])
        self.assertEqual(find_features("definitely-unknown-capability"), [])
        self.assertEqual(find_features("workers")[0]["id"], "execution_workers")
        self.assertEqual(find_features("atlas")[0]["id"], "stack_atlas")
        self.assertEqual(find_features("mcpv3")[0]["id"], "mcpv3_surface")
        results = find_features("current state", limit=2)
        self.assertLessEqual(len(results), 2)
        self.assertTrue(all(item["authority"] == ATLAS_CONTRACT["authority"] for item in results))

    def test_pid_is_lookup_key_not_component_identity(self):
        self.assertIn("ephemeral live lookup key", ATLAS_CONTRACT["pid_semantics"])
        self.assertIn("stable identity", ATLAS_CONTRACT["pid_semantics"])

    def test_unknown_process_is_never_disposable(self):
        processes = [{
            "pid": 4444,
            "ppid": 1,
            "name": "node.exe",
            "command_line": "node.exe unknown.js",
        }]
        result = blast_radius(4444, processes)
        self.assertEqual(result["status"], "UNRESOLVED")
        self.assertEqual(result["destructive_verdict"], "BLOCK_UNKNOWN_TOPOLOGY")
        self.assertIn("stable_component_identity", result["unknowns"])

    def test_mcpv3_lookup_starts_from_semantics_not_edge(self):
        details = component_details("mcpv3")
        self.assertEqual(details["id"], "mcpv3_surface")
        sources = " ".join(details["canonical_sources"])
        self.assertIn("process-tool-contract.json", sources)
        self.assertIn("process-manager.js", sources)
        self.assertIn("wait_ms", details["boundary"])
        self.assertIn("aggregate duration alone", details["boundary"])
        self.assertIn("tool contract/schema", details["diagnostic_order"][0])
        self.assertIn("VPS edge/reverse-SSH only", " ".join(details["diagnostic_order"]))

    def test_mcpv3_stall_search_requires_semantic_latency_classification(self):
        result = find_features("mcpv3 stall")[0]
        self.assertEqual(result["id"], "execution.transport")
        self.assertIn("mcpv3_surface", result["owner_components"])
        self.assertIn("process-tool-contract.json", " ".join(result["entrypoints"]))
        self.assertIn("Expected wait/poll windows", result["boundary"])
        self.assertIn("aggregate duration alone", result["boundary"])

    def test_busy_lookup_forces_current_contract_and_ownership_boundary(self):
        details = component_details("busy")
        self.assertEqual(details["id"], "busy_coordinator")
        sources = " ".join(details["canonical_sources"])
        self.assertIn("coordinator-contract.json", sources)
        self.assertIn("busy.py", sources)
        self.assertIn("--help", " ".join(details["live_status"]))
        self.assertIn("ownership only", details["boundary"])
        self.assertIn("queue/workflow commands are retired", details["boundary"])

    def test_atlas_contract_requires_contract_first_debugging(self):
        gate = ATLAS_CONTRACT["debugging_gate"]
        self.assertIn("contract/help", gate)
        self.assertIn("requested waits", gate)
        self.assertIn("child-command runtime", gate)

    def test_mcp_front_door_requires_inactive_generation_update_path(self):
        details = component_details("mcp_front_door")
        self.assertIn("inactive backend generation", " ".join(details["independent_recovery"]))
        self.assertIn("exact tool contract", " ".join(details["live_status"]))

    def test_vps_edge_process_classifies_and_blocks_disruption(self):
        process = {
            "pid": 480, "ppid": 1, "name": "python.exe",
            "command_line": r"python.exe C:\Users\Lauri\AppData\Local\McpVpsEdge\vps_mcp_reverse_tunnel.py",
        }
        result = blast_radius(480, [process])
        self.assertEqual(result["identity"]["component"], "vps_edge_ingress")
        self.assertEqual(result["destructive_verdict"], "BLOCK_ACTIVE_TRANSPORT")

    def test_vps_origin_listener_wrapper_classifies_as_minimal_clone(self):
        listener = {
            "pid": 11328, "ppid": 5376, "name": "node.exe",
            "command_line": r"node.exe dist/index.js",
        }
        launcher = {
            "pid": 5376, "ppid": 1, "name": "powershell.exe",
            "command_line": r"powershell.exe -File C:\Users\Lauri\AppData\Local\Temp\launch-mcp-vps-origin.ps1",
        }
        mapping = {item["pid"]: item for item in (listener, launcher)}
        self.assertEqual(classify_process(listener, mapping)["component"], "mcp_minimal_clone")

    def test_natural_component_aliases_resolve(self):
        self.assertEqual(component_details("mcp")["id"], "mcp_front_door")
        self.assertEqual(component_details("plugin2")["id"], "mcp_front_door")
        self.assertEqual(component_details("webgpt")["id"], "chatgpt_session")
        self.assertEqual(component_details("coordinator")["id"], "busy_coordinator")
        self.assertEqual(component_details("ci")["id"], "github_actions")
        self.assertEqual(component_details("atlas")["id"], "stack_atlas")
        self.assertEqual(component_details("webgpt")["role"], "session:user-facing")

    def test_bootstrap_directory_covers_major_stack_surfaces(self):
        atlas = build_bootstrap_atlas()
        ids = set(__import__("tools.stack_atlas", fromlist=["COMPONENTS"]).COMPONENTS)
        expected = {
            "stack_atlas", "busy_coordinator", "mcpv3_surface", "mcp_front_door", "mcp_backend", "mcp_minimal_clone",
            "agent_rules", "repo_rule_pointer", "north_star", "chatgpt_memory", "memory_bank",
            "chatgpt_session", "execution_workers", "chatgpt_automations", "local_git", "github",
            "github_actions", "github_runner", "worker_reports",
        }
        self.assertTrue(expected.issubset(ids), sorted(expected - ids))
        self.assertNotIn("operator_live", ids)

    def test_product_repositories_are_outside_atlas(self):
        for name in ("p3", "tiny3d", "lowvram", "asset_library", "p3 build", "build contention"):
            with self.subTest(name=name), self.assertRaises(KeyError):
                component_details(name)
        inventory = full_inventory()
        self.assertNotIn("product_flow", inventory)
        self.assertIn("STACK_INFRA_MAP_ONLY", inventory["contract"]["scope"])

    def test_capability_directory_is_derived_from_current_routing_policy(self):
        policy = deepcopy(load_capability_policy())
        policy["capabilities"]["fresh_capability"] = policy["capabilities"]["runtime_validate"]
        with patch("tools.stack_atlas.load_policy", return_value=policy):
            atlas = build_bootstrap_atlas()
        self.assertNotIn("inventory", atlas)
        self.assertNotIn("library", atlas)


    def test_generated_operational_manual_matches_atlas(self):
        manual = ROOT / "docs" / "assistant-stack-operational-atlas.md"
        self.assertEqual(manual.read_text(encoding="utf-8"), render_manual() + "\n")
        text = manual.read_text(encoding="utf-8")
        self.assertNotIn("desktop_commander", text.casefold())
        self.assertIn("### `mcp_front_door`", text)
        self.assertIn("Independent recovery", text)
        self.assertIn("Supervisor", text)
        self.assertIn("Resources", text)
        self.assertNotIn("## Product flow", text)
        self.assertIn("P3, Tiny3D, LowVRAM", text)

    def test_repo_agents_stays_pointer_only(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("pointer-only", agents)
        self.assertNotIn("consume the current Stack Atlas", agents)
        self.assertNotIn("deep-lookup", agents)

    def test_every_component_declares_its_own_live_truth_and_recovery_routes(self):
        atlas = __import__("tools.stack_atlas", fromlist=["COMPONENTS"])
        for component in atlas.COMPONENTS:
            with self.subTest(component=component):
                details = component_details(component)
                for field in ("canonical_sources", "live_status", "supervisor", "self_heal", "independent_recovery", "resources", "dependents", "runbook"):
                    self.assertIn(field, details)
                    self.assertIsNotNone(details[field])
                self.assertTrue(details["live_status"])
                self.assertTrue(details["canonical_sources"])
                self.assertTrue(details["runbook"])

    def test_library_atlas_is_deterministic_on_demand_inventory(self):
        data = render_library_atlas_bytes()
        artifact = json.loads(data)
        self.assertEqual(artifact["library_path"], "/Agent Bootstrap/stack-atlas.json")
        self.assertEqual(artifact["inventory"], __import__("tools.stack_atlas", fromlist=["full_inventory"]).full_inventory())
        self.assertEqual(data, render_library_atlas_bytes())
        self.assertEqual(atlas_publication_plan()["bytes"], len(data))


class Issue394StackVisibilityTests(unittest.TestCase):
    def test_human_aliases_cover_invisible_stack_seams(self):
        self.assertEqual(component_details("tailscale")["id"], "tailscale_ingress")
        self.assertEqual(component_details("transfer")["id"], "file_transfer")
        self.assertEqual(component_details("file transfer")["id"], "file_transfer")
        self.assertEqual(component_details("visual proof")["id"], "visual_proof")
        self.assertEqual(component_details("workers")["id"], "execution_workers")
