import json
import unittest

from tools.memory_bank import annotate_memory
from tools.memory_context import build_context_pack


class MemoryContextPackTests(unittest.TestCase):
    @staticmethod
    def memory(ident, *, kind="lesson", scope="global", state="PROVEN", text="Evidence before claims", evidence=None, project=None):
        out = {
            "id": ident, "timestamp": "2026-08-27T10:00:00+03:00", "kind": kind,
            "scope": scope, "tags": [], "title": text, "text": text, "state": state,
            "evidence": list(evidence if evidence is not None else ["incident:test"]), "supersedes": [],
        }
        if project:
            out["project"] = project
        return annotate_memory(out)

    def test_separates_durable_memory_and_historical_conversation_evidence(self):
        user_wording = self.memory("u1", kind="correction", text="Preserve the inherited task.", evidence=["user-instruction:x"])
        project = self.memory("m1", scope="p3", text="Old build state is not live truth.")
        history = {
            "conversation_id": "c1", "title": "Old chat", "role": "user", "created_at": "2026-08-20T00:00:00Z",
            "match": "This was the old observation.", "context_before": "must not leak", "context_after": "must not leak",
            "sources": ["source:a"], "source_class": "HISTORICAL_CONTEXT", "retrieval_role": "EVIDENCE_EXCERPT",
        }
        pack = build_context_pack("work on p3", [user_wording, project, history])
        self.assertEqual([x["id"] for x in pack["durable_memory"]], ["u1", "m1"])
        self.assertEqual(len(pack["historical_evidence"]), 1)
        self.assertNotIn("behavior_authority", pack)
        self.assertNotIn("context_before", pack["historical_evidence"][0])
        self.assertNotIn("context_after", pack["historical_evidence"][0])

    def test_provisional_and_status_do_not_enter_default_durable_context(self):
        hits = [
            self.memory("p", state="PROVISIONAL", text="maybe", evidence=[]),
            self.memory("s", kind="status", scope="p3", text="13 jobs queued"),
        ]
        pack = build_context_pack("p3 queue", hits)
        self.assertEqual(pack["durable_memory"], [])
        self.assertEqual(pack["omitted"]["provisional_matches"], 1)
        self.assertEqual(pack["omitted"]["status_matches"], 1)

    def test_unanchored_proven_memory_is_not_injected(self):
        pack = build_context_pack("ordinary task", [self.memory("m", evidence=[])])
        self.assertEqual(pack["durable_memory"], [])
        self.assertEqual(pack["omitted"]["unanchored_matches"], 1)

    def test_named_project_excludes_other_named_project_memory(self):
        p3 = self.memory("p3", scope="p3/build", project="p3", text="P3 build lesson")
        tiny = self.memory("tiny", scope="tiny3d/build", project="tiny3d", text="Tiny3D build lesson")
        global_note = self.memory("global")
        pack = build_context_pack("work on p3", [tiny, global_note, p3])
        self.assertEqual(pack["selectors"]["projects"], ["p3"])
        self.assertEqual([x["id"] for x in pack["durable_memory"]], ["global", "p3"])
        self.assertEqual(pack["omitted"]["project_mismatch_matches"], 1)

    def test_explicit_role_excludes_other_explicit_role_memory(self):
        worker = self.memory("worker", scope="p3/worker", text="Worker-local evidence")
        orchestrator = self.memory("orch", scope="p3/orchestrator", text="Orchestrator-local evidence")
        pack = build_context_pack("p3 orchestrator status", [worker, orchestrator])
        self.assertEqual(pack["selectors"], {"projects": ["p3"], "roles": ["orchestrator"]})
        self.assertEqual([x["id"] for x in pack["durable_memory"]], ["orch"])
        self.assertEqual(pack["omitted"]["role_mismatch_matches"], 1)

    def test_context_exposes_compact_classification(self):
        pack = build_context_pack("p3 build", [self.memory("classified", scope="p3/build", project="p3", text="P3 build lesson")])
        record = pack["durable_memory"][0]
        self.assertEqual(record["primary_domain"], "project:p3")
        self.assertEqual(record["semantic_category"], "PROJECT_LESSON")
        self.assertEqual(record["durability"], "DURABLE")

    def test_recurrence_timeline_is_separate_non_authoritative_evidence(self):
        timeline = [{"thread_id": "scope:error", "event_count": 2, "events": [{"id": "a"}, {"id": "b"}]}]
        pack = build_context_pack("this error again", [], timeline=timeline)
        self.assertEqual(pack["timeline"], timeline)
        self.assertIn("chronology", pack["contract"]["timeline"])
        self.assertNotIn("behavior_authority", pack)

    def test_blank_query_rejected(self):
        with self.assertRaises(ValueError):
            build_context_pack("   ", [])

    def test_hard_budget_drops_history_before_durable_evidence(self):
        durable = self.memory("m1", scope="p3", text="B" * 650)
        history = [
            {"conversation_id": f"c{i}", "title": "Old chat", "role": "assistant", "created_at": "2026-08-20T00:00:00Z",
             "match": "H" * 500, "sources": ["source:a"], "source_class": "HISTORICAL_CONTEXT", "retrieval_role": "EVIDENCE_EXCERPT"}
            for i in range(8)
        ]
        pack = build_context_pack("p3", [durable, *history], max_chars=2000)
        self.assertTrue(pack["truncated"])
        self.assertEqual([x["id"] for x in pack["durable_memory"]], ["m1"])
        self.assertLessEqual(pack["serialized_chars"], 2000)

    def test_hard_budget_counts_serialized_chars_field_itself(self):
        history = [
            {"conversation_id": f"c{i}", "title": "Old chat", "role": "assistant", "created_at": "2026-08-20T00:00:00Z",
             "match": "H" * 330, "sources": ["source:a"], "source_class": "HISTORICAL_CONTEXT", "retrieval_role": "EVIDENCE_EXCERPT"}
            for i in range(19)
        ]
        pack = build_context_pack("p3 evidence", history, max_chars=10000)
        actual = len(json.dumps(pack, ensure_ascii=False, separators=(",", ":")))
        self.assertEqual(pack["serialized_chars"], actual)
        self.assertLessEqual(actual, 10000)

    def test_long_memory_body_is_clipped(self):
        pack = build_context_pack("test evidence", [self.memory("m", text="x" * 5000)])
        self.assertLess(len(pack["durable_memory"][0]["text"]), 800)


if __name__ == "__main__":
    unittest.main()
