import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.memory_authority import (
    ROLE_ADVISORY,
    ROLE_CANONICAL,
    ROLE_USER,
    behavioral_authority,
    behavioral_context,
)
from tools.memory_bank import load_bank, recent_title_entries

ROOT = Path(__file__).resolve().parents[1]


class MemoryAuthorityFirewallTests(unittest.TestCase):
    def e(self, ident, *, kind="lesson", state="PROVEN", evidence=None, supersedes=None, ts="2026-08-27T10:00:00+03:00"):
        return {
            "id": ident,
            "timestamp": ts,
            "kind": kind,
            "scope": "memory",
            "tags": ["test"],
            "text": ident,
            "state": state,
            "evidence": evidence or [],
            "supersedes": supersedes or [],
        }

    def test_proven_is_not_behavioral_authority_by_itself(self):
        lesson = self.e("assistant-derived", state="PROVEN", evidence=["regression:incident-1"])
        auth = behavioral_authority(lesson)
        self.assertEqual(auth["role"], ROLE_ADVISORY)
        self.assertFalse(auth["may_change_behavior"])

    def test_user_sourced_fact_is_evidence_not_policy(self):
        entry = self.e("user-fact", kind="fact", evidence=["user-instruction:captured"])
        auth = behavioral_authority(entry)
        self.assertEqual(auth["role"], ROLE_ADVISORY)
        self.assertFalse(auth["may_change_behavior"])
        self.assertEqual(auth["basis"], "kind_not_behavioral")

    def test_direct_user_instruction_does_not_require_proven_state(self):
        entry = self.e("user-direct", kind="correction", state="PROVISIONAL", evidence=["user-instruction:captured"])
        auth = behavioral_authority(entry)
        self.assertEqual(auth["role"], ROLE_USER)
        self.assertTrue(auth["may_change_behavior"])
        self.assertEqual(auth["claim_state"], "PROVISIONAL")

    def test_explicit_user_instruction_is_behavior_authority_not_external_truth(self):
        entry = self.e("user", kind="correction", evidence=["user-instruction:current"])
        auth = behavioral_authority(entry)
        self.assertEqual(auth["role"], ROLE_USER)
        self.assertTrue(auth["may_change_behavior"])
        self.assertEqual(auth["authority_scope"], "behavior_only")

    def test_live_canonical_policy_is_behavior_authority(self):
        entry = self.e("policy", kind="decision", evidence=["agents-policy:repo/AGENTS.md"])
        auth = behavioral_authority(entry)
        self.assertEqual(auth["role"], ROLE_CANONICAL)
        self.assertTrue(auth["may_change_behavior"])

    def test_proven_derived_lesson_cannot_override_provisional_direct_user_instruction(self):
        direct = self.e("direct", kind="correction", state="PROVISIONAL", evidence=["user-instruction:current"], ts="2026-08-20T10:00:00+03:00")
        derived = self.e("derived", kind="lesson", state="PROVEN", evidence=["regression:incident"], ts="2026-08-27T10:00:00+03:00")
        selected = behavioral_context([derived, direct])
        self.assertEqual([e["id"] for e in selected], ["direct"])

    def test_user_authority_precedes_canonical_and_advisory_is_excluded(self):
        user = self.e("user", kind="correction", evidence=["user-instruction:current"], ts="2026-08-20T10:00:00+03:00")
        policy = self.e("policy", kind="decision", evidence=["repo-policy:AGENTS.md"], ts="2026-08-27T10:00:00+03:00")
        lesson = self.e("lesson", evidence=["regression:incident"])
        self.assertEqual([e["id"] for e in behavioral_context([lesson, policy, user])], ["user", "policy"])

    def test_superseded_policy_candidate_cannot_survive_firewall(self):
        wrong = self.e("wrong", state="PROVISIONAL")
        correction = self.e("correct", kind="correction", evidence=["user-instruction:current"], supersedes=["wrong"])
        selected = behavioral_context([wrong, correction])
        self.assertEqual([e["id"] for e in selected], ["correct"])

    def test_real_security_warning_incident_is_governed_correctly(self):
        entries = load_bank()
        old = next(e for e in entries if e["id"] == "mem-20260827-afce2baf")
        correction = next(e for e in entries if e["id"] == "mem-20260827-9a770b5b")
        self.assertFalse(behavioral_authority(old)["may_change_behavior"])
        self.assertEqual(behavioral_authority(old)["role"], ROLE_ADVISORY)
        self.assertTrue(behavioral_authority(correction)["may_change_behavior"])
        self.assertEqual(behavioral_authority(correction)["role"], ROLE_USER)
        selected_ids = {e["id"] for e in behavioral_context(entries)}
        self.assertNotIn(old["id"], selected_ids)
        self.assertIn(correction["id"], selected_ids)

    def test_expired_user_instruction_does_not_remain_behavior_authority(self):
        expired = self.e("expired-user", kind="correction", evidence=["user-instruction:old"])
        expired["expires_at"] = "2026-08-01T00:00:00+03:00"
        self.assertEqual(behavioral_context([expired]), [])
        self.assertEqual(recent_title_entries([expired], limit=1), [])

    def test_recent_bootstrap_exposes_authority_label(self):
        user = self.e("user", kind="correction", evidence=["user-instruction:current"])
        recent = recent_title_entries([user], limit=1)
        self.assertEqual(recent[0]["authority"], ROLE_USER)

    def test_cli_search_exposes_authority_without_mutating_canonical_bank(self):
        before = (ROOT / "memory" / "memory-bank.jsonl").read_bytes()
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "memory_bank.py"), "search", "security warning incident", "--limit", "3"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
        hits = json.loads(proc.stdout.decode("utf-8"))
        self.assertTrue(all("behavioral_authority" in hit for hit in hits))
        after = (ROOT / "memory" / "memory-bank.jsonl").read_bytes()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
