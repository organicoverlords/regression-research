import json
import tempfile
import unittest
from pathlib import Path

from tools.slopwall_raw_discovery import discover


def msg(mid, role, text, t):
    return {"id": mid, "author": {"role": role}, "create_time": t, "content": {"parts": [text]}}


def conversation(cid, title, messages):
    return {
        "conversation_id": cid,
        "title": title,
        "mapping": {m["id"]: {"id": m["id"], "message": m} for m in messages},
    }


class SlopwallRawDiscoveryTests(unittest.TestCase):
    def test_literal_discovery_dedupes_message_aliases_and_preserves_bounded_context(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            day1 = root / "2026-08-26"
            day2 = root / "2026-08-27"
            day1.mkdir(); day2.mkdir()
            messages = [
                msg("a1", "assistant", "before", 1),
                msg("u1", "user", "Slopwall", 2),
                msg("a2", "assistant", "after", 3),
            ]
            (day1 / "one.json").write_text(json.dumps(conversation("c1", "One", messages)), encoding="utf-8")
            (day2 / "alias.json").write_text(json.dumps(conversation("c1", "One", messages)), encoding="utf-8")
            (day2 / "two.json").write_text(json.dumps(conversation("c2", "Two", [msg("u2", "user", "literal slop wall here", 4)])), encoding="utf-8")

            report = discover(root, source_root_label="raw")
            self.assertEqual(report["summary"]["files_scanned"], 3)
            self.assertEqual(report["summary"]["bad_json_files"], 0)
            self.assertEqual(report["summary"]["unique_hit_messages"], 2)
            self.assertEqual(report["summary"]["literal_occurrences"], {"slopwall": 1, "slop wall": 1})
            by_id = {row["message_id"]: row for row in report["records"]}
            self.assertEqual(by_id["u1"]["source_alias_count"], 2)
            self.assertEqual(by_id["u1"]["context_before"][0]["text"], "before")
            self.assertEqual(by_id["u1"]["context_after"][0]["text"], "after")
            self.assertEqual(by_id["u2"]["matched_forms"]["slop wall"], 1)
            self.assertEqual(by_id["u2"]["review_state"], "PENDING_CANONICAL_DEDUPE_AND_SCORING")

    def test_bad_json_is_counted_not_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); day = root / "2026-08-26"; day.mkdir()
            (day / "bad.json").write_text("{", encoding="utf-8")
            report = discover(root)
            self.assertEqual(report["summary"]["bad_json_files"], 1)
            self.assertEqual(report["records"], [])


if __name__ == "__main__":
    unittest.main()
