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


    def test_vault_policy_is_centralized_and_local_agents_is_pointer_only(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(r"C:\Users\Lauri\.agents\RULES.md", text)
        self.assertIn(r"C:\Users\Lauri\.agents\AGENTS.md", text)
        self.assertIn("https://github.com/organicoverlords/agents", text)
        self.assertIn("pointer-only", text)
        self.assertNotIn(r"C:\Users\Lauri\Documents\agent-rules", text)
        self.assertNotIn(r"contexts\vault.md", text)
        self.assertNotIn("memory_bank.py bootstrap", text)
        self.assertNotIn("### Navigation minimap", text)

    def test_worker_contract_stays_small_and_non_blocking(self):
        text = (ROOT / "04 Operating Contracts/fresh-worker-generation-launch.md").read_text(encoding="utf-8")
        self.assertIn("Five is a hard maximum for the recurring worker fleet", text)

        self.assertIn("The scheduler provides recurrence only", text)
        self.assertIn("Workers never administer workers", text)
        self.assertIn("About 24 minutes is an observational utilization target", text)
        self.assertIn("never a completion or admission gate", text)
        self.assertIn("Do not create a new issue or unrelated scope merely to fill the run window", text)
        self.assertIn("A blocker changes scope; it does not end unrelated work", text)
        self.assertIn("BusyCoordinator is collision control only", text)
        self.assertIn("worker-reports/current/<automation-id>.md", text)
        self.assertIn("Near the start of every timed run", text)
        self.assertIn("before any command that may consume a material part of the useful run window", text)
        self.assertIn("`state: RUNNING`", text)
        self.assertNotIn("metrics.json.latest_reports", text)
        self.assertNotIn("PENDING_REVIEW", text)
        self.assertNotIn("Remote Desktop Commander", text)
        self.assertNotIn("first-launch proof", text.lower())

if __name__ == "__main__":
    unittest.main()
