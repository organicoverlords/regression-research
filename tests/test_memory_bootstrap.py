import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.chatgpt_bootstrap_artifact import (
    DEFAULT_LIBRARY_PATH,
    build_chatgpt_bootstrap_artifact,
    render_artifact_bytes,
    verify_artifact_copy,
    write_artifact_copy,
)
from tools.memory_authority import AUTHORITY_REGISTRY, behavioral_context
from tools.memory_bank import DEFAULT_BANK, build_startup_bootstrap, load_bank, recent_title_entries
from tools.memory_timeline import build_behavior_bootstrap, build_fresh_session_startup_contract


class MemoryBootstrapTests(unittest.TestCase):
    def test_bootstrap_contains_every_current_rule_without_history_payload(self):
        entries = load_bank()
        current = behavioral_context(entries)
        payload = build_behavior_bootstrap(entries)
        expected = {entry["id"]: entry["text"] for entry in current}
        actual = {
            item["id"]: item["text"]
            for item in [*payload["behavior_profile"], *payload["canonical_policy_profile"]]
        }
        self.assertEqual(actual, expected)
        self.assertTrue(payload["contract"]["complete_behavior_semantics"])
        self.assertIn("behavior/policy load only", payload["contract"]["completion_boundary"])
        self.assertFalse(payload["contract"]["history_included"])
        self.assertFalse(payload["contract"]["live_status_included"])
        self.assertIn("assistant must close the live-status gap", payload["contract"]["live_status_gap_owner"])
        self.assertNotIn("only when the task needs them", payload["contract"]["follow_up"])
        self.assertIn("before the first substantive response", payload["contract"]["follow_up"])
        self.assertNotIn("recent_events", payload)
        self.assertNotIn("projects", payload)

    def test_bootstrap_carries_fresh_session_operating_cycle_without_turning_rehydration_into_a_loop(self):
        payload = build_behavior_bootstrap(load_bank())
        startup = payload["fresh_session_startup"]
        self.assertIn("fresh normal conversation only", startup["applies"])
        self.assertIn("must not retrigger this sweep", startup["rehydration"])
        self.assertIn("first user message itself triggers startup", startup["wake_up_semantics"])
        self.assertIn("first substantive response", startup["response_gate"])
        self.assertEqual(startup["startup_sequence"], ["behavior_bootstrap", "recent_memory_glance", "live_orientation", "response"])
        self.assertIn("up to 20", startup["recent_memory_glance"])
        self.assertIn("after the bounded recent-memory glance", startup["live_orientation"])
        self.assertIn("scheduled-worker state/recent runs", startup["live_orientation"])
        self.assertIn("recent meaningful commits/PRs/checks", startup["live_orientation"])
        self.assertIn("stay quiet about the sweep", startup["orientation_reporting"])
        self.assertIn("repair or contain it first", startup["anomaly_handling"])
        self.assertIn("re-check the relevant live sources", startup["current_status_refresh"])
        self.assertIn("immediately before answering", startup["worker_status_truth"])
        self.assertIn("zero positive weight", startup["worker_status_truth"])
        self.assertIn("claim timestamps may delimit", startup["worker_progress_truth"])
        self.assertIn("actual work", startup["worker_progress_truth"])
        self.assertIn("never present coordinator active", startup["worker_status_reporting"])
        self.assertEqual(
            startup["authority_cross_references"],
            ["assistant-orchestration/user-burden", "assistant-orchestration/tool-availability"],
        )
        self.assertIn("lead with the fire", startup["startup_report"])
        self.assertIn("status dump is never task completion", startup["continuation"])
        root = Path(__file__).resolve().parents[1]
        self.assertNotIn("source_contract", startup)
        self.assertFalse((root / "04 Operating Contracts/fresh-chat-startup-contract.json").exists())
        self.assertTrue((root / startup["documentation"]).is_file())
        self.assertTrue((root / startup["personal_instructions_bridge"]).is_file())

    def test_fresh_session_startup_is_bootstrap_owned_not_an_external_contract(self):
        with patch("tools.memory_timeline.Path.read_text", side_effect=AssertionError("external startup contract read")):
            startup = build_fresh_session_startup_contract()
        self.assertEqual(startup["startup_sequence"], ["behavior_bootstrap", "recent_memory_glance", "live_orientation", "response"])
        self.assertNotIn("source_contract", startup)

    def test_personal_instructions_bridge_requires_pre_response_live_orientation(self):
        bridge = (Path(__file__).resolve().parents[1] / "04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt").read_text(encoding="utf-8")
        self.assertIn("before the first substantive answer", bridge)
        self.assertIn("recent_memory_glance", bridge)
        self.assertIn("up to 20", bridge)
        self.assertIn("Do this even for a greeting", bridge)
        self.assertIn("Do not decide the scan is unnecessary before acquiring it", bridge)
        self.assertIn("If the bounded scan is clean, stay quiet about it", bridge)
        self.assertIn("Re-check relevant live repo/coordinator/worker/CI/runtime state", bridge)
        self.assertIn("inspect current execution immediately before answering", bridge)
        self.assertIn("zero positive weight", bridge)
        self.assertIn("claim timestamps may delimit", bridge)
        self.assertIn(DEFAULT_LIBRARY_PATH, bridge)
        self.assertIn("transport fallback, not a second behavioral authority", bridge)
        self.assertIn("continue from current user instruction", bridge)
        self.assertIn("/Agent Bootstrap/agents.md", bridge)
        self.assertIn("legacy `chatgpt-memory-seed.md`", bridge)

    def test_distribution_contract_requires_single_variable_live_promotion_canary(self):
        contract = (Path(__file__).resolve().parents[1] / "04 Operating Contracts/chatgpt-bootstrap-distribution.md").read_text(encoding="utf-8")
        self.assertIn("landed Vault revision", contract)
        self.assertIn("restorable before snapshot", contract)
        self.assertIn("Change one live variable at a time", contract)
        self.assertIn("instruction-delivery-canary.json", contract)
        self.assertIn("same-model fresh-chat", contract)
        self.assertIn("byte-exact `PROVEN` verification", contract)
        self.assertIn("Restore the previous Library bytes", contract)
        self.assertIn("does not make Library a semantic authority", contract)

    def test_generated_distribution_is_exact_bootstrap_with_source_provenance(self):
        artifact = build_chatgpt_bootstrap_artifact()
        self.assertEqual(artifact["artifact_schema_version"], 1)
        self.assertEqual(artifact["library_path"], DEFAULT_LIBRARY_PATH)
        entries = load_bank()
        self.assertEqual(artifact["payload"], build_startup_bootstrap(entries))
        self.assertEqual(artifact["payload"]["recent_memory_glance"]["entries"], recent_title_entries(entries, limit=20))
        self.assertLessEqual(len(artifact["payload"]["recent_memory_glance"]["entries"]), 20)
        self.assertTrue(artifact["payload"]["contract"]["complete_behavior_semantics"])
        self.assertFalse(artifact["payload"]["contract"]["history_included"])
        self.assertFalse(artifact["payload"]["contract"]["live_status_included"])

        for key, path in (("behavior_bank", DEFAULT_BANK), ("authority_registry", AUTHORITY_REGISTRY)):
            data = path.read_bytes()
            descriptor = artifact["source"][key]
            self.assertEqual(descriptor["bytes"], len(data))
            self.assertEqual(descriptor["sha256"], hashlib.sha256(data).hexdigest().upper())

        self.assertEqual(render_artifact_bytes(), render_artifact_bytes())

    def test_generated_distribution_verification_is_byte_exact(self):
        expected = render_artifact_bytes()
        with tempfile.TemporaryDirectory() as td:
            copy = Path(td) / "chatgpt-bootstrap.json"
            copy.write_bytes(expected)
            proven = verify_artifact_copy(copy)
            self.assertEqual(proven["status"], "PROVEN")
            self.assertEqual(proven["expected_sha256"], proven["actual_sha256"])
            self.assertEqual(proven["expected_bytes"], proven["actual_bytes"])

            copy.write_bytes(expected + b" ")
            mismatch = verify_artifact_copy(copy)
            self.assertEqual(mismatch["status"], "MISMATCH")
            self.assertNotEqual(mismatch["expected_sha256"], mismatch["actual_sha256"])

    def test_generated_distribution_publish_preserves_last_good_copy_on_replace_failure(self):
        original = b"last-known-good\n"
        replacement = render_artifact_bytes()
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "chatgpt-bootstrap.json"
            output.write_bytes(original)
            with patch("tools.chatgpt_bootstrap_artifact.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_artifact_copy(output, replacement)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(list(output.parent.glob(f".{output.name}.*.tmp")), [])

    def test_bootstrap_uses_current_recurring_worker_recovery_rule(self):
        payload = build_behavior_bootstrap(load_bank())
        active = {item["id"]: item["text"] for item in payload["behavior_profile"]}
        self.assertIn("mem-20260830-31beca08", active)
        for superseded in (
            "mem-20260830-fc6b5bba",
            "mem-20260830-767675cf",
            "mem-20260830-a2f3f2fe",
            "mem-20260829-d3594411",
            "mem-20260829-bf3bcb41",
            "mem-20260829-1f6d75a4",
        ):
            self.assertNotIn(superseded, active)
        rule = active["mem-20260830-31beca08"]
        self.assertIn("hard maximum of five enabled workers total", rule)
        self.assertIn("never create or keep a sixth enabled recurring worker", rule)
        self.assertIn("one-for-one replacement", rule)
        self.assertIn("refresh/re-discovery/reload is repeatable", rule)
        self.assertIn("no one-refresh ceiling or fixed failure-count cutoff", rule)
        self.assertIn("Workers never administer their own or sibling recurrence", rule)

        contract = (Path(__file__).resolve().parents[1] / "04 Operating Contracts/fresh-worker-generation-launch.md").read_text(encoding="utf-8")
        self.assertIn("Five is a hard maximum for the recurring worker fleet", contract)
        self.assertIn("temporary sixth", contract)
        self.assertIn("at most five total enabled workers", contract)
        self.assertIn("Replacement is one-for-one at the cap", contract)
        self.assertIn("status first; replace only proven-bad slots", contract)
        self.assertIn("schedule Worker 1 once with enough runway", contract)
        self.assertIn("Go work; do not idle or re-arm", contract)
        self.assertIn("A failed first launch replaces only the failed slot", contract)
        self.assertIn("do not create a verifier timer as a substitute", contract)
        self.assertIn("repeatable, explicitly allowed, and may be mandatory many times", contract)
        self.assertIn("Do not impose a one-refresh ceiling or a fixed failure-count cutoff", contract)
        self.assertIn("One bad worker is not evidence that all five are bad", contract)
        self.assertNotIn("perform one supported tool refresh/re-discovery/reload", contract)

        template = (Path(__file__).resolve().parents[1] / "templates/P3-V2-SWARM-TEMPLATE.md").read_text(encoding="utf-8-sig")
        self.assertIn("fresh five-worker P3 V2 generations", template)
        self.assertIn("Exactly five recurring workers per fresh generation", template)
        self.assertIn("Five is also the hard fleet cap", template)
        self.assertIn("Never have a sixth enabled recurring worker", template)
        self.assertIn("Workers 2-5 are armed in the same setup pass as Worker 1", template)
        self.assertIn("Preserve Workers 2-5 unless current evidence shows the whole generation shares the defect", template)
        self.assertIn("Refresh/re-discovery/reload is repeatable, explicitly allowed, and may be mandatory many times", template)
        self.assertIn("there is no one-refresh ceiling or fixed failure-count cutoff", template)
        self.assertNotIn("third separated failure including that post-refresh retry", template)
        self.assertNotIn("Exactly four recurring workers per fresh generation", template)
        self.assertNotIn("fresh four-worker generation", template)
        self.assertIn("admitted target worktree's `AGENTS.md`", template)
        self.assertIn("Treat `origin/main` as convergence context, not as a substitute for the worktree-local repository contract", template)
        self.assertNotIn("origin/main:AGENTS.md", template)
        self.assertNotIn("origin/main:docs/WORK_COORDINATION.md", template)
        self.assertNotIn("origin/main:docs/v2/WORKER_START_HERE.md", template)

    def test_startup_bootstrap_fits_plugin2_read_window(self):
        rendered = json.dumps(build_startup_bootstrap(load_bank()), ensure_ascii=False)
        self.assertLessEqual(len(rendered), 32000)
        self.assertIn("recent_memory_glance", rendered)


if __name__ == "__main__":
    unittest.main()
