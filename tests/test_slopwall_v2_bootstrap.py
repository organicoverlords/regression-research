from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.stack_atlas import _bootstrap_critical_guidance, _bootstrap_slopwall_contract


V2_RULES = (
    "response/task-quality regression investigation\n"
    "Treat the immediately preceding assistant reply/action or repair attempt as the failed boundary\n"
    "which governing user/system/shared rules or evidence were loaded or otherwise available\n"
    "the first supported divergence\n"
    "rule violation, rule missed/not loaded, rule gap/conflict, authority selection, or ordinary reasoning/action selection\n"
    "Expose a bounded useful diagnosis to the user\n"
    "materially answer/execute the inherited objective better\n"
    "incident record, replay fixture, bounded score/confidence\n"
    "searchable memory pointer, and behavior-contract review\n"
    "Capture is visible-context only\n"
    "never load, reconstruct, export, or backfill the whole conversation\n"
    "`incident report`, when the user uses it as a command about the preceding assistant/system failure, starts the **same V2 behavior-incident loop**\n"
    "A meta-reference or question about the phrase `incident report` is not a trigger\n"
)

V2_AGENTS = (
    "explicit `slopwall` and command-form `incident report` enter the V2 behavior-incident loop\n"
    "first establish the immediately preceding failed reply/action/repair as the failure boundary\n"
    "Give the user the bounded useful diagnosis\n"
    "then materially repair/resume the inherited objective\n"
    "incident record/report, replay fixture, bounded score/confidence or `UNSCORABLE`\n"
    "Raw capture is `VISIBLE_CONTEXT_ONLY`\n"
    "Never load/reconstruct/backfill the whole conversation just to complete an incident\n"
    "If another corrective trigger arrives before closure, make the failed repair a linked child event\n"
)

LEGACY_RULES = (
    "`slopwall` is a **mandatory correction-and-learning incident**\n"
    "re-read this canonical Slopwall rule and the matching AGENTS.md correction owner before finalizing the correction\n"
    "compare the failed reply/action directly against the inherited objective\n"
    "identify the concrete core proposition, decision, action, or evidence the user needed foregrounded\n"
    "identify what displaced that core\n"
    "infer the best-supported mechanism or decision failure\n"
    "derive one reusable prevention lesson\n"
    "persist one compact durable correction\n"
    "The durable correction is mandatory for literal `slopwall`\n"
    "The durable correction must name the lost core and the displacement\n"
    "A slopwall is not defined by length\n"
)

LEGACY_AGENTS = (
    "literal `slopwall` additionally requires a bounded durable learning loop\n"
    "re-read the canonical Slopwall rule plus this correction owner\n"
    "identify the lost core proposition/decision/action/evidence and what displaced it\n"
    "The Slopwall record is mandatory\n"
    "do not store merely `be concise`, `answer better`\n"
    "bounded uncertainty instead of fabricating a root cause\n"
    "after durability is secured, continue or finish the inherited task\n"
)


class SlopwallV2BootstrapTests(unittest.TestCase):
    def test_behavior_incident_contract_supports_v2_and_legacy_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "RULES.md").write_text(V2_RULES, encoding="utf-8")
            (root / "AGENTS.md").write_text(V2_AGENTS, encoding="utf-8")
            contract = _bootstrap_slopwall_contract(root)
            self.assertEqual(contract["status"], "ENFORCED")
            self.assertEqual(contract["version"], "V2")
            self.assertEqual(contract["triggers"], ["slopwall", "incident_report"])
            self.assertIn("VISIBLE_CONTEXT_ONLY", contract["capture"])
            self.assertIn("no_full_conversation_reload_or_backfill", contract["capture"])
            self.assertIn("failed_boundary", contract["process"])
            self.assertIn("inspect_governing_guidance_and_evidence", contract["process"])
            self.assertIn("bounded_user_visible_diagnosis", contract["process"])
            self.assertIn("repair_inherited_objective", contract["process"])
            self.assertIn("persist_incident_replay_score_memory_contract_review", contract["process"])
            self.assertIn("repeated_trigger_links_failed_repair", contract["process"])

            (root / "RULES.md").write_text(LEGACY_RULES, encoding="utf-8")
            (root / "AGENTS.md").write_text(LEGACY_AGENTS, encoding="utf-8")
            legacy = _bootstrap_slopwall_contract(root)
            self.assertEqual(legacy["status"], "ENFORCED")
            self.assertEqual(legacy["version"], "LEGACY_V84")
            self.assertEqual(legacy["triggers"], ["slopwall"])
            self.assertIn("legacy accepted only until", legacy["transition"])

            (root / "AGENTS.md").write_text("partial behavior guidance\n", encoding="utf-8")
            legacy_drift = _bootstrap_slopwall_contract(root)
            self.assertEqual(legacy_drift["status"], "DRIFTED")
            self.assertEqual(legacy_drift["version"], "LEGACY_V84")
            self.assertIn("AGENTS:reread", legacy_drift["missing"])
            self.assertIn("AGENTS:loop", legacy_drift["v2_missing"])

            (root / "RULES.md").write_text(V2_RULES, encoding="utf-8")
            v2_drift = _bootstrap_slopwall_contract(root)
            self.assertEqual(v2_drift["status"], "DRIFTED")
            self.assertEqual(v2_drift["version"], "V2")
            self.assertIn("AGENTS:loop", v2_drift["missing"])
            self.assertIn("AGENTS:learning_loop", v2_drift["legacy_missing"])

    def test_critical_guidance_tracks_contract_without_dropping_shared_correction(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "RULES.md").write_text(V2_RULES, encoding="utf-8")
            (root / "AGENTS.md").write_text(V2_AGENTS, encoding="utf-8")
            guidance = _bootstrap_critical_guidance(root)
            self.assertEqual(guidance["mode"], "HINT_ONLY")
            self.assertEqual(guidance["behavior_incident_version"], "V2")
            self.assertIn("failed boundary first", guidance["slopwall"])
            self.assertIn("visible context verbatim only", guidance["slopwall"])
            self.assertIn("never reload/backfill whole chat", guidance["slopwall"])
            self.assertIn("repeated corrective trigger links the failed repair", guidance["slopwall"])
            self.assertIn("same V2 loop", guidance["incident_report"])
            self.assertIn("meta-reference is not a trigger", guidance["incident_report"])
            self.assertIn("no unrelated mutation authority", guidance["incident_report"])
            self.assertIn("RULE_GAP vs RULE_VIOLATION", guidance["shared_correction"])
            self.assertIn("durable canonical proof", guidance["shared_correction"])

            (root / "RULES.md").write_text(LEGACY_RULES, encoding="utf-8")
            (root / "AGENTS.md").write_text(LEGACY_AGENTS, encoding="utf-8")
            legacy = _bootstrap_critical_guidance(root)
            self.assertEqual(legacy["behavior_incident_version"], "LEGACY_V84")
            self.assertIn("mandatory correction before final", legacy["slopwall"])
            self.assertIn("not a canonical trigger", legacy["incident_report"])
            self.assertIn("RULE_GAP vs RULE_VIOLATION", legacy["shared_correction"])


if __name__ == "__main__":
    unittest.main()
