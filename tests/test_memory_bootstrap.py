import json
import unittest
from pathlib import Path

from tools.memory_bank import build_startup_bootstrap, load_bank


ROOT = Path(__file__).resolve().parents[1]
RETIRED_LIBRARY_PATH = "/Agent Bootstrap/chatgpt-bootstrap.json"


class MemoryBootstrapRetirementTests(unittest.TestCase):
    def test_legacy_bootstrap_is_tiny_retirement_marker(self):
        payload = build_startup_bootstrap(load_bank())
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(payload["status"], "RETIRED")
        self.assertIn("history/notebook/evidence", payload["purpose"])
        self.assertIn("ChatGPT/harness memory", payload["continuity"])
        self.assertIn("Stack Atlas", payload["stack_map"])
        self.assertIn("live sources", payload["current_truth"])
        self.assertNotIn("behavior_profile", payload)
        self.assertNotIn("canonical_policy_profile", payload)
        self.assertNotIn("recent_memory_glance", payload)
        self.assertLess(len(rendered), 1000)

    def test_personal_instructions_use_memory_atlas_and_live_truth(self):
        text = (ROOT / "04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt").read_text(encoding="utf-8")
        self.assertIn("ChatGPT Memory for continuity", text)
        self.assertIn("Stack Atlas", text)
        self.assertIn("current live evidence", text)
        self.assertIn("optional searchable history, notebook, evidence", text)
        self.assertIn("Keep useful work and the recurring worker fleet moving", text)
        self.assertNotIn("memory_bank.py bootstrap", text)
        self.assertNotIn(RETIRED_LIBRARY_PATH, text)

    def test_session_contract_has_no_vault_startup_gate(self):
        text = (ROOT / "04 Operating Contracts/fresh-chat-startup-orientation.md").read_text(encoding="utf-8")
        self.assertIn("current conversation and ChatGPT Memory", text)
        self.assertIn("There is no Vault behavior bootstrap", text)
        self.assertIn("consult the Stack Atlas", text)
        self.assertIn("Current-state answers require current evidence", text)
        self.assertIn("optional notebook-style enrichment", text)
        self.assertNotIn("behavior delivery ->", text)

    def test_distribution_contract_retires_behavior_bootstrap(self):
        text = (ROOT / "04 Operating Contracts/chatgpt-bootstrap-distribution.md").read_text(encoding="utf-8")
        self.assertIn("behavior-bootstrap pipeline is retired", text)
        self.assertIn(RETIRED_LIBRARY_PATH, text)
        self.assertIn("legacy/recovery surfaces only", text)
        self.assertIn("Stack Atlas remains an operational map", text)
        self.assertIn("searchable history/notebook/evidence", text)
        self.assertNotIn("Library publisher worker contract", text)

    def test_shared_policy_treats_vault_as_optional_history(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("### Navigation minimap", text)
        self.assertIn("Vault is history/evidence", text)
        self.assertIn("never recursively scan Vault or make it a startup gate", text)
        self.assertNotIn("memory_bank.py bootstrap", text)

    def test_worker_contract_still_keeps_five_workers_and_no_self_admin(self):
        text = (ROOT / "04 Operating Contracts/fresh-worker-generation-launch.md").read_text(encoding="utf-8")
        self.assertIn("Five is a hard maximum for the recurring worker fleet", text)
        self.assertIn("switch immediately to Commander", text)
        self.assertIn("Plugin2 loss alone never permits", text)
        self.assertIn("Worker execution may never administer the scheduler", text)
        self.assertIn("For stack/infra work only", text)
        self.assertIn("optional mirror", text)
        self.assertIn("never a startup gate or blocker", text)
        self.assertIn("visual_proof_run", text)
        self.assertIn("visual_proof_reviewed_json", text)
        self.assertIn("PENDING_REVIEW", text)
        self.assertIn("Visual review never blocks the worker fleet", text)
        self.assertIn("automatic metrics", text)
        self.assertIn("about 24 minutes of useful execution budget", text)
        self.assertIn("duration is diagnostic data, never completion proof", text)
        self.assertIn("Workers must not manually calculate, narrate, or maintain those metrics", text)
        self.assertIn("worker-reports/metrics.json", text)
        self.assertIn("stop_reason", text)
        self.assertIn("tool_drop_effect", text)
        self.assertIn("A transient tool drop is evidence, not by itself permission to stop", text)
        self.assertIn(r"C:\P3Proofs", text)
        self.assertIn("latest snapshot, not the log", text)
        self.assertIn("worker-reports/history/<WorkerName>/", text)
        self.assertIn("Finish owned delivery before opening more inventory", text)
        self.assertIn("Publishing a PR, pushing a commit, or passing local tests is progress, not completion", text)


if __name__ == "__main__":
    unittest.main()
