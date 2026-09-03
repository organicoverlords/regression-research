import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "02 Evidence" / "2026-08-27_slopwall_raw_discovery.json"


class SlopwallRawDiscoverySnapshotTests(unittest.TestCase):
    def test_snapshot_is_deduped_traceable_and_pending_review(self):
        data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["authority"], "RAW_DISCOVERY_ONLY")
        self.assertEqual(data["summary"]["bad_json_files"], 0)
        self.assertEqual(data["summary"]["unique_hit_messages"], 46)
        self.assertEqual(data["summary"]["literal_occurrences"], {"slopwall": 46, "slop wall": 0})
        records = data["records"]
        self.assertEqual(len(records), 46)
        self.assertEqual(len({row["message_id"] for row in records}), len(records))
        self.assertGreaterEqual(data["summary"]["source_aliases"], len(records))
        for row in records:
            self.assertEqual(row["review_state"], "PENDING_CANONICAL_DEDUPE_AND_SCORING")
            self.assertLessEqual(len(row["context_before"]), 4)
            self.assertLessEqual(len(row["context_after"]), 4)
            self.assertGreaterEqual(row["source_alias_count"], 1)
            for source in row["sources"]:
                self.assertTrue(source["path"].startswith("ChatPortEvidence/raw/"))
                self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
