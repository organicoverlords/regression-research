import unittest

from tools.wip_hygiene import classify_path


class WipHygieneTests(unittest.TestCase):
    def test_research_evidence_remains_visible_wip(self):
        self.assertEqual(classify_path("01 Reports/new-audit.md"), "research_wip")
        self.assertEqual(classify_path("03 Fixtures and Experiments/new-case.json"), "research_wip")

    def test_private_temp_classes_are_explicit(self):
        self.assertEqual(classify_path("tmp-main-brave-history.sqlite"), "private_temp")
        self.assertEqual(classify_path("tmp-chatport-history-copy.sqlite"), "private_temp")
        self.assertEqual(classify_path("tmp-cloudflare-ab/cloudflared.log"), "private_temp")
        self.assertEqual(classify_path("tmp-current-chat-cdp.mjs"), "private_temp")

    def test_unknown_wip_is_not_silently_ignored(self):
        self.assertEqual(classify_path("mystery-output.bin"), "unclassified")


if __name__ == "__main__":
    unittest.main()
