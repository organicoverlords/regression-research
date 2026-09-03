import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.conversation_corpus import backup, import_source, sync_source, verify


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

    def test_sync_source_adds_only_new_files_and_fast_reuses_unchanged(self):
        a = self.source / "a.json"
        a.write_text("one", encoding="utf-8")
        import_source(self.source, "old", self.root)
        b = self.source / "b.json"
        b.write_text("two", encoding="utf-8")

        result = sync_source(self.source, "old", self.root)
        self.assertEqual(result["status"], "PROVEN")
        self.assertEqual(result["copied"], 1)
        self.assertEqual(result["reused"], 1)
        self.assertEqual(result["fast_reused"], 1)
        self.assertEqual((self.root / "raw" / "old" / "b.json").read_text(encoding="utf-8"), "two")
        self.assertEqual(verify(self.root, hashes=True)["status"], "PROVEN")

    def test_sync_source_preserves_changed_path_as_revision(self):
        src = self.source / "a.json"
        src.write_text("one", encoding="utf-8")
        import_source(self.source, "old", self.root)
        src.write_text("two-two", encoding="utf-8")
        result = sync_source(self.source, "old", self.root)
        self.assertEqual(result["revisions_copied"], 1)
        self.assertEqual((self.root / "raw" / "old" / "a.json").read_text(encoding="utf-8"), "one")
        revisions = list((self.root / "revisions" / "old").rglob("a.json"))
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].read_text(encoding="utf-8"), "two-two")
        self.assertEqual(verify(self.root, hashes=True)["status"], "PROVEN")

    def test_sync_source_rejects_tampered_canonical_baseline(self):
        src = self.source / "a.json"
        src.write_text("one", encoding="utf-8")
        import_source(self.source, "old", self.root)
        target = self.root / "raw" / "old" / "a.json"
        target.write_text("tampered", encoding="utf-8")
        src.write_text("new source bytes", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            sync_source(self.source, "old", self.root)

    def test_sync_source_never_deletes_canonical_file_missing_from_source(self):
        src = self.source / "a.json"
        src.write_text("one", encoding="utf-8")
        import_source(self.source, "old", self.root)
        src.unlink()
        result = sync_source(self.source, "old", self.root)
        self.assertEqual(result["copied"], 0)
        self.assertEqual(result["preserved_missing_source_files"], 1)
        self.assertTrue((self.root / "raw" / "old" / "a.json").is_file())
        self.assertEqual(verify(self.root, hashes=True)["status"], "PROVEN")

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
