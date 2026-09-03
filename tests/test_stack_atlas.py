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
        self.assertIn("load canonical inventory before reasoning/answer/change", atlas["must"])
        self.assertIn("touched components for live proof", atlas["must"])
        self.assertIn("blocks disruption", atlas["must"])
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
        self.assertEqual(component_details("webgpt")["role"], "session:user-facing")
        self.assertEqual(component_details("rules")["id"], "agent_rules")

    def test_bootstrap_directory_covers_major_stack_surfaces(self):
        atlas = build_bootstrap_atlas()
        ids = set(__import__("tools.stack_atlas", fromlist=["COMPONENTS"]).COMPONENTS) | set(__import__("tools.stack_atlas", fromlist=["PRODUCT_ROOTS"]).PRODUCT_ROOTS)
        expected = {
            "busy_coordinator", "mcp_front_door", "mcp_backend", "mcp_minimal_clone",
            "agent_rules", "repo_rule_pointer", "north_star", "chatgpt_memory", "memory_bank",
            "chatgpt_session", "execution_workers", "chatgpt_automations", "local_git", "github",
            "github_actions", "github_runner", "dev_progress_board", "operator_live", "worker_reports",
            "lowvram", "asset_library", "tiny3d", "p3",
        }
        self.assertTrue(expected.issubset(ids), sorted(expected - ids))

    def test_product_flow_and_roles_match_current_repo_architecture(self):
        atlas = __import__("tools.stack_atlas", fromlist=["PRODUCT_FLOW"])
        self.assertEqual(atlas.PRODUCT_FLOW, (("lowvram", "tiny3d"), ("tiny3d", "p3")))
        lowvram = component_details("lowvram")
        tiny3d = component_details("tiny3d")
        library = component_details("asset_library")
        self.assertEqual(lowvram["role"], "generator:image_to_3d")
        self.assertEqual(tiny3d["role"], "product:post_generation_asset_compiler")
        self.assertIn("README.md", " ".join(lowvram["canonical_sources"]))
        self.assertIn("TINY3D_NORTH_STAR.md", " ".join(tiny3d["canonical_sources"]))
        self.assertEqual(library["canonical_sources"][0], r"C:\Users\Lauri\Desktop\Tiny3D_LIBRARY")
        self.assertEqual(full_inventory()["product_flow"], [["lowvram", "tiny3d"], ["tiny3d", "p3"]])

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

    def test_vault_agents_is_pointer_only_to_canonical_rules(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(len(agents.rstrip().splitlines()), 7)
        self.assertIn(r"C:\Users\Lauri\Documents\agent-rules\RULES.md", agents)
        self.assertIn(r"contexts\vault.md", agents)
        self.assertIn("pointer-only", agents)
        self.assertNotIn("SHARED-AGENT-POLICY", agents)
        self.assertNotIn("### Navigation minimap", agents)

    def test_memory_bank_publishes_only_through_dedicated_memory_branch(self):
        memory = component_details("memory_bank")
        joined = " ".join([*memory["canonical_sources"], *memory["live_status"]])
        self.assertIn("origin/memory/live", joined)
        self.assertIn("forbidden publication targets", joined)

    def test_every_component_declares_its_own_live_truth_and_recovery_routes(self):
        atlas = __import__("tools.stack_atlas", fromlist=["COMPONENTS", "PRODUCT_ROOTS"])
        for component in [*atlas.COMPONENTS, *atlas.PRODUCT_ROOTS]:
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

    def test_full_stack_timeline_is_discoverable_by_workers(self):
        found = find_features("full stack timeline")
        self.assertTrue(found)
        self.assertEqual(found[0]["id"], "stack.timeline")
        self.assertIn("full_stack_timeline.py", " ".join(found[0]["entrypoints"]))
