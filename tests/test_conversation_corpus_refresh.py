import json
import tempfile
import unittest
import sqlite3
from pathlib import Path

from tools.conversation_corpus import import_source
from tools.conversation_corpus_refresh import configured_imports, refresh_corpus
from tools.conversation_search import coverage_report, search_db


class ConversationCorpusRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.corpus = self.base / "corpus"
        self.db = self.base / "search.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def conversation(cid, phrase, ts):
        return [{
            "id": cid,
            "title": cid,
            "messages": [{"id": cid + "-m", "role": "user", "content": phrase, "create_time": ts}],
        }]

    def test_refresh_picks_up_new_files_and_rebuilds_index(self):
        (self.source / "one.json").write_text(json.dumps(self.conversation("c1", "first corpus marker", 1724371200)), encoding="utf-8")
        import_source(self.source, "chatport", self.corpus)
        first = refresh_corpus(corpus_root=self.corpus, db=self.db, min_age_seconds=0)
        self.assertEqual(first["status"], "PROVEN")
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(coverage_report(conn)["conversations"], 1)
        finally:
            conn.close()

        (self.source / "two.json").write_text(json.dumps(self.conversation("c2", "second fresh marker", 1756080000)), encoding="utf-8")
        second = refresh_corpus(corpus_root=self.corpus, db=self.db, min_age_seconds=0)
        self.assertEqual(second["status"], "PROVEN")
        self.assertEqual(second["copied"], 1)
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(coverage_report(conn)["conversations"], 2)
        finally:
            conn.close()
        hits = search_db(self.db, "second fresh marker", limit=4)
        self.assertEqual(hits[0]["conversation_id"], "c2")

    def test_refresh_preserves_changed_capture_as_revision_and_indexes_new_content(self):
        capture = self.source / "capture.json"
        capture.write_text(json.dumps(self.conversation("c1", "old capture marker", 1724371200)), encoding="utf-8")
        import_source(self.source, "chatport", self.corpus)
        first = refresh_corpus(corpus_root=self.corpus, db=self.db, min_age_seconds=0)
        self.assertEqual(first["status"], "PROVEN")

        capture.write_text(json.dumps(self.conversation("c1", "new capture marker", 1756080000)), encoding="utf-8")
        second = refresh_corpus(corpus_root=self.corpus, db=self.db, min_age_seconds=0)
        self.assertEqual(second["status"], "PROVEN")
        self.assertEqual(second["revisions_copied"], 1)
        self.assertTrue(search_db(self.db, "old capture marker", limit=4))
        new_hits = search_db(self.db, "new capture marker", limit=4)
        self.assertEqual(new_hits[0]["conversation_id"], "c1")
        revisions = list((self.corpus / "revisions" / "chatport").rglob("capture.json"))
        self.assertEqual(len(revisions), 1)

    def test_missing_configured_source_is_reported_but_preserved_corpus_still_verifies(self):
        (self.source / "one.json").write_text(json.dumps(self.conversation("c1", "marker", 1724371200)), encoding="utf-8")
        import_source(self.source, "chatport", self.corpus)
        self.source.rename(self.base / "gone")
        result = refresh_corpus(corpus_root=self.corpus, db=self.db, index=False, min_age_seconds=0)
        self.assertEqual(result["status"], "PROVEN")
        self.assertEqual(result["unavailable"][0]["label"], "chatport")
        self.assertEqual(result["verification"]["status"], "PROVEN")

    def test_unknown_label_fails_closed(self):
        (self.source / "one.json").write_text("[]", encoding="utf-8")
        import_source(self.source, "chatport", self.corpus)
        result = refresh_corpus(corpus_root=self.corpus, db=self.db, labels={"nope"}, index=False, min_age_seconds=0)
        self.assertEqual(result["status"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
