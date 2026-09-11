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
        self.assertIn("Each recurring subscription partition has a hard maximum of five workers", text)
        self.assertIn("the two known partitions permit up to ten recurring workers total", text)
        self.assertIn("Never create or enable a sixth worker inside either partition", text)

        self.assertIn("The scheduler provides recurrence only", text)
        self.assertIn("Use current direction and live state; task memory is conditional evidence", text)
        self.assertIn("memory_bank.py context <query>", text)
        self.assertIn("only when a specific historical fact", text)
        self.assertIn("memory_bank.py timeline <query>", text)
        self.assertIn("memory/timeline remains conditional rather than mandatory ceremony", text)
        self.assertIn("Historical memory/timeline is evidence, never current truth", text)
        self.assertNotIn("even when the task appears new", text)
        self.assertNotIn("run both targeted context and timeline", text)
        self.assertIn("Do not turn this into a broad Vault scan", text)
        self.assertNotIn("Do not make Atlas, Vault, reports, history, or scheduler metadata a generic startup gate", text)
        self.assertIn("Recurring workers observe fleet health but never administer scheduler state", text)
        self.assertIn("must never administer itself", text)
        self.assertIn("authorize no scheduler write by that worker", text)
        self.assertIn("belongs to the supervising/manual ChatGPT session or explicit operator handoff", text)
        self.assertIn("About 24 minutes remains the timed utilization target", text)
        self.assertIn("existing >=80% completion guard", text)
        self.assertIn("Utilization never requires creating a new work identity", text)
        self.assertIn("work identity follows the canonical shared issue-first rules", text)
        self.assertIn("A blocker changes route; it does not end unrelated work", text)
        self.assertIn("Scope, repository, project, issue, branch, or worktree boundaries constrain relevance and collision safety", text)
        self.assertIn("exhausting one is never itself a yield condition", text)
        self.assertIn("actual platform/tool/safety/authorization/unrecoverable external limit", text)
        self.assertIn("lack of ready work inside an inferred scope does not qualify", text)
        self.assertNotIn("no safe in-scope contribution", text)
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
