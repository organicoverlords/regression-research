import time
import tracemalloc
import unittest
from datetime import datetime, timedelta, timezone

from tools.memory_bank import search_entries


class MemoryBankScaleRecallTests(unittest.TestCase):
    @staticmethod
    def entry(index, text, *, evidence=None, state="PROVEN"):
        stamp = datetime(2026, 8, 1, tzinfo=timezone.utc) + timedelta(seconds=index)
        return {
            "id": f"scale-{index:05d}",
            "timestamp": stamp.isoformat(),
            "kind": "fact",
            "scope": "global",
            "tags": ["scale"],
            "text": text,
            "state": state,
            "evidence": evidence or [],
            "supersedes": [],
        }

    def test_thousands_of_candidates_keep_recall_bounded_and_relevant(self):
        entries = [
            self.entry(i, f"routine corpus record {i}")
            for i in range(5000)
        ]
        entries.extend(
            self.entry(5000 + i, f"bounded recall target {i}", evidence=["regression:scale"])
            for i in range(40)
        )
        entries.append(
            self.entry(6000, "unrelated canonical policy", evidence=["user-instruction:current"])
        )

        tracemalloc.start()
        started = time.perf_counter()
        default = search_entries(entries, "bounded recall target")
        explicit = search_entries(entries, "bounded recall target", limit=1000)
        history = search_entries(entries, "", history=True, limit=1000)
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        self.assertEqual(len(default), 5)
        self.assertEqual(len(explicit), 8)
        self.assertEqual(len(history), 20)
        self.assertNotIn("scale-06000", {entry["id"] for entry in default + explicit})
        self.assertLess(elapsed, 5.0)
        self.assertLess(peak, 64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
