import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.user_message_catalog import (
    build_catalog,
    candidate_records,
    classify_user_text,
    iter_user_messages,
)


class UserMessageCatalogTests(unittest.TestCase):
    def make_db(self, root: Path) -> Path:
        db = root / "catalog.sqlite3"
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE conversations(conversation_id TEXT PRIMARY KEY,title TEXT,create_time TEXT,update_time TEXT);
            CREATE TABLE messages(rowid INTEGER PRIMARY KEY,message_uid TEXT NOT NULL UNIQUE,conversation_id TEXT NOT NULL,message_id TEXT NOT NULL,role TEXT NOT NULL,created_at TEXT,order_index INTEGER NOT NULL,text TEXT NOT NULL);
            CREATE TABLE sources(source_id TEXT PRIMARY KEY,locator TEXT NOT NULL UNIQUE,kind TEXT,root TEXT,size INTEGER,mtime_ns INTEGER,fingerprint TEXT,indexed_at TEXT);
            CREATE TABLE source_messages(source_id TEXT NOT NULL,message_uid TEXT NOT NULL,PRIMARY KEY(source_id,message_uid));
            """
        )
        conn.execute("INSERT INTO conversations VALUES(?,?,?,?)", ("c1", "Rules", None, None))
        conn.executemany(
            "INSERT INTO messages VALUES(NULL,?,?,?,?,?,?,?)",
            [
                ("u1", "c1", "m1", "user", "2026-06-01T10:00:00Z", 1, "For all future responses, verify current state before claiming success."),
                ("a1", "c1", "m2", "assistant", "2026-06-01T10:00:01Z", 2, "Okay"),
                ("u2", "c1", "m3", "user", "1970-01-01T00:00:01Z", 3, "hello"),
            ],
        )
        conn.executemany("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?)", [
            ("s1", "source:b", "json", "r", 1, 1, "f1", "x"),
            ("s2", "source:a", "json", "r", 1, 1, "f2", "x"),
        ])
        conn.executemany("INSERT INTO source_messages VALUES(?,?)", [("s1", "u1"), ("s2", "u1"), ("s1", "u2")])
        conn.commit()
        conn.close()
        return db

    def test_explicit_future_behavior_is_candidate_not_authority(self):
        result = classify_user_text("For all future responses, verify current state before claiming success.")
        self.assertEqual(result["candidate_tier"], "PERSISTENT_RULE_CANDIDATE")
        self.assertIn("persistent_scope", result["signals"])
        self.assertIn("behavior_target", result["signals"])

    def test_catalog_contains_every_user_message_once_and_excludes_assistant(self):
        with tempfile.TemporaryDirectory() as td:
            rows = list(iter_user_messages(self.make_db(Path(td))))
        self.assertEqual([row["message_uid"] for row in rows], ["u1", "u2"])
        self.assertEqual(rows[0]["source_locators"], ["source:a", "source:b"])
        self.assertTrue(rows[0]["wall_clock"])
        self.assertFalse(rows[1]["wall_clock"])

    def test_build_is_byte_deterministic_for_same_db(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = self.make_db(root)
            first = root / "first.jsonl"
            second = root / "second.jsonl"
            one = build_catalog(db, first)
            two = build_catalog(db, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(one["catalog_sha256"], two["catalog_sha256"])
            self.assertEqual(one["user_messages"], 2)
            self.assertEqual(one["non_wall_clock_messages"], 1)

    def test_candidates_are_bounded_and_filterable(self):
        with tempfile.TemporaryDirectory() as td:
            db = self.make_db(Path(td))
            rows = candidate_records(db, tier="PERSISTENT_RULE_CANDIDATE", limit=1)
        self.assertEqual([row["message_uid"] for row in rows], ["u1"])

    def test_manifest_does_not_promote_catalog_to_behavior_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = self.make_db(root)
            report = build_catalog(db, root / "catalog.jsonl")
            manifest = json.loads((root / "catalog.manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(report["authority"], "FORENSIC_CATALOG_ONLY")
        self.assertEqual(manifest["authority"], "FORENSIC_CATALOG_ONLY")


if __name__ == "__main__":
    unittest.main()
