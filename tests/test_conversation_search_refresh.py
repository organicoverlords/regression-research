import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.conversation_search import index_roots, search_db
from tools.conversation_search_refresh import rebuild_index


def conversation(cid, phrase):
    return {"id": cid, "title": cid, "messages": [{"id": "m1", "role": "user", "content": phrase}]}


class ConversationSearchRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.corpus = self.base / "vault" / "memory" / "conversations" / "raw"
        self.corpus.mkdir(parents=True)
        self.db = self.base / "conversations.sqlite3"

    def tearDown(self):
        self.tmp.cleanup()

    def test_rebuild_indexes_only_canonical_vault_corpus_and_prunes_old_provenance(self):
        old = self.base / "Downloads" / "ChatPortEvidence"
        old.mkdir(parents=True)
        (old / "old.json").write_text(json.dumps(conversation("old", "downloads-only phrase")), encoding="utf-8")
        index_roots(self.db, [old])
        self.assertTrue(search_db(self.db, "downloads-only phrase", literal=True))

        (self.corpus / "vault.json").write_text(json.dumps(conversation("vault", "vault-only phrase")), encoding="utf-8")
        result = rebuild_index(self.db, self.corpus)
        self.assertEqual(result["status"], "PROVEN")
        self.assertEqual(result["rebuild"], "atomic-fresh")
        self.assertEqual(search_db(self.db, "downloads-only phrase", literal=True), [])
        hits = search_db(self.db, "vault-only phrase", literal=True)
        self.assertEqual(len(hits), 1)
        self.assertIn(str(self.corpus), hits[0]["sources"][0])

        conn = sqlite3.connect(self.db)
        try:
            locators = [row[0] for row in conn.execute("SELECT locator FROM sources")]
        finally:
            conn.close()
        self.assertTrue(locators)
        self.assertTrue(all(str(self.corpus) in locator for locator in locators))


if __name__ == "__main__":
    unittest.main()
