import unittest

from tools.memory_bank import derive_display_title, recent_title_entries


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


if __name__ == "__main__":
    unittest.main()
