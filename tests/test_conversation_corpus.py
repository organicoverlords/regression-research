import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.conversation_corpus import backup, export_legacy_sqlite, import_source, verify


class ConversationCorpusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / "source"
        self.root = self.base / "vault" / "memory" / "conversations"
        self.backup_dir = self.base / "backup"
        self.source.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_preserves_bytes_and_is_restart_safe(self):
        (self.source / "raw").mkdir()
        a = self.source / "raw" / "a.json"
        b = self.source / "notes.txt"
        a.write_bytes(b'{"id":"c1","messages":[]}')
        b.write_text("notes", encoding="utf-8")

        first = import_source(self.source, "old", self.root)
        self.assertEqual(first["status"], "PROVEN")
        self.assertEqual(first["copied"], 2)
        self.assertEqual((self.root / "raw" / "old" / "raw" / "a.json").read_bytes(), a.read_bytes())
        self.assertEqual(verify(self.root, hashes=True)["status"], "PROVEN")

        second = import_source(self.source, "old", self.root)
        self.assertEqual(second["copied"], 0)
        self.assertEqual(second["reused"], 2)
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["files"]), 2)

    def test_import_refuses_to_overwrite_different_canonical_bytes(self):
        src = self.source / "a.json"
        src.write_text("one", encoding="utf-8")
        import_source(self.source, "old", self.root)
        target = self.root / "raw" / "old" / "a.json"
        target.write_text("tampered", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            import_source(self.source, "old", self.root)

    def test_changed_source_is_not_silently_replaced(self):
        src = self.source / "a.json"
        src.write_text("one", encoding="utf-8")
        import_source(self.source, "old", self.root)
        src.write_text("two", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            import_source(self.source, "old", self.root)

    def test_recovers_legacy_sqlite_into_self_contained_conversation_json(self):
        legacy = self.base / "legacy.sqlite"
        conn = sqlite3.connect(legacy)
        conn.execute("CREATE TABLE conversations(id TEXT PRIMARY KEY,title TEXT,source_kind TEXT,source_path TEXT,source_hash TEXT,opened_at TEXT,scraped_at TEXT,create_time REAL,update_time REAL,message_count INTEGER,char_count INTEGER,signal_score INTEGER,full_traversal INTEGER)")
        conn.execute("CREATE TABLE messages(conversation_id TEXT,seq INTEGER,role TEXT,message_id TEXT,create_time REAL,text TEXT,PRIMARY KEY(conversation_id,seq))")
        conn.execute("INSERT INTO conversations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", ("c1","Recovered","library","missing.md","hash",None,None,10.0,20.0,2,9,0,1))
        conn.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)", ("c1",0,"user","u1",10.0,"old marker"))
        conn.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)", ("c1",1,"assistant","a1",11.0,"old answer"))
        conn.commit(); conn.close()
        import_source(legacy, "legacy-db-source", self.root)
        result = export_legacy_sqlite(legacy, self.root)
        self.assertEqual(result["status"], "PROVEN")
        self.assertEqual(result["conversations"], 1)
        recovered = self.root / "recovered" / "legacy-regression-sqlite" / "conversations" / "c1.json"
        payload = json.loads(recovered.read_text(encoding="utf-8"))
        self.assertEqual(payload["messages"][0]["content"]["parts"], ["old marker"])
        self.assertEqual(verify(self.root, hashes=True)["status"], "PROVEN")

    def test_backup_is_crc_and_checksum_verified(self):
        (self.source / "a.json").write_text('{"id":"c1","messages":[]}', encoding="utf-8")
        import_source(self.source, "old", self.root)
        result = backup(self.root, self.backup_dir)
        self.assertEqual(result["status"], "PROVEN")
        archive = Path(result["archive"])
        self.assertTrue(archive.is_file())
        self.assertTrue(Path(result["checksum"]).is_file())
        with zipfile.ZipFile(archive) as zf:
            self.assertIsNone(zf.testzip())
            self.assertIn("manifest.json", zf.namelist())
            self.assertIn("raw/old/a.json", zf.namelist())


if __name__ == "__main__":
    unittest.main()
