import time
import tracemalloc
import unittest

from tools.memory_bank import search_entries, search_memory_entries
from tools.memory_hybrid import search_entries_hybrid


class HybridPromotionTests(unittest.TestCase):
    @staticmethod
    def entry(index, text, *, title="", ts=None):
        return {
            "id": f"m-{index}",
            "timestamp": ts or f"2026-08-27T10:{index % 60:02d}:00+03:00",
            "kind": "fact",
            "scope": "global",
            "tags": [],
            "title": title,
            "text": text,
            "state": "PROVEN",
            "evidence": [],
            "supersedes": [],
        }

    def test_default_strategy_is_hybrid(self):
        entries = [
            self.entry(1, "refresh context background detail", title="Other context note"),
            self.entry(2, "A refresh is incomplete until retrieval actually occurs.", title="Refresh requires retrieval before completion"),
        ]
        query = "when asked to refresh, reread before saying it is done"
        expected = [e["id"] for e in search_entries_hybrid(entries, query)]
        actual = [e["id"] for e in search_memory_entries(entries, query)]
        self.assertEqual(actual, expected)

    def test_history_preserves_legacy_semantics(self):
        old = self.entry(1, "old route")
        old["state"] = "REJECTED"
        hybrid_history = search_memory_entries([old], "", history=True)
        legacy_history = search_entries([old], "", history=True)
        self.assertEqual(hybrid_history, legacy_history)

    def test_hybrid_scale_stays_inside_existing_budget(self):
        entries = [self.entry(i, f"routine corpus record {i}") for i in range(5000)]
        entries.extend(self.entry(5000 + i, f"bounded recall target {i}", title=f"Recall target {i}") for i in range(40))
        tracemalloc.start()
        started = time.perf_counter()
        hits = search_entries_hybrid(entries, "bounded recall target", limit=8)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertEqual(len(hits), 8)
        self.assertTrue(all("bounded recall target" in h["text"] for h in hits))
        self.assertLess(elapsed, 5.0)
        self.assertLess(peak, 64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
