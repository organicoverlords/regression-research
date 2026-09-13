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
        self.assertIn("Use current direction and live state; unified `find` is the first discovery surface", text)
        self.assertIn("memory_bank.py context <query>", text)
        self.assertIn("at most one `timeline <query>` only as drill-down", text)
        self.assertIn("when a concrete historical fact remains materially unknown", text)
        self.assertIn("Historical search evidence is never current truth", text)
        self.assertNotIn("task memory is conditional evidence", text)
        self.assertNotIn("memory/timeline remains conditional rather than mandatory ceremony", text)
        self.assertIn("Every recurring worker is also a bounded same-partition peer-recovery orchestrator", text)
        self.assertNotIn("Recurring workers observe fleet health but never administer scheduler state", text)
        self.assertIn("must never administer itself", text)
        self.assertIn("one idempotent `is_enabled=true`", text)
        self.assertIn("Supervising/manual ChatGPT or explicit operator handoff remains a fallback", text)
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
        self.assertIn("Last-resort Library Inbox durability", text)
        self.assertNotIn("first-launch proof", text.lower())

    def test_timed_worker_current_report_is_lifecycle_snapshot_not_live_progress(self):
        contract = (ROOT / "04 Operating Contracts/fresh-worker-generation-launch.md").read_text(encoding="utf-8")
        self.assertIn("The `current` path is a run-lifecycle location, not live progress telemetry", contract)
        self.assertIn("the RUNNING file begins as the start snapshot", contract)
        self.assertIn("Update the current report at natural checkpoints", contract)
        self.assertIn("do not infer continuous activity, liveness, or current progress", contract)

        topology = json.loads((ROOT / "04 Operating Contracts/chatgpt-swarm-topology.json").read_text(encoding="utf-8"))
        authority = topology["subscriptions"]["S2"]["enabled_state_authority"]
        self.assertIn("run-lifecycle start/finalization evidence only", authority)
        self.assertIn("do not prove current liveness, in-run progress, or scheduler flags", authority)
        self.assertNotIn("live worker reports prove recent execution", authority)

if __name__ == "__main__":
    unittest.main()
