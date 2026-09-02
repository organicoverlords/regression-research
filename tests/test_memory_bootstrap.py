import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.chatgpt_bootstrap_artifact import (
    DEFAULT_LIBRARY_PATH,
    build_chatgpt_bootstrap_artifact,
    publication_plan,
    render_artifact_bytes,
    verify_artifact_copy,
    write_artifact_copy,
)
from tools.memory_bank import build_startup_bootstrap, load_bank
from tools.stack_atlas import ATLAS_LIBRARY_PATH, render_library_atlas_bytes


ROOT = Path(__file__).resolve().parents[1]


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
        self.assertNotIn(DEFAULT_LIBRARY_PATH, text)

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
        self.assertIn(DEFAULT_LIBRARY_PATH, text)
        self.assertIn("legacy/recovery surfaces only", text)
        self.assertIn("Stack Atlas remains an operational map", text)
        self.assertIn("searchable history/notebook/evidence", text)
        self.assertNotIn("Library publisher worker contract", text)

    def test_generated_bootstrap_artifact_is_only_a_retired_tombstone(self):
        artifact = build_chatgpt_bootstrap_artifact()
        self.assertTrue(artifact["retired"])
        self.assertEqual(artifact["authority"], "NONE")
        self.assertEqual(artifact["library_path"], DEFAULT_LIBRARY_PATH)
        self.assertEqual(artifact["payload"]["status"], "RETIRED")
        self.assertNotIn("behavior", artifact["payload"])
        self.assertNotIn("policy", artifact["payload"])
        self.assertLess(len(render_artifact_bytes()), 1000)

    def test_publication_plan_refuses_bootstrap_and_preserves_atlas(self):
        plan = publication_plan()
        self.assertEqual(plan["status"], "RETIRED_NO_LIBRARY_ARTIFACT")
        self.assertFalse(plan["publish"])
        self.assertEqual(plan["library_path"], DEFAULT_LIBRARY_PATH)
        self.assertEqual(plan["stack_atlas"]["library_path"], ATLAS_LIBRARY_PATH)
        self.assertEqual(plan["stack_atlas"]["bytes"], len(render_library_atlas_bytes()))

    def test_retired_artifact_verification_remains_byte_exact(self):
        expected = render_artifact_bytes()
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / "chatgpt-bootstrap.json"
            copy.write_bytes(expected)
            self.assertEqual(verify_artifact_copy(copy)["status"], "PROVEN")
            copy.write_bytes(expected + b" ")
            self.assertEqual(verify_artifact_copy(copy)["status"], "MISMATCH")

    def test_atomic_writer_preserves_existing_copy_on_replace_failure(self):
        original = b"last-known-good\n"
        replacement = render_artifact_bytes()
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "chatgpt-bootstrap.json"
            output.write_bytes(original)
            with patch("tools.chatgpt_bootstrap_artifact.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_artifact_copy(output, replacement)
            self.assertEqual(output.read_bytes(), original)

    def test_shared_policy_treats_vault_as_optional_history(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("### Navigation minimap", text)
        self.assertIn("Vault is history/evidence", text)
        self.assertIn("never recursively scan Vault or make it a startup gate", text)
        self.assertNotIn("memory_bank.py bootstrap", text)

    def test_worker_contract_still_keeps_five_workers_and_no_self_admin(self):
        text = (ROOT / "04 Operating Contracts/fresh-worker-generation-launch.md").read_text(encoding="utf-8")
        self.assertIn("Five is a hard maximum for the recurring worker fleet", text)
        self.assertIn("repeatable, explicitly allowed, and may be mandatory many times", text)
        self.assertIn("Worker execution may never administer the scheduler", text)
        self.assertIn("stack_atlas_glance", text)
        self.assertIn("visual_proof_run", text)
        self.assertIn("visual_proof_reviewed_json", text)
        self.assertIn("PENDING_REVIEW", text)
        self.assertIn("Visual review never blocks the worker fleet", text)
        self.assertIn("latest snapshot, not the log", text)
        self.assertIn("worker-reports/history/<WorkerName>/", text)
        self.assertIn("Finish owned delivery before opening more inventory", text)
        self.assertIn("Publishing a PR, pushing a commit, or passing local tests is progress, not completion", text)


if __name__ == "__main__":
    unittest.main()
