import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.conversation_search_refresh import discover_extended


class ConversationSearchRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.downloads = Path(self.tmp.name) / "Downloads"
        self.downloads.mkdir()
        (self.downloads / "ChatPortEvidence").mkdir()
        (self.downloads / "ChatGPTLocalExporter").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_nested_opaque_export_zip_without_adding_archive_container(self):
        archive_dir = self.downloads / "@5_Archives"
        archive_dir.mkdir()
        opaque = archive_dir / "8f31c0.zip"
        with zipfile.ZipFile(opaque, "w") as zf:
            zf.writestr("export/conversations.json", json.dumps([]))
        roots = discover_extended(self.downloads)
        self.assertIn(opaque, roots)
        self.assertNotIn(archive_dir, roots)

    def test_ignores_unrelated_nested_zip_with_generic_jsonl(self):
        archive_dir = self.downloads / "05_Archives"
        archive_dir.mkdir()
        unrelated = archive_dir / "repo-proof.zip"
        with zipfile.ZipFile(unrelated, "w") as zf:
            zf.writestr("logs/events.jsonl", "{}\n")
        roots = discover_extended(self.downloads)
        self.assertNotIn(unrelated, roots)

    def test_finds_nested_official_export_folder_by_conversations_json(self):
        container = self.downloads / "sorted" / "2026" / "opaque-export"
        container.mkdir(parents=True)
        (container / "conversations.json").write_text("[]", encoding="utf-8")
        roots = discover_extended(self.downloads)
        self.assertIn(container, roots)

    def test_depth_bound_excludes_deeper_unknown_container(self):
        deep = self.downloads / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "conversations.json").write_text("[]", encoding="utf-8")
        roots = discover_extended(self.downloads, max_depth=3)
        self.assertNotIn(deep, roots)


if __name__ == "__main__":
    unittest.main()
