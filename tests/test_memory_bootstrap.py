import json
import unittest
from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]
RETIRED_LIBRARY_PATH = "/Agent Bootstrap/chatgpt-bootstrap.json"


class MemoryBootstrapRetirementTests(unittest.TestCase):
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
        self.assertIn("command is no longer exposed", text)
        self.assertIn("not published as current behavior authority", text)
        self.assertIn("Stack Atlas remains an operational map", text)
        self.assertIn("searchable history/notebook/evidence", text)
        self.assertNotIn("Library publisher worker contract", text)

    def test_shared_policy_treats_vault_as_optional_history(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("### Navigation minimap", text)
        self.assertIn("Vault is history/evidence", text)
        self.assertIn("never recursively scan Vault or make it a startup gate", text)
        self.assertNotIn("memory_bank.py bootstrap", text)

    def test_worker_contract_stays_small_and_non_blocking(self):
        text = (ROOT / "04 Operating Contracts/fresh-worker-generation-launch.md").read_text(encoding="utf-8")
        self.assertIn("Five is a hard maximum for the recurring worker fleet", text)

        self.assertIn("The scheduler provides recurrence only", text)
        self.assertIn("Workers never administer workers", text)
        self.assertIn("About 24 minutes is a utilization target", text)
        self.assertIn("A blocker changes scope; it does not end unrelated work", text)
        self.assertIn("BusyCoordinator is collision control only", text)
        self.assertIn("worker-reports/current/<automation-id>.md", text)
        self.assertNotIn("metrics.json.latest_reports", text)
        self.assertNotIn("PENDING_REVIEW", text)
        self.assertNotIn("Remote Desktop Commander", text)
        self.assertNotIn("first-launch proof", text.lower())

if __name__ == "__main__":
    unittest.main()
