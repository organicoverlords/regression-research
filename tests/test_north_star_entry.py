import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTIVE = (
    "- In this repository, before substantive stack/policy, BUSY/MCP, plugin-routing, "
    "memory-boundary, or regression work, read the current `NORTH_STAR.md` and use it as "
    "project direction. It does not override current user instructions, live repo/runtime "
    "evidence, or these operating rules."
)


class NorthStarEntryTests(unittest.TestCase):
    def test_agents_requires_current_north_star_before_substantive_stack_work(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(DIRECTIVE), 1)

    def test_north_star_exposes_current_project_direction_and_finish_line(self):
        north_star = (ROOT / "NORTH_STAR.md").read_text(encoding="utf-8")
        for required in (
            "# Assistant Stack North Star",
            "Status: **PRODUCT DIRECTION.**",
            "## North star",
            "The stack should be boring to use.",
            "## The anti-regression contract",
            "## What finished looks like",
        ):
            self.assertIn(required, north_star)

    def test_orientation_keeps_north_star_distinct_from_operating_authority(self):
        self.assertIn("project direction", DIRECTIVE)
        self.assertIn("does not override current user instructions", DIRECTIVE)
        self.assertIn("or these operating rules", DIRECTIVE)


if __name__ == "__main__":
    unittest.main()
