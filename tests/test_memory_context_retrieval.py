import unittest

from tools.memory_bank import search_context_memory


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


if __name__ == "__main__":
    unittest.main()
