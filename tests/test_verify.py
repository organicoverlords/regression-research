import unittest
from unittest.mock import patch

from tools.verify import changed_files, select_areas


class VerifyTests(unittest.TestCase):
    def test_selects_only_affected_area(self):
        self.assertEqual(select_areas({"tools/capability_routing.py"}), ["stack"])
        self.assertEqual(select_areas({"tools/connector_reliability.py"}), ["stack"])
        self.assertEqual(select_areas({"tools/conversation_search.py"}), ["conversation"])
        self.assertEqual(select_areas({"README.md"}), [])

    def test_verifier_changes_run_every_area(self):
        self.assertEqual(
            select_areas({"tools/verify.py"}),
            ["stack", "conversation"],
        )

    def test_all_runs_every_area(self):
        self.assertEqual(select_areas(set(), run_all=True), ["stack", "conversation"])

    @patch("tools.verify.subprocess.check_output")
    def test_changed_files_normalizes_git_paths(self, check_output):
        check_output.side_effect = [
            "README.md\n",
            "tools\\verify.py\n",
            "tests/test_verify.py\n",
        ]
        self.assertEqual(
            changed_files("origin/main"),
            {"tools/verify.py", "tests/test_verify.py", "README.md"},
        )


if __name__ == "__main__":
    unittest.main()
