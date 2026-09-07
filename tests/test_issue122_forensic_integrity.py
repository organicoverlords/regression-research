import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRE_REPAIR = ROOT / "02 Evidence" / "issue122" / "2026-08-25_122229_EEST_pre-repair-memory-block.txt"
LEDGER = ROOT / "02 Evidence" / "issue122" / "2026-08-27_canonical-claim-evidence-ledger.md"
ATTRS = ROOT / ".gitattributes"
SIBLING_SEARCH = ROOT / "02 Evidence" / "issue122" / "2026-09-07_false-boundary-sibling-search.json"


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

    def test_false_boundary_sibling_search_is_hash_bound_and_negative_only(self):
        data = json.loads(SIBLING_SEARCH.read_text(encoding="utf-8"))
        self.assertEqual(data["issue"], 122)
        self.assertEqual(data["source"]["mapping_nodes"], 829)
        self.assertEqual(
            data["source"]["sha256"],
            "d033b99f158486c291de82e003d718e20aa63b19e86f7f74900fe5fd2f02725b",
        )
        self.assertEqual(
            [(item["name"], item["path_nodes"], len(item["branch_points"])) for item in data["target_paths"]],
            [
                ("false_boundary_explanation_1716", 4, 0),
                ("premature_final_1743", 158, 0),
                ("premature_final_1819", 276, 0),
            ],
        )
        self.assertEqual(data["graph_control"]["total_branch_points"], 1)
        self.assertEqual(data["graph_control"]["branch_points"][0]["children"], 2)
        self.assertFalse(data["result"]["natural_retry_or_sibling_control_available"])
        self.assertEqual(data["result"]["classification"], "NEGATIVE_SOURCE_SEARCH")
        self.assertIn("does not prove or disprove", data["causal_limit"])

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
        self.assertIn("`issue.updatedAt` is comment-sensitive", text)
        self.assertIn(
            "a22d85efc6b88572ec30eff802c88eacd744da97c172461e3efe7003728c2bd6",
            text,
        )
        self.assertNotIn("canonical body `updatedAt`:", text)


if __name__ == "__main__":
    unittest.main()
