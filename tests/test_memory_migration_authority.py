import unittest

from tools.migrate_memory_bank import migrate_candidates


class SourceAuthorityConflictTests(unittest.TestCase):
    def e(self, id_, text, evidence, state="PROVEN", scope="global", supersedes=None):
        return {"id": id_, "timestamp": "2026-08-25T10:00:00+03:00", "kind": "lesson",
                "scope": scope, "tags": ["policy"], "text": text, "state": state,
                "evidence": evidence, "supersedes": supersedes or []}

    def test_recovery_only_cannot_supersede_live_canonical(self):
        canonical = self.e("canon", "Workers read AGENTS.md before mutating.",
                           ["shared-policy:SHARED-AGENT-POLICY.md"])
        seed = self.e("seed", "Workers load the bootstrap seed before mutating.",
                      ["legacy-seed:chatgpt-memory-seed.md"], supersedes=["canon"])
        out = migrate_candidates([canonical, seed])
        self.assertEqual(len(out), 2)
        rejected = next(x for x in out if x["id"] == "seed")
        self.assertEqual(rejected["supersedes"], [])

    def test_equal_authority_supersession_is_honoured(self):
        old = self.e("old", "Policy v1.3 wording.", ["shared-policy:v1.3"])
        new = self.e("new", "Policy v1.4 wording.", ["shared-policy:v1.4"], supersedes=["old"])
        out = migrate_candidates([old, new])
        self.assertEqual(next(x for x in out if x["id"] == "new")["supersedes"], ["old"])

    def test_higher_authority_supersession_is_honoured(self):
        historical = self.e("hist", "MCP paging is required first.",
                            ["claude-history:2026-08-24"])
        canonical = self.e("canon", "No bootstrap load is required.",
                           ["shared-policy:SHARED-AGENT-POLICY.md"], supersedes=["hist"])
        out = migrate_candidates([historical, canonical])
        self.assertEqual(next(x for x in out if x["id"] == "canon")["supersedes"], ["hist"])

    def test_rejected_supersession_is_audited_with_both_classes(self):
        canonical = self.e("canon", "Canonical claim.", ["shared-policy:x"])
        seed = self.e("seed", "Stale claim.", ["legacy-seed:y"], supersedes=["canon"])
        audit = []
        migrate_candidates([canonical, seed], audit=audit)
        record = next(r for r in audit if r["action"] == "supersession_rejected")
        self.assertEqual(record["candidate"], "seed")
        self.assertEqual(record["target"], "canon")
        self.assertEqual(record["source_class"], "RECOVERY_ONLY")
        self.assertEqual(record["target_class"], "LIVE_CANONICAL")
        self.assertTrue(record["reason"])

    def test_duplicate_collapse_is_audited(self):
        a = self.e("a", "Same durable statement.", ["incident:1"])
        b = self.e("b", "Same durable statement.", ["issue:7"])
        audit = []
        migrate_candidates([a, b], audit=audit)
        record = next(r for r in audit if r["action"] == "collapsed_duplicate")
        self.assertEqual(record["candidate"], "b")
        self.assertEqual(record["target"], "a")

    def test_every_candidate_produces_an_audit_record(self):
        candidates = [
            self.e("a", "First.", ["shared-policy:x"]),
            self.e("b", "First.", ["incident:2"]),
            self.e("c", "Second.", ["legacy-seed:z"], supersedes=["a"]),
        ]
        audit = []
        migrate_candidates(candidates, audit=audit)
        self.assertEqual({r["candidate"] for r in audit} & {"a", "b", "c"}, {"a", "b", "c"})

    def test_unresolvable_supersession_target_is_kept_but_audited(self):
        entry = self.e("only", "Refers to a bank entry not in this batch.",
                       ["shared-policy:x"], supersedes=["mem-elsewhere"])
        audit = []
        out = migrate_candidates([entry], audit=audit)
        self.assertEqual(out[0]["supersedes"], ["mem-elsewhere"])
        self.assertTrue(any(r["action"] == "supersession_unverified" for r in audit))

    def test_known_existing_entries_are_used_to_resolve_targets(self):
        existing = [self.e("canon", "Canonical.", ["shared-policy:x"])]
        seed = self.e("seed", "Stale.", ["legacy-seed:y"], supersedes=["canon"])
        out = migrate_candidates([seed], existing=existing)
        self.assertEqual(out[0]["supersedes"], [])


if __name__ == "__main__":
    unittest.main()


class DuplicateEvidenceEscalationTests(unittest.TestCase):
    def e(self, id_, text, evidence, supersedes=None):
        return {"id": id_, "timestamp": "2026-08-25T10:00:00+03:00", "kind": "lesson",
                "scope": "global", "tags": ["policy"], "text": text, "state": "PROVEN",
                "evidence": evidence, "supersedes": supersedes or []}

    def test_duplicate_evidence_cannot_elevate_a_low_authority_supersession(self):
        canon = self.e("canon", "Canonical policy claim.", ["shared-policy:SHARED-AGENT-POLICY.md"])
        low = self.e("low", "Same durable statement.", ["legacy-seed:seed.md"], supersedes=["canon"])
        dup = self.e("dup", "Same durable statement.", ["shared-policy:v1.4"])
        out = migrate_candidates([canon, low, dup])
        merged = next(x for x in out if x["id"] == "low")
        self.assertIn("shared-policy:v1.4", merged["evidence"])   # merge still happens
        self.assertEqual(merged["supersedes"], [])                # but does not license the claim

    def test_high_authority_supersession_survives_a_low_authority_duplicate(self):
        old = self.e("old", "Superseded wording.", ["shared-policy:v1.3"])
        high = self.e("high", "Same durable statement.", ["shared-policy:v1.4"], supersedes=["old"])
        junk = self.e("junk", "Same durable statement.", ["legacy-seed:seed.md"])
        out = migrate_candidates([old, high, junk])
        self.assertEqual(next(x for x in out if x["id"] == "high")["supersedes"], ["old"])

    def test_each_assertion_judged_at_its_own_asserters_authority(self):
        canon = self.e("canon", "Canonical.", ["shared-policy:x"])
        old = self.e("old", "Old wording.", ["shared-policy:v1.3"])
        hi = self.e("hi", "Same statement.", ["shared-policy:v1.4"], supersedes=["old"])
        lo = self.e("lo", "Same statement.", ["legacy-seed:seed.md"], supersedes=["canon"])
        out = migrate_candidates([canon, old, hi, lo])
        merged = next(x for x in out if x["id"] == "hi")
        self.assertEqual(merged["supersedes"], ["old"])           # hi's own claim kept
        self.assertNotIn("canon", merged["supersedes"])           # lo's claim not licensed by hi
