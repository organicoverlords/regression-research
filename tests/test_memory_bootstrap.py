import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.chatgpt_bootstrap_artifact import (
    CAPABILITY_POLICY_SOURCE,
    DEFAULT_LIBRARY_PATH,
    STACK_ATLAS_SOURCE,
    build_chatgpt_bootstrap_artifact,
    publication_plan,
    render_artifact_bytes,
    verify_artifact_copy,
    write_artifact_copy,
)
from tools.memory_authority import AUTHORITY_REGISTRY, behavioral_context
from tools.memory_bank import DEFAULT_BANK, build_startup_bootstrap, load_bank, recent_title_entries
from tools.memory_timeline import build_behavior_bootstrap, build_fresh_session_startup_contract
from tools.stack_atlas import ATLAS_LIBRARY_PATH, render_library_atlas_bytes


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
        self.assertIn("compact Atlas follows universally", payload["contract"]["completion_boundary"])
        self.assertFalse(payload["contract"]["history_included"])
        self.assertFalse(payload["contract"]["live_status_included"])
        self.assertIn("when the requested answer or mutation depends on them", payload["contract"]["live_status_gap_owner"])
        self.assertIn("no universal fresh-chat live scan", payload["contract"]["live_status_gap_owner"])
        self.assertIn("fetch only relevant missing context or live truth", payload["contract"]["follow_up"])
        self.assertNotIn("recent_events", payload)
        self.assertNotIn("projects", payload)

    def test_bootstrap_carries_fresh_session_operating_cycle_without_turning_rehydration_into_a_loop(self):
        payload = build_behavior_bootstrap(load_bank())
        startup = payload["fresh_session_startup"]
        self.assertIn("fresh normal conversation only", startup["applies"])
        self.assertIn("must not retrigger this sweep", startup["rehydration"])
        self.assertIn("first user message itself triggers startup", startup["wake_up_semantics"])
        self.assertIn("compact Atlas are universal startup context", startup["response_gate"])
        self.assertEqual(startup["startup_sequence"], ["behavior_delivery", "stack_atlas_glance", "relevant_context", "response"])
        self.assertIn("only when recent durable context is needed", startup["recent_memory_glance"])
        self.assertIn("otherwise skip it", startup["recent_memory_glance"])
        self.assertIn("Atlas before stack/infra reasoning/changes", startup["stack_atlas_glance"])
        self.assertIn("before judging relevance/blast radius", startup["stack_atlas_glance"])
        self.assertIn("reuse loaded schemas when valid", startup["tool_schema_discovery"])
        self.assertIn("prefer narrow discovery", startup["tool_schema_discovery"])
        self.assertIn("refresh when stale, changed, failed, or missing", startup["tool_schema_discovery"])
        compact_fresh = build_chatgpt_bootstrap_artifact()["payload"]["startup"]["fresh"]
        self.assertIn("Reuse valid schemas", compact_fresh)
        self.assertIn("refresh stale/failed/missing", compact_fresh)
        self.assertIn("inspect only the live facts", startup["live_orientation"])
        self.assertIn("no mandatory fresh-chat fleet/repo/worker/CI scan", startup["live_orientation"])
        self.assertIn("small status-independent edits", startup["live_orientation"])
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

    def test_fresh_chat_short_prompt_binds_to_inherited_context(self):
        fixture_path = Path(__file__).resolve().parent / "fixtures/fresh-chat-short-prompt-inherited-context.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        payload = build_behavior_bootstrap(load_bank())
        wake_up = payload["fresh_session_startup"]["wake_up_semantics"]
        for fragment in fixture["required_wake_up_fragments"]:
            self.assertIn(fragment, wake_up)
        active_text = "\n".join(item["text"] for item in payload["behavior_profile"])
        self.assertIn(fixture["required_behavior_fragment"], active_text)
        compact_fresh = build_chatgpt_bootstrap_artifact()["payload"]["startup"]["fresh"]
        for fragment in fixture["required_compact_fragments"]:
            self.assertIn(fragment, compact_fresh)
        lowered_bad = fixture["bad_response"].lower()
        for fragment in fixture["forbidden_bad_response_fragments"]:
            self.assertIn(fragment, lowered_bad)

    def test_fresh_session_startup_is_bootstrap_owned_not_an_external_contract(self):
        with patch("tools.memory_timeline.Path.read_text", side_effect=AssertionError("external startup contract read")):
            startup = build_fresh_session_startup_contract()
        self.assertEqual(startup["startup_sequence"], ["behavior_delivery", "stack_atlas_glance", "relevant_context", "response"])
        self.assertNotIn("source_contract", startup)

    def test_personal_instructions_bridge_keeps_startup_work_conditional(self):
        bridge = (Path(__file__).resolve().parents[1] / "04 Operating Contracts/chatgpt-personal-instructions-bootstrap.txt").read_text(encoding="utf-8")
        self.assertIn("acquire complete behavior once", bridge)
        self.assertIn("Consume the compact Stack Atlas on every fresh chat", bridge)
        self.assertIn("before deciding relevance or blast radius", bridge)
        self.assertIn("Recent-memory and other live-state reads remain conditional", bridge)
        self.assertIn("Reuse loaded tool/function schemas when valid", bridge)
        self.assertIn("normally five minutes", bridge)
        self.assertIn("zero positive weight", bridge)
        self.assertIn(DEFAULT_LIBRARY_PATH, bridge)
        self.assertIn("transport fallback cache", bridge)
        self.assertIn("retry", bridge)
        self.assertLess(bridge.index("memory_bank.py bootstrap"), bridge.index(DEFAULT_LIBRARY_PATH))
        self.assertNotIn("recent-titles --limit 20", bridge)
        self.assertNotIn("deep-lookup every relevant component", bridge)
        self.assertIn("reacquire behavior and compact Atlas once", bridge)

    def test_distribution_contract_requires_primary_library_publisher_acceptance(self):
        contract = (Path(__file__).resolve().parents[1] / "04 Operating Contracts/chatgpt-bootstrap-distribution.md").read_text(encoding="utf-8")
        self.assertIn("transport fallback cache", contract)
        self.assertIn("stack_atlas_glance", contract)
        self.assertIn("Stack Atlas entrypoint", contract)
        self.assertIn("retry it once through a compatible local execution route", contract)
        self.assertIn("Vault behavior bootstrap -> compact Stack Atlas -> relevant context -> response", contract)
        self.assertIn("compact Atlas is universal startup context", contract)
        self.assertIn("Library publisher worker contract", contract)
        self.assertIn("publication-plan", contract)
        self.assertIn("restorable previous copies", contract)
        self.assertIn("verify <copy>` to return `PROVEN`", contract)
        self.assertIn("green repository check must not be described as proof", contract)
        self.assertIn("do not require repeated Personal-Instructions edits", contract)

    def test_generated_distribution_is_compact_complete_bootstrap_with_source_provenance(self):
        artifact = build_chatgpt_bootstrap_artifact()
        self.assertEqual(artifact["artifact_schema_version"], 3)
        self.assertEqual(artifact["authority"], "Vault")
        self.assertEqual(artifact["library_path"], DEFAULT_LIBRARY_PATH)

        entries = load_bank()
        full = build_startup_bootstrap(entries)
        payload = artifact["payload"]
        self.assertTrue(payload["complete_behavior_semantics"])
        self.assertIn("USER_EXPLICIT", payload["profile_semantics"])
        self.assertIn("CANONICAL_POLICY", payload["profile_semantics"])
        self.assertEqual(payload["behavior"], [item["text"] for item in full["behavior_profile"]])
        self.assertEqual(payload["policy"], [item["text"] for item in full["canonical_policy_profile"]])
        self.assertEqual(payload["startup"]["sequence"], full["fresh_session_startup"]["startup_sequence"])
        self.assertEqual(payload["atlas"], full["stack_atlas_glance"])
        self.assertEqual(
            payload["recent"],
            [[item["timestamp"], item["title"]] for item in full["recent_memory_glance"]["entries"][:1]],
        )
        self.assertLessEqual(len(render_artifact_bytes()), 15_000)

        plan = publication_plan()
        for key, path in (
            ("behavior_bank", DEFAULT_BANK),
            ("authority_registry", AUTHORITY_REGISTRY),
            ("stack_atlas", STACK_ATLAS_SOURCE),
            ("capability_policy", CAPABILITY_POLICY_SOURCE),
        ):
            self.assertEqual(plan["source"][key], hashlib.sha256(path.read_bytes()).hexdigest().upper())

        self.assertEqual(render_artifact_bytes(), render_artifact_bytes())

    def test_publication_plan_exposes_exact_primary_library_delivery_target(self):
        plan = publication_plan()
        rendered = render_artifact_bytes()
        self.assertEqual(plan["status"], "EXPECTED_LIBRARY_ARTIFACT")
        self.assertEqual(plan["library_path"], DEFAULT_LIBRARY_PATH)
        self.assertEqual(plan["delivery_role"], "fallback")
        self.assertEqual(plan["canonical_authority"], "Vault")
        self.assertEqual(plan["bytes"], len(rendered))
        self.assertEqual(plan["sha256"], hashlib.sha256(rendered).hexdigest().upper())
        self.assertIn("byte-exact", plan["acceptance"])
        self.assertEqual(plan["stack_atlas"]["library_path"], ATLAS_LIBRARY_PATH)
        self.assertEqual(plan["stack_atlas"]["bytes"], len(render_library_atlas_bytes()))

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
        self.assertIn("stack_atlas_glance", contract)
        self.assertIn("deep-lookup every relevant Atlas component", contract)
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

    def test_bootstrap_rejects_invented_per_chat_behavior_contracts(self):
        fixture_path = Path(__file__).resolve().parent / "fixtures/no-false-per-chat-promises-regression.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8-sig"))
        entries = load_bank()
        payload = build_behavior_bootstrap(entries)
        active = {item["id"]: item["text"] for item in payload["behavior_profile"]}

        current_id = fixture["required_behavior_rule_id"]
        self.assertIn(current_id, active)
        self.assertNotIn(fixture["superseded_behavior_rule_id"], active)
        for fragment in fixture["required_rule_fragments"]:
            self.assertIn(fragment, active[current_id])

        source_entry = next(item for item in entries if item["id"] == current_id)
        for correction in fixture["user_corrections"]:
            self.assertIn(correction, source_entry["source_messages"])

    def test_startup_bootstrap_fits_plugin2_read_window(self):
        payload = build_startup_bootstrap(load_bank())
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        self.assertLessEqual(len(rendered), 32000)
        self.assertEqual(json.loads(rendered), payload)
        self.assertIn("recent_memory_glance", rendered)
        self.assertIn("stack_atlas_glance", rendered)


if __name__ == "__main__":
    unittest.main()
