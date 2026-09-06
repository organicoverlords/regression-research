import unittest

from tools.memory_bank import aggregate_memory, derive_display_title, recent_title_entries


class MemoryRecentTitleTests(unittest.TestCase):
    def entry(self, ident, timestamp, text, *, state="PROVEN", supersedes=None, title=None):
        value = {
            "id": ident,
            "timestamp": timestamp,
            "kind": "lesson",
            "scope": "memory",
            "tags": ["startup"],
            "text": text,
            "state": state,
            "evidence": ["issue:53"],
            "supersedes": supersedes or [],
        }
        if title is not None:
            value["title"] = title
        return value

    def test_explicit_title_wins_and_text_title_is_bounded(self):
        explicit = self.entry("mem-a", "2026-08-25T10:00:00+03:00", "ignored", title="  Recent   errors  ")
        self.assertEqual(derive_display_title(explicit), "Recent errors")
        derived = self.entry("mem-b", "2026-08-25T10:01:00+03:00", "x" * 120)
        title = derive_display_title(derived)
        self.assertEqual(len(title), 80)
        self.assertTrue(title.endswith("…"))

    def test_newest_first_default_is_ten_and_hard_cap_is_twenty(self):
        entries = [
            self.entry(f"mem-{i:02d}", f"2026-08-25T10:{i:02d}:00+03:00", f"note {i}")
            for i in range(25)
        ]
        default = recent_title_entries(entries)
        self.assertEqual(len(default), 10)
        self.assertEqual(default[0]["id"], "mem-24")
        self.assertEqual(default[-1]["id"], "mem-15")
        self.assertEqual(len(recent_title_entries(entries, limit=999)), 20)

    def test_rejected_and_superseded_entries_are_hidden(self):
        old = self.entry("mem-old", "2026-08-25T10:00:00+03:00", "old error")
        rejected = self.entry("mem-rejected", "2026-08-25T10:02:00+03:00", "bad note", state="REJECTED")
        current = self.entry("mem-current", "2026-08-25T10:03:00+03:00", "corrected note", supersedes=["mem-old"])
        result = recent_title_entries([old, rejected, current])
        self.assertEqual([item["id"] for item in result], ["mem-current"])

    def test_zero_limit_is_empty(self):
        entry = self.entry("mem-a", "2026-08-25T10:00:00+03:00", "one")
        self.assertEqual(recent_title_entries([entry], limit=0), [])

    def test_overview_aggregates_durable_memory_without_query(self):
        first = self.entry("mem-a", "2026-08-25T10:00:00+03:00", "first")
        first["project"] = "p3"
        first["tags"] = ["routing", "assistant-recorded"]
        second = self.entry("mem-b", "2026-08-25T10:01:00+03:00", "second")
        second["project"] = "p3"
        second["tags"] = ["routing", "evidence"]
        rejected = self.entry("mem-rejected", "2026-08-25T10:02:00+03:00", "rejected", state="REJECTED")
        rejected["project"] = "noise"

        overview = aggregate_memory([first, second, rejected], limit=5)

        self.assertEqual(overview["schema"], "memory-bank.overview.v1")
        self.assertEqual(overview["eligible_entries"], 2)
        self.assertEqual(overview["projects"][0]["name"], "p3")
        self.assertEqual(overview["projects"][0]["count"], 2)
        self.assertEqual(overview["projects"][0]["latest"]["id"], "mem-b")
        self.assertEqual(overview["recurring_tags"], [{"name": "routing", "count": 2}])
        self.assertNotIn("assistant-recorded", {item["name"] for item in overview["top_tags"]})
        self.assertEqual([item["id"] for item in overview["recent"]], ["mem-b", "mem-a"])
        self.assertEqual(overview["incident_rollups"], [])

    def test_overview_rolls_repeated_incident_memories_into_one_lineage(self):
        entries = []
        for i in range(6):
            entry = self.entry(f"mem-{i}", f"2026-08-25T10:0{i}:00+03:00", f"MCP regression observation {i}", title=f"Regression {i}")
            entry["scope"] = "mcp"
            entry["tags"] = ["regression"]
            entry["evidence"] = ["github:organicoverlords/regression-research#125"]
            entries.append(entry)
        overview = aggregate_memory(entries, limit=5)
        self.assertEqual(len(overview["incident_rollups"]), 1)
        rollup = overview["incident_rollups"][0]
        self.assertEqual(rollup["observations"], 6)
        self.assertEqual(rollup["latest_event_id"], "mem-5")
        self.assertEqual(rollup["thread_source"], "EVIDENCE_ANCHOR")


if __name__ == "__main__":
    unittest.main()
