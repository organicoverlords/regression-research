import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.conversation_search import discover_roots, index_roots, search_db


def conversation(cid, title, user_text, assistant_text, base=1):
    return {
        "id": cid,
        "title": title,
        "create_time": base,
        "update_time": base + 2,
        "mapping": {
            "u": {
                "message": {
                    "id": "u1",
                    "author": {"role": "user"},
                    "create_time": base,
                    "content": {"parts": [user_text]},
                }
            },
            "a": {
                "message": {
                    "id": "a1",
                    "author": {"role": "assistant"},
                    "create_time": base + 1,
                    "content": {"parts": [assistant_text]},
                }
            },
        },
    }


class ConversationSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "Downloads"
        self.root.mkdir()
        self.old = self.root / "ChatPortEvidence"
        self.new = self.root / "ChatGPTLocalExporter"
        self.old.mkdir()
        self.new.mkdir()
        self.db = Path(self.tmp.name) / "conversations.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_discovers_old_new_and_opaque_zip(self):
        opaque = self.root / "e31c17.zip"
        with zipfile.ZipFile(opaque, "w") as archive:
            archive.writestr("nested/conversations.json", json.dumps([conversation("z", "Zip", "zip phrase", "answer")]))
        roots = discover_roots(self.root)
        self.assertEqual({path.name for path in roots}, {"ChatPortEvidence", "ChatGPTLocalExporter", "e31c17.zip"})

    def test_full_text_search_dedupes_repeated_captures_and_keeps_provenance(self):
        old = conversation("c1", "Old convo", "needle old phrase", "old answer", 100)
        (self.old / "capture1.json").write_text(json.dumps(old), encoding="utf-8")
        (self.old / "capture2.json").write_text(json.dumps(old), encoding="utf-8")
        new = conversation("c2", "New convo", "newer unique phrase", "new answer", 200)
        (self.new / "conversations.json").write_text(json.dumps([new]), encoding="utf-8")

        report = index_roots(self.db, discover_roots(self.root))
        self.assertEqual(report["status"], "PROVEN")
        self.assertEqual(report["coverage"]["conversations"], 2)
        self.assertEqual(report["coverage"]["messages"], 4)

        old_hits = search_db(self.db, "needle old phrase", literal=True)
        self.assertEqual(len(old_hits), 1)
        self.assertEqual(old_hits[0]["conversation_id"], "c1")
        self.assertEqual(len(old_hits[0]["sources"]), 2)
        self.assertEqual(old_hits[0]["context_after"], "assistant: old answer")

        new_hits = search_db(self.db, "newer unique")
        self.assertEqual(new_hits[0]["conversation_id"], "c2")

    def test_incremental_reindex_removes_stale_message_version(self):
        path = self.new / "conversations.json"
        path.write_text(json.dumps([conversation("c2", "New", "first phrase", "answer", 200)]), encoding="utf-8")
        index_roots(self.db, [self.new])
        self.assertTrue(search_db(self.db, "first phrase", literal=True))

        path.write_text(json.dumps([conversation("c2", "New", "replacement phrase", "answer", 200)]), encoding="utf-8")
        index_roots(self.db, [self.new])
        self.assertEqual(search_db(self.db, "first phrase", literal=True), [])
        self.assertTrue(search_db(self.db, "replacement phrase", literal=True))


if __name__ == "__main__":
    unittest.main()
