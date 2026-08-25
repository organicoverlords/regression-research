import time
import tracemalloc
import unittest

from tools.memory_bank import search_entries


SOURCE_REGISTRY = {
    "classes": {"LIVE_CANONICAL": 60, "HISTORICAL_CONTEXT": 20},
    "sources": [
        {"class": "LIVE_CANONICAL", "match_prefixes": ["live://"]},
        {"class": "HISTORICAL_CONTEXT", "match_prefixes": ["history://"]},
    ],
}


def stress_corpus(size=5000):
    """Deterministic compact corpus fixture large enough to exercise scale bounds."""
    entries = []
    for index in range(size):
        relevant = index % 10 == 0
        entries.append({
            "id": f"scale-{index:05d}",
            "timestamp": f"2026-08-{1 + (index % 25):02d}T10:{index % 60:02d}:00+03:00",
            "kind": "fact",
            "scope": "memory" if relevant else "other",
            "tags": ["target", "scale"] if relevant else ["noise"],
            "text": f"target bounded recall candidate {index}" if relevant else f"unrelated authority noise {index}",
            "state": "PROVEN",
            "evidence": [("history://" if relevant else "live://") + str(index)],
            "supersedes": [],
        })
    return entries


class MemoryScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = stress_corpus()

    def test_large_corpus_keeps_recall_and_history_hard_bounded(self):
        default = search_entries(self.entries, "target", source_registry=SOURCE_REGISTRY)
        requested_too_many = search_entries(
            self.entries, "target", limit=5000, source_registry=SOURCE_REGISTRY
        )
        history = search_entries(
            self.entries, "", history=True, limit=5000, source_registry=SOURCE_REGISTRY
        )

        self.assertEqual(len(default), 5)
        self.assertEqual(len(requested_too_many), 8)
        self.assertEqual(len(history), 20)
        self.assertTrue(all("target" in entry["tags"] for entry in requested_too_many))
        self.assertFalse(any(entry["evidence"][0].startswith("live://") for entry in requested_too_many))

    def test_large_corpus_recall_has_routine_worker_resource_cost(self):
        tracemalloc.start()
        started = time.perf_counter()
        result = search_entries(
            self.entries, "target", limit=5000, source_registry=SOURCE_REGISTRY
        )
        elapsed = time.perf_counter() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        print(f"scale_metrics entries={len(self.entries)} elapsed_ms={elapsed * 1000:.1f} peak_bytes={peak_bytes}")

        self.assertEqual(len(result), 8)
        self.assertLess(elapsed, 2.0)
        self.assertLess(peak_bytes, 64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
