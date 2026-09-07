import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRE_REPAIR = ROOT / "02 Evidence" / "issue122" / "2026-08-25_122229_EEST_pre-repair-memory-block.txt"
LEDGER = ROOT / "02 Evidence" / "issue122" / "2026-08-27_canonical-claim-evidence-ledger.md"
ATTRS = ROOT / ".gitattributes"


class Issue122ForensicIntegrityTests(unittest.TestCase):
    def test_pre_repair_memory_preserves_exact_raw_chatport_bytes(self):
        data = PRE_REPAIR.read_bytes()
        self.assertEqual(len(data), 5804)
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            "6db44de30f4871a54f2552c344677f176bae5520d0593b0669b404a7c145dede",
        )
        git_object = b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        self.assertEqual(hashlib.sha1(git_object).hexdigest(), "3be47b2b78aab9f20bf5cbfc39a573056de5438f")
        self.assertIn(b"\r\n", data)
        self.assertIn(b"\n\n\n\nROLES.", data)

    def test_exact_artifact_is_exempt_from_text_normalization(self):
        line = (
            '"02 Evidence/issue122/2026-08-25_122229_EEST_pre-repair-memory-block.txt" '
            "-text whitespace=cr-at-eol"
        )
        self.assertEqual(ATTRS.read_text(encoding="ascii").strip(), line)

    def test_ledger_uses_branch_aware_counts_and_pins_later_provenance(self):
        text = LEDGER.read_text(encoding="utf-8")
        self.assertIn("123 minimal direct non-async GPT-5.6 turns", text)
        self.assertIn("6,697 assistant code/tool-call nodes", text)
        self.assertIn("C14 supersedes C12's flattened `126 / 7,195`", text)
        self.assertNotIn("and 126 minimal direct GPT-5.6 prompts", text)
        for comment_id in ("#5439052260", "#5439082005", "#5439169350"):
            with self.subTest(comment_id=comment_id):
                self.assertIn(comment_id, text)
        self.assertIn("d84e78b1939244532913c5a970850c9085865c372685bd9a3e70a8352d876929", text)
        self.assertIn("Context/mission continuity is directly user-authored by Aug 20", text)


if __name__ == "__main__":
    unittest.main()
