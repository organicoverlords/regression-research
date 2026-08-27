import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tools.conversation_search import _print, discover_roots, index_roots, search_db, search_report
from tools.memory_bank import _print_json, search_all_memory


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

    def test_search_report_keeps_full_frequency_signal_but_bounds_diverse_context(self):
        conversations = [
            conversation(
                f"c{index}",
                f"MCP {index}",
                f"mcp recurring marker user {index}",
                f"mcp recurring marker assistant {index}",
                100 + index * 100,
            )
            for index in range(12)
        ]
        (self.new / "conversations.json").write_text(json.dumps(conversations), encoding="utf-8")
        index_roots(self.db, [self.new])

        report = search_report(self.db, "mcp recurring marker", limit=4)

        self.assertEqual(report["summary"]["matching_messages"], 24)
        self.assertEqual(report["summary"]["matching_conversations"], 12)
        self.assertEqual(report["summary"]["sampled_conversations"], 4)
        self.assertEqual(len(report["hits"]), 4)
        self.assertEqual(len({hit["conversation_id"] for hit in report["hits"]}), 4)
        self.assertEqual(sum(report["summary"]["roles"].values()), 24)
        self.assertEqual(report["summary"]["top_conversations"][0]["matches"], 2)

    def test_memory_bootstrap_stays_light_but_search_can_query_conversations(self):
        memory_bank = (Path(__file__).resolve().parents[1] / "tools" / "memory_bank.py").read_text(encoding="utf-8")
        bootstrap_prefix = memory_bank.split("def _conversation_excerpt", 1)[0]
        self.assertNotIn("conversation_search", bootstrap_prefix)

        path = self.new / "conversations.json"
        path.write_text(json.dumps([conversation("c-memory", "Old behavior", "rare historical marker", "answer", 200)]), encoding="utf-8")
        index_roots(self.db, [self.new])
        hits = search_all_memory([], "rare historical marker", conversation_db=self.db)
        excerpt = next(hit for hit in hits if hit.get("kind") == "conversation")
        self.assertEqual(excerpt.get("conversation_id"), "c-memory")
        self.assertEqual(excerpt.get("source_class"), "HISTORICAL_CONTEXT")
        self.assertEqual(excerpt.get("retrieval_role"), "EVIDENCE_EXCERPT")
        self.assertNotIn("state", excerpt)
        self.assertNotIn("context_before", excerpt)
        self.assertNotIn("context_after", excerpt)
        summary = next(hit for hit in hits if hit.get("kind") == "corpus-summary")
        self.assertEqual(summary["matching_conversations"], 1)
        self.assertEqual(summary["interpretation"], "prevalence_signal_not_truth")

    def test_unified_search_keeps_aggregate_signal_and_bounds_combined_evidence(self):
        conversations = [
            conversation(
                f"c{index}",
                f"MCP {index}",
                f"mcp recurring marker user {index}",
                f"mcp recurring marker assistant {index}",
                100 + index * 100,
            )
            for index in range(12)
        ]
        (self.new / "conversations.json").write_text(json.dumps(conversations), encoding="utf-8")
        index_roots(self.db, [self.new])
        entries = [
            {
                "id": f"mem-{index}",
                "timestamp": f"2026-08-2{index}T10:00:00+03:00",
                "kind": "correction",
                "scope": "mcp",
                "tags": ["mcp"],
                "text": f"mcp recurring marker durable {index}",
                "state": "PROVEN",
                "evidence": [f"evidence:{index}"],
                "supersedes": [],
            }
            for index in range(1, 6)
        ]

        hits = search_all_memory(entries, "mcp recurring marker", limit=4, conversation_db=self.db)
        evidence_hits = [hit for hit in hits if hit.get("kind") != "corpus-summary"]
        memory_hits = [hit for hit in evidence_hits if hit.get("kind") != "conversation"]
        conversation_hits = [hit for hit in evidence_hits if hit.get("kind") == "conversation"]
        summary = next(hit for hit in hits if hit.get("kind") == "corpus-summary")

        self.assertEqual(len(evidence_hits), 4)
        self.assertEqual(len(memory_hits), 3)
        self.assertEqual(len(conversation_hits), 1)
        self.assertEqual(summary["matching_messages"], 24)
        self.assertEqual(summary["matching_conversations"], 12)
        self.assertLessEqual(len(summary["top_conversations"]), 3)
        self.assertTrue(all(hit.get("source_class") == "HISTORICAL_CONTEXT" for hit in conversation_hits))
        self.assertTrue(all("state" not in hit for hit in conversation_hits))

        scoped = search_all_memory(entries, "mcp recurring marker", scope="mcp", limit=4, conversation_db=self.db)
        self.assertTrue(any(hit.get("kind") == "corpus-summary" for hit in scoped))
        self.assertTrue(any(hit.get("kind") == "conversation" for hit in scoped))

    def test_json_output_handles_private_use_unicode_on_legacy_stdout_encoding(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        with patch("tools.conversation_search.sys.stdout", stream):
            _print({"text": "\ue200"})
            stream.flush()
        payload = raw.getvalue().decode("utf-8")
        self.assertEqual(json.loads(payload)["text"], "\ue200")

    def test_memory_json_output_handles_private_use_unicode_on_legacy_stdout_encoding(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252")
        with patch("tools.memory_bank.sys.stdout", stream):
            _print_json({"text": "\ue200"})
            stream.flush()
        payload = raw.getvalue().decode("utf-8")
        self.assertEqual(json.loads(payload)["text"], "\ue200")

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
