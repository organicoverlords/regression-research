import json
import unittest
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path

from tools.capability_routing import load_policy as load_capability_policy
from tools.stack_atlas import (
    ATLAS_CONTRACT,
    blast_radius,
    build_bootstrap_atlas,
    classify_process,
    component_details,
    find_features,
    full_inventory,
    render_manual,
    render_library_atlas_bytes,
    atlas_publication_plan,
)

ROOT = Path(__file__).resolve().parents[1]


class StackAtlasTests(unittest.TestCase):
    def test_bootstrap_atlas_is_small_directory_not_live_status_cache(self):
        atlas = build_bootstrap_atlas()
        self.assertEqual(atlas["schema"], "atlas.v1")
        self.assertIn("Stack/infra only", atlas["must"])
        self.assertIn("quick locator", atlas["must"])
        self.assertIn("do not route ordinary product-repo work through Atlas", atlas["must"])
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
            "stack_atlas", "busy_coordinator", "mcp_front_door", "mcp_backend", "mcp_minimal_clone",
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
        self.assertEqual(atlas["inventory"], "inventory")


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
