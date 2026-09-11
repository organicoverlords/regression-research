from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import json
import subprocess
import sys
import tempfile
import unittest

import tools.stack_atlas as atlas
import tools.yard_inbox_bridge as inbox


ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "tools" / "yard_inbox_bridge.py"


class YardInboxBootstrapTests(unittest.TestCase):
    def _store(self, root: Path, items: list[dict]) -> Path:
        path = root / "comments.json"
        path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_claims_legacy_comment_and_answer_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(Path(tmp), [{
                "id": 123,
                "name": "Mom",
                "text": "Keep this tree?",
                "view": {"camera": [1, 2, 3]},
                "ts": "2026-09-11T14:00:00Z",
            }])
            claimed = inbox.claim_next(store, actor="chat-a")
            self.assertEqual(claimed["status"], "CLAIMED")
            self.assertEqual(claimed["actor"], "chat-a")
            self.assertEqual(claimed["message"]["role"], "human")
            self.assertEqual(claimed["message"]["status"], "processing")
            self.assertEqual(claimed["message"]["text"], "Keep this tree?")

            second = inbox.claim_next(store, actor="chat-b")
            self.assertEqual(second["status"], "EMPTY")

            answered = inbox.answer("123", "chat-a", "Keep it.", store_path=store)
            self.assertTrue(answered["ok"])
            items = json.loads(store.read_text(encoding="utf-8"))
            self.assertEqual(items[0]["status"], "answered")
            self.assertEqual(items[1]["role"], "assistant")
            self.assertEqual(items[1]["reply_to"], 123)
            self.assertEqual(items[1]["text"], "Keep it.")

    def test_stale_processing_claim_is_recovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime(2026, 9, 11, 14, 30, tzinfo=timezone.utc)
            old = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
            store = self._store(Path(tmp), [{
                "id": "msg_old",
                "role": "human",
                "name": "Mom",
                "text": "Stale claim",
                "status": "processing",
                "claimed_by": "dead-chat",
                "claimed_at": old,
            }])
            claimed = inbox.claim_next(store, actor="new-chat", now=now, ttl_seconds=1200)
            self.assertEqual(claimed["status"], "CLAIMED")
            self.assertEqual(claimed["message"]["claimed_by"], "new-chat")

    def test_two_processes_compete_and_only_one_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(Path(tmp), [{
                "id": "msg_one",
                "name": "Mom",
                "text": "One message",
                "ts": "2026-09-11T14:00:00Z",
            }])
            base = [sys.executable, str(BRIDGE), "--store", str(store), "claim"]
            p1 = subprocess.Popen(base + ["--actor", "chat-a"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            p2 = subprocess.Popen(base + ["--actor", "chat-b"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out1, err1 = p1.communicate(timeout=10)
            out2, err2 = p2.communicate(timeout=10)
            self.assertEqual(p1.returncode, 0, err1)
            self.assertEqual(p2.returncode, 0, err2)
            statuses = sorted([json.loads(out1)["status"], json.loads(out2)["status"]])
            self.assertEqual(statuses, ["CLAIMED", "EMPTY"])

    def test_bootstrap_glance_checks_and_claims_inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(Path(tmp), [{
                "id": "msg_boot",
                "name": "Mom",
                "text": "Bootstrap sees this",
                "ts": "2026-09-11T14:00:00Z",
            }])
            claim = lambda: inbox.claim_next(store, actor="bootstrap-test")
            with patch.object(atlas, "_yard_inbox_claim_next", side_effect=claim):
                glance = atlas.build_live_bootstrap_glance()
            self.assertEqual(glance["schema"], "bootstrap.v1")
            self.assertEqual(glance["yard_inbox"]["status"], "CLAIMED")
            self.assertEqual(glance["yard_inbox"]["message"]["id"], "msg_boot")
            self.assertEqual(glance["bootstrap_end"]["status"], "COMPLETE")
            encoded = json.dumps(glance, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            self.assertLessEqual(len(encoded), atlas.BOOTSTRAP_GLANCE_MAX_BYTES)


if __name__ == "__main__":
    unittest.main()
