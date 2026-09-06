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
        self.assertIn("Exactly five canonical recurring workers stay enabled", text)

        self.assertIn("The scheduler provides recurrence only", text)
        self.assertIn("Every recurring worker is also a bounded peer-recovery orchestrator", text)
        self.assertIn("must never administer itself", text)
        self.assertIn("re-enable that sibling once with `is_enabled=true` only", text)
        self.assertIn("Do not require a particular failure signature before restoring the requested 5/5 enabled fleet", text)
        self.assertIn("An unexpected disabled canonical worker is degradation to repair", text)
        self.assertIn("does not create a sixth supervisor slot", text)
        self.assertIn("About 24 minutes remains the timed utilization target", text)
        self.assertIn("Finishing the selected acceptance early is a valid finish.", text)
        self.assertIn("Never open another issue/PR, select another acceptance row, or hunt for a disjoint gap merely to reach >=80% utilization.", text)
        self.assertIn("A blocker constrains the selected acceptance; it does not authorize scope expansion.", text)
        self.assertNotIn("Finishing one bounded slice early should lead to another safe useful action", text)
        self.assertIn("BusyCoordinator is collision control only", text)
        self.assertIn("worker-reports/current/<automation-id>.md", text)
        self.assertIn("Near the start of every timed run", text)
        self.assertIn("before any command that may consume a material part of the useful run window", text)
        self.assertIn("`state: RUNNING`", text)
        self.assertIn("Reporting is evidence/observability only and never completion", text)
        self.assertIn("A manual report is accounting/feedback evidence, not liveness", text)
        self.assertNotIn("metrics.json.latest_reports", text)
        self.assertNotIn("PENDING_REVIEW", text)
        self.assertNotIn("Remote Desktop Commander", text)
        self.assertNotIn("first-launch proof", text.lower())

if __name__ == "__main__":
    unittest.main()
