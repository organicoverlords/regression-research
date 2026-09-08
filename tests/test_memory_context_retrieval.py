import unittest

from tools.memory_bank import search_context_memory, search_all_memory
from unittest.mock import patch


class MemoryContextRetrievalTests(unittest.TestCase):
    @staticmethod
    def entry(ident, text, *, project=None, scope="global"):
        out = {
            "id": ident, "timestamp": "2026-08-27T10:00:00+03:00", "kind": "lesson",
            "scope": scope, "tags": [], "title": text, "text": text, "state": "PROVEN",
            "evidence": ["incident:" + ident], "supersedes": [],
        }
        if project:
            out["project"] = project
        return out

    def test_single_token_context_query_stays_closed(self):
        old_rule = self.entry("rule", "slopwall incident capture rule", scope="assistant-orchestration/slopwall")
        old_rule["behavior_rule"] = True
        old_rule["evidence"] = ["user-instruction:test"]
        advisory = self.entry("incident", "slopwall historical incident")
        self.assertEqual(search_context_memory([advisory, old_rule], "slopwall", limit=8), [])

    def test_multitoken_context_uses_relevance_not_authority(self):
        relevant = self.entry("relevant", "preserve inherited task evidence")
        unrelated = self.entry("other", "unrelated historical note")
        hits = search_context_memory([unrelated, relevant], "preserve inherited", limit=8)
        self.assertEqual([hit["id"] for hit in hits], ["relevant"])

    def test_named_project_gets_reserved_recall_budget(self):
        globals_ = [self.entry(f"g{i}", f"build routing generic note {i}") for i in range(12)]
        project = self.entry("p3-specific", "p3 build routing project note", project="p3", scope="p3/build")
        hits = search_context_memory([*globals_, project], "p3 build routing", limit=8)
        self.assertIn("p3-specific", [h["id"] for h in hits])
        self.assertEqual(hits[0]["id"], "p3-specific")
        self.assertLessEqual(len(hits), 8)

    def test_named_project_can_use_entity_linked_global_fallback_without_rescoping_it(self):
        global_tiny = self.entry("tiny-global", "Tiny3D build routing evidence", scope="control-plane")
        global_tiny["title"] = "Cross-project Tiny3D routing evidence"
        unrelated = self.entry("global", "build routing generic note", scope="global")
        hits = search_context_memory([unrelated, global_tiny], "tiny3d build routing", limit=8)
        self.assertEqual(hits[0]["id"], "tiny-global")
        self.assertIn("global", [h["id"] for h in hits])
        self.assertNotIn("project", global_tiny)

    def test_other_named_project_is_excluded_before_ranking(self):
        p3 = self.entry("p3", "p3 build routing", project="p3", scope="p3/build")
        tiny = self.entry("tiny", "p3 build routing exact tempting text", project="tiny3d", scope="tiny3d/build")
        hits = search_context_memory([tiny, p3], "p3 build routing", limit=8)
        self.assertEqual([h["id"] for h in hits], ["p3"])

    def test_linked_memory_id_bypasses_word_search_and_conversation_fallback(self):
        target = self.entry("mem-20260908-abc12345", "Earlier correction", project="p3")
        decoy = self.entry("mem-20260908-decoy", "Mention mem-20260908-abc12345", project="p3")
        with patch("tools.memory_bank.conversation_history_report", side_effect=AssertionError("no corpus lookup for IDs")):
            self.assertEqual([e["id"] for e in search_all_memory([decoy, target], target["id"])], [target["id"]])
            self.assertEqual([e["id"] for e in search_context_memory([decoy, target], target["id"])], [target["id"]])
            self.assertEqual(search_all_memory([decoy, target], "mem-20260908-missing"), [])

    def test_exact_id_does_not_promote_rejected_history(self):
        target = self.entry("mem-20260908-rejected", "Earlier rejected correction")
        target["state"] = "REJECTED"
        self.assertEqual(search_context_memory([target], target["id"]), [])
        with patch("tools.memory_bank.conversation_history_report", side_effect=AssertionError("no corpus lookup")):
            historical = search_all_memory([target], target["id"], history=True)
        self.assertEqual(historical[0]["state"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
