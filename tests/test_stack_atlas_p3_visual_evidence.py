from __future__ import annotations

import unittest

from tools.stack_atlas import atlas_lookup, component_details, find_features


class P3VisualEvidenceAtlasTests(unittest.TestCase):
    def test_p3_visual_evidence_navigation_uses_durable_root_index(self) -> None:
        for alias in ("p3_visual_evidence", "p3 proof library"):
            with self.subTest(alias=alias):
                details = atlas_lookup(alias)
                self.assertEqual(details["id"], "project.p3_visual_evidence")
                self.assertEqual(details["kind"], "feature_navigation")
                self.assertEqual(details["index"], r"G:\Oma Drive\P3 Visual Evidence\p3\index-v1.json")
                self.assertIn("ConvertFrom-Json", details["query"])
                self.assertIn("Google Drive My Drive", details["boundary"])
                self.assertIn("ChatGPT Library", details["boundary"])
                self.assertIn("native Library file to open/render", details["boundary"])
                self.assertIn("consumer gate unmet", details["boundary"])
                self.assertIn("Do not recursively scan", details["boundary"])
                self.assertIn("MCP media payloads/base64/custom HTTP/Git-LFS", details["boundary"])
                self.assertIn("NOT_RECORDED", details["boundary"])

        self.assertEqual(find_features("lane war proof", limit=1)[0]["id"], "project.p3_visual_evidence")
        self.assertEqual(find_features("meteor proof", limit=1)[0]["id"], "project.p3_visual_evidence")
        with self.assertRaises(KeyError):
            component_details("p3_visual_evidence")


if __name__ == "__main__":
    unittest.main()
