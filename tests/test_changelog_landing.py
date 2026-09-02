import importlib.util
import tempfile
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

    def test_substantive_change_does_not_require_timeline_edit(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("substantive PR changed without CHANGELOG.md", source)
        self.assertNotIn("substantive PR needs a newly added", source)

    def test_projection_is_merge_stable(self):
        readme = "# Vault\n\n" + MODULE.projection("ignored") + "\n\nBody\n"
        first = MODULE.projected_readme(readme, "- [2026-09-02] First")
        second = MODULE.projected_readme(readme, "- [2026-09-02] Second")
        self.assertEqual(first, second)

    def test_write_utf8_lf_is_platform_stable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "README.md"
            MODULE.write_utf8_lf(path, "a\r\nb\r")
            self.assertEqual(path.read_bytes(), b"a\nb\n")


if __name__ == "__main__":
    unittest.main()
