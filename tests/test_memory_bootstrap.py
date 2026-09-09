import json
import unittest
from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]
RETIRED_LIBRARY_PATH = "/Agent Bootstrap/chatgpt-bootstrap.json"


class MemoryBootstrapRetirementTests(unittest.TestCase):
    def test_personal_instructions_are_not_repository_authority(self):
        self.assertFalse((ROOT / "04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt").exists())
        atlas = (ROOT / "tools/stack_atlas.py").read_text(encoding="utf-8")
        self.assertIn("context:disabled-product-memory", atlas)
        self.assertIn('"targeted Vault history"', atlas)
        self.assertNotIn('"canonical_sources": ["current conversation", "ChatGPT Memory"', atlas)
        self.assertNotIn('"runbook": ["04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt"]', atlas)

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
        self.assertIn("Exactly five canonical recurring workers per ChatGPT subscription partition stay enabled", text)

        self.assertIn("The scheduler provides recurrence only", text)
        self.assertIn("Every recurring worker is a bounded sibling-recovery participant", text)
        self.assertIn("must never administer itself", text)
        self.assertIn("issue at most one targeted idempotent `is_enabled=true` write", text)
        self.assertIn("Older launcher wording that asks for a full scheduler/report pre-startup-failure signature is satisfied by this local missed-cadence/start-evidence rule", text)
        self.assertIn("An unexpected disabled canonical worker is degradation to repair", text)
        self.assertIn("does not authorize a sixth worker in either partition", text)
        self.assertIn("About 24 minutes remains the timed utilization target", text)
        self.assertIn("existing >=80% completion guard", text)
        self.assertIn("Utilization never requires creating a new work identity", text)
        self.assertIn("work identity follows the canonical shared issue-first rules", text)
        self.assertIn("A blocker changes scope; it does not end unrelated work", text)
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
