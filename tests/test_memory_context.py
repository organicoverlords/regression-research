import unittest

from tools.memory_context import build_context_pack


class MemoryContextPackTests(unittest.TestCase):
    def test_separates_behavior_memory_and_history(self):
        hits = [
            {
                "id": "u1", "kind": "correction", "scope": "global", "state": "PROVEN",
                "title": "User rule", "text": "Preserve the inherited task.", "evidence": ["user-instruction:x"],
                "behavioral_authority": {"role": "USER_EXPLICIT", "may_change_behavior": True, "authority_scope": "behavior_only"},
            },
            {
                "id": "m1", "kind": "lesson", "scope": "p3", "state": "PROVEN",
                "title": "P3 lesson", "text": "Old build state is not live truth.", "evidence": ["incident:x"],
                "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False, "authority_scope": "evidence_only"},
            },
            {
                "id": "conversation-corpus-summary", "source_class": "HISTORICAL_CONTEXT",
                "retrieval_role": "AGGREGATE_SIGNAL", "text": "14 matches across 3 conversations.",
                "matching_messages": 14, "matching_conversations": 3,
            },
            {
                "conversation_id": "c1", "title": "Old chat", "role": "user", "created_at": "2026-08-20T00:00:00Z",
                "match": "This was the old observation.", "context_before": "must not leak", "context_after": "must not leak",
                "sources": ["source:a"], "source_class": "HISTORICAL_CONTEXT", "retrieval_role": "EVIDENCE_EXCERPT",
            },
        ]
        pack = build_context_pack("work on p3", hits)
        self.assertEqual([x["id"] for x in pack["behavior_authority"]], ["u1"])
        self.assertEqual([x["id"] for x in pack["durable_memory"]], ["m1"])
        self.assertEqual(len(pack["historical_evidence"]), 2)
        self.assertEqual(pack["omitted"], {
            "provisional_matches": 0, "status_matches": 0,
            "unanchored_matches": 0, "project_mismatch_matches": 0, "role_mismatch_matches": 0,
        })
        self.assertNotIn("context_before", pack["historical_evidence"][1])
        self.assertNotIn("context_after", pack["historical_evidence"][1])
        self.assertEqual(pack["historical_evidence"][1]["authority"], "ADVISORY_EVIDENCE")

    def test_provisional_and_status_do_not_enter_default_durable_context(self):
        hits = [
            {"id": "p", "kind": "lesson", "scope": "global", "state": "PROVISIONAL", "text": "maybe", "evidence": [],
             "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False}},
            {"id": "s", "kind": "status", "scope": "p3", "state": "PROVEN", "text": "13 jobs queued", "evidence": ["github:x"],
             "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False}},
        ]
        pack = build_context_pack("p3 queue", hits)
        self.assertEqual(pack["durable_memory"], [])
        self.assertEqual(pack["omitted"], {
            "provisional_matches": 1, "status_matches": 1,
            "unanchored_matches": 0, "project_mismatch_matches": 0, "role_mismatch_matches": 0,
        })

    def test_unanchored_proven_memory_is_not_injected(self):
        hit = {
            "id": "m", "kind": "lesson", "scope": "global", "state": "PROVEN",
            "text": "assistant asserted this without a source", "evidence": [],
            "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False},
        }
        pack = build_context_pack("ordinary task", [hit])
        self.assertEqual(pack["durable_memory"], [])
        self.assertEqual(pack["omitted"]["unanchored_matches"], 1)

    def test_named_project_excludes_other_named_project_memory(self):
        p3 = {
            "id": "p3", "kind": "lesson", "scope": "p3/build", "state": "PROVEN",
            "text": "P3 build lesson", "evidence": ["incident:p3"],
            "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False},
        }
        tiny = {
            "id": "tiny", "kind": "lesson", "scope": "tiny3d/build", "state": "PROVEN",
            "text": "Tiny3D build lesson", "evidence": ["incident:tiny3d"],
            "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False},
        }
        global_note = {
            "id": "global", "kind": "lesson", "scope": "global", "state": "PROVEN",
            "text": "Evidence before claims", "evidence": ["incident:global"],
            "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False},
        }
        pack = build_context_pack("work on p3", [tiny, global_note, p3])
        self.assertEqual(pack["selectors"]["projects"], ["p3"])
        self.assertEqual([x["id"] for x in pack["durable_memory"]], ["global", "p3"])
        self.assertEqual(pack["omitted"]["project_mismatch_matches"], 1)

    def test_explicit_role_excludes_other_explicit_role_memory(self):
        worker = {
            "id": "worker", "kind": "lesson", "scope": "p3/worker", "state": "PROVEN",
            "text": "Worker-local rule", "evidence": ["incident:worker"],
            "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False},
        }
        orchestrator = {
            "id": "orch", "kind": "lesson", "scope": "p3/orchestrator", "state": "PROVEN",
            "text": "Orchestrator-local rule", "evidence": ["incident:orchestrator"],
            "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False},
        }
        pack = build_context_pack("p3 orchestrator status", [worker, orchestrator])
        self.assertEqual(pack["selectors"], {"projects": ["p3"], "roles": ["orchestrator"]})
        self.assertEqual([x["id"] for x in pack["durable_memory"]], ["orch"])
        self.assertEqual(pack["omitted"]["role_mismatch_matches"], 1)

    def test_context_exposes_compact_classification(self):
        hit = {
            "id": "classified", "timestamp": "2026-08-27T10:00:00+03:00",
            "kind": "lesson", "scope": "p3/build", "project": "p3", "tags": [],
            "text": "P3 build lesson", "state": "PROVEN", "evidence": ["report:x"], "supersedes": [],
        }
        from tools.memory_authority import annotate_memory
        pack = build_context_pack("p3 build", [annotate_memory(hit)])
        record = pack["durable_memory"][0]
        self.assertEqual(record["primary_domain"], "project:p3")
        self.assertEqual(record["semantic_category"], "PROJECT_LESSON")
        self.assertEqual(record["durability"], "DURABLE")

    def test_blank_query_rejected(self):
        with self.assertRaises(ValueError):
            build_context_pack("   ", [])

    def test_hard_budget_drops_history_before_authority(self):
        behavior = {
            "id": "u1", "kind": "preference", "scope": "global", "state": "PROVEN",
            "title": "User rule", "text": "A" * 650, "evidence": ["user-instruction:x"],
            "behavioral_authority": {"role": "USER_EXPLICIT", "may_change_behavior": True, "authority_scope": "behavior_only"},
        }
        current = {
            "id": "m1", "kind": "lesson", "scope": "p3", "state": "PROVEN",
            "title": "Current memory", "text": "B" * 650, "evidence": ["incident:x"],
            "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False, "authority_scope": "evidence_only"},
        }
        history = [
            {"conversation_id": f"c{i}", "title": "Old chat", "role": "assistant", "created_at": "2026-08-20T00:00:00Z",
             "match": "H" * 500, "sources": ["source:a"], "source_class": "HISTORICAL_CONTEXT", "retrieval_role": "EVIDENCE_EXCERPT"}
            for i in range(8)
        ]
        pack = build_context_pack("p3", [behavior, current, *history], max_chars=2000)
        self.assertTrue(pack["truncated"])
        self.assertEqual([x["id"] for x in pack["behavior_authority"]], ["u1"])
        self.assertLessEqual(pack["serialized_chars"], 2000)

    def test_long_memory_body_is_clipped(self):
        hit = {
            "id": "m", "kind": "lesson", "scope": "global", "state": "PROVEN",
            "text": "x" * 5000, "evidence": ["incident:x"],
            "behavioral_authority": {"role": "ADVISORY_EVIDENCE", "may_change_behavior": False},
        }
        pack = build_context_pack("test", [hit])
        self.assertLess(len(pack["durable_memory"][0]["text"]), 800)


if __name__ == "__main__":
    unittest.main()
