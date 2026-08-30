import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check_changelog_landing.py"
SPEC = importlib.util.spec_from_file_location("check_changelog_landing", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ChangelogLandingTests(unittest.TestCase):
    def test_unreleased_lines_rejects_merge_conflict_markers(self):
        changelog = """# Changelog

## [Unreleased]

<<<<<<< HEAD
- [2026-08-29] one
=======
- [2026-08-29] two
>>>>>>> origin/main
"""
        with self.assertRaisesRegex(SystemExit, "merge-conflict marker"):
            MODULE.unreleased_lines(changelog)

    def test_repository_changelog_has_no_merge_conflict_markers(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        MODULE.unreleased_lines(changelog)


if __name__ == "__main__":
    unittest.main()
