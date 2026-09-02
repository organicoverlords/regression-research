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
    full_inventory,
    load_snapshot,
    render_manual,
    render_library_atlas_bytes,
    atlas_publication_plan,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "stack-atlas-pid-29864.json"


class StackAtlasTests(unittest.TestCase):
    def test_bootstrap_atlas_is_small_directory_not_live_status_cache(self):
        atlas = build_bootstrap_atlas()
        self.assertEqual(atlas["schema"], "atlas.v1")
        self.assertIn("load canonical inventory before reasoning/answer/change", atlas["must"])
        self.assertIn("touched components for live proof", atlas["must"])
        self.assertIn("blocks disruption", atlas["must"])
        self.assertNotIn("live_overlay", atlas)
        self.assertLess(len(json.dumps(atlas)), 12000)

    def test_pid_is_lookup_key_not_component_identity(self):
        self.assertIn("ephemeral live lookup key", ATLAS_CONTRACT["pid_semantics"])
        self.assertIn("stable identity", ATLAS_CONTRACT["pid_semantics"])

    def test_29864_incident_resolves_commander_and_blocks_kill(self):
        processes, ports, resources = load_snapshot(FIXTURE)
        result = blast_radius(29864, processes, ports=ports, resource_observations=resources)
        self.assertEqual(result["status"], "RESOLVED")
        self.assertEqual(result["identity"]["component"], "desktop_commander_local")
        self.assertEqual(result["destructive_verdict"], "BLOCK_CONTROL_PATH_DEPENDENCY")
        self.assertTrue(result["affected"]["commander"])
        self.assertTrue(result["affected"]["worker_execution"])
        self.assertTrue(result["affected"]["busy_coordinator_access"])
        self.assertFalse(result["affected"]["mcp"])
        self.assertIn("execution_workers", result["affected"]["other_control_paths"])
        self.assertEqual(
            result["resource_observations"][0]["relation"],
            "open_handle_blocked_atomic_replace",
        )

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

    def test_same_component_identity_survives_pid_change(self):
        first = {
            "pid": 29864, "ppid": 30120, "name": "node.exe",
            "command_line": r"node.exe C:\Users\Lauri\AppData\Local\DesktopCommanderFallback\app\node_modules\@wonderwhy-er\desktop-commander\dist\index.js",
        }
        second = dict(first, pid=9001)
        parent = {
            "pid": 30120, "ppid": 17208, "name": "node.exe",
            "command_line": r"node.exe C:\Users\Lauri\AppData\Local\DesktopCommanderFallback\app\node_modules\@wonderwhy-er\desktop-commander\dist\index.js remote --persist-session",
        }
        watchdog = {
            "pid": 17208, "ppid": 1, "name": "pwsh.exe",
            "command_line": r"pwsh.exe -File C:\Users\Lauri\AppData\Local\DesktopCommanderFallback\watchdog.ps1",
        }
        first_map = {item["pid"]: item for item in (first, parent, watchdog)}
        second_map = {item["pid"]: item for item in (second, parent, watchdog)}
        self.assertEqual(classify_process(first, first_map)["component"], "desktop_commander_local")
        self.assertEqual(classify_process(second, second_map)["component"], "desktop_commander_local")

    def test_mcp_front_door_requires_inactive_generation_update_path(self):
        details = component_details("mcp_front_door")
        self.assertIn("inactive backend generation", " ".join(details["independent_recovery"]))
        self.assertIn("exact tool contract", " ".join(details["live_status"]))

    def test_bootstrap_directory_covers_major_stack_surfaces(self):
        atlas = build_bootstrap_atlas()
        ids = set(__import__("tools.stack_atlas", fromlist=["COMPONENTS"]).COMPONENTS) | set(__import__("tools.stack_atlas", fromlist=["PRODUCT_ROOTS"]).PRODUCT_ROOTS)
        expected = {
            "busy_coordinator", "mcp_front_door", "mcp_backend", "mcp_minimal_clone",
            "desktop_commander_watchdog", "desktop_commander_remote", "desktop_commander_local",
            "shared_policy", "repo_agents", "north_star", "chatgpt_memory", "memory_bank",
            "chatgpt_orchestrator", "execution_workers", "chatgpt_automations", "local_git", "github",
            "github_actions", "github_runner", "dev_progress_board", "operator_live",
            "lowvram", "asset_library", "tinylab", "tiny3d", "p3", "vault_history",
        }
        self.assertTrue(expected.issubset(ids), sorted(expected - ids))

    def test_product_flow_and_roles_match_current_repo_architecture(self):
        atlas = __import__("tools.stack_atlas", fromlist=["PRODUCT_FLOW"])
        self.assertEqual(atlas.PRODUCT_FLOW, (("lowvram", "tiny3d"), ("tiny3d", "p3")))
        lowvram = component_details("lowvram")
        tiny3d = component_details("tiny3d")
        tinylab = component_details("tinylab")
        library = component_details("asset_library")
        self.assertEqual(lowvram["role"], "generator:image_to_3d")
        self.assertEqual(tiny3d["role"], "product:post_generation_asset_compiler")
        self.assertEqual(tinylab["role"], "legacy_name:not_active_product_authority")
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
        self.assertIn("### `desktop_commander_local`", text)
        self.assertIn("### `mcp_front_door`", text)
        self.assertIn("Independent recovery", text)
        self.assertIn("Supervisor", text)
        self.assertIn("Resources", text)

    def test_repo_agents_requires_atlas_before_stack_work(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("consume the current Stack Atlas", agents)
        self.assertIn("before deciding relevance or blast radius", agents)
        self.assertIn("deep-lookup only the components/live proof routes relevant to the task", agents)
        self.assertIn("unresolved dependency or recovery impact blocks the action", agents)
        self.assertIn("PID is only an ephemeral lookup key", agents)

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
