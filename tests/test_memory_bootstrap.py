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

    def test_worker_contract_still_keeps_five_workers_and_no_self_admin(self):
        text = (ROOT / "04 Operating Contracts/fresh-worker-generation-launch.md").read_text(encoding="utf-8")
        self.assertIn("Five is a hard maximum for the recurring worker fleet", text)
        self.assertIn("continue through `plugin2`; Remote Desktop Commander and the hosted GitHub connector are not fallbacks", text)
        self.assertIn("route failure is local and recovery/fallback comes first", text)
        self.assertIn("Worker execution may never administer the scheduler", text)
        self.assertIn("For stack/infra work only", text)
        self.assertIn("Atlas is navigation, live sources are truth, and Vault/reports are history or projections", text)
        self.assertIn("Do not make Atlas or Vault a generic worker startup gate", text)
        self.assertIn("visual_proof_run", text)
        self.assertIn("visual_proof_reviewed_json", text)
        self.assertIn("PENDING_REVIEW", text)
        self.assertIn("Visual review never blocks the worker fleet", text)
        self.assertIn("automatic metrics", text)
        self.assertIn("about 24 minutes of useful execution budget", text)
        self.assertIn("duration is diagnostic data, never completion proof", text)
        self.assertIn("workers must not manually maintain aggregate metrics", text)
        self.assertIn("metrics.json.latest_reports", text)
        self.assertIn("stop_reason", text)
        self.assertIn("tool_failure_effect", text)
        self.assertIn("A transient failure does not justify stopping while supported fallback or safe useful work remains", text)
        self.assertIn(r"C:\P3Proofs", text)
        self.assertIn("current-snapshot key is the scheduler automation/task ID", text)
        self.assertIn("worker-reports/history/_reports/", text)
        self.assertIn("Current user-directed product outcome outranks owned-delivery cleanup", text)
        self.assertIn("Publishing a PR, pushing a commit, or passing local tests is progress, not completion", text)


if __name__ == "__main__":
    unittest.main()
