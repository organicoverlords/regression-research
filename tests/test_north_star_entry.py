import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTIVE = (
    "- In this repository, before substantive stack/policy, BUSY/MCP, plugin-routing, "
    "memory-boundary, or regression work, read the current `NORTH_STAR.md` and use it as "
    "project direction. It does not override current user instructions, live repo/runtime "
    "evidence, or these operating rules."
)

BOOTSTRAP_COMMAND = r"python C:\Users\Lauri\Desktop\vault\tools\memory_bank.py bootstrap"
BOOTSTRAP_RETRY = "On failure retry that exact command once"
BOOTSTRAP_CONTINUE = "after a second failure continue from current instruction, policy, and verified live state instead of debugging memory"


INVESTIGATION_ADMISSION = (
    "- Bounded read-only orientation may remain unclaimed. Before crossing into substantive "
    "investigation or analysis on an exact issue/scope, acquire that exact durable scope in the "
    "standalone BusyCoordinator; if another live owner already holds it, yield that scope and "
    "choose non-duplicative work."
)


class NorthStarEntryTests(unittest.TestCase):
    def test_agents_requires_current_north_star_before_substantive_stack_work(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(DIRECTIVE), 1)


    def test_fresh_local_session_bootstrap_failure_stays_bounded(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(BOOTSTRAP_COMMAND), 1)
        self.assertEqual(agents.count(BOOTSTRAP_RETRY), 1)
        self.assertEqual(agents.count(BOOTSTRAP_CONTINUE), 1)
        self.assertLess(agents.index(BOOTSTRAP_COMMAND), agents.index(BOOTSTRAP_RETRY))
        self.assertLess(agents.index(BOOTSTRAP_RETRY), agents.index(BOOTSTRAP_CONTINUE))

    def test_substantive_investigation_requires_exact_durable_admission(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(INVESTIGATION_ADMISSION), 1)
        self.assertIn("Bounded read-only orientation may remain unclaimed", INVESTIGATION_ADMISSION)
        self.assertIn("acquire that exact durable scope", INVESTIGATION_ADMISSION)
        self.assertIn("standalone BusyCoordinator", INVESTIGATION_ADMISSION)
        self.assertIn("yield that scope", INVESTIGATION_ADMISSION)

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

    def test_north_star_uses_standalone_coordinator_not_mcp_or_busy_as_authority(self):
        north_star = (ROOT / "NORTH_STAR.md").read_text(encoding="utf-8")
        self.assertIn("standalone BusyCoordinator", north_star)
        self.assertIn("transports, not ownership authorities", north_star)
        self.assertNotIn("Check live BUSY ownership", north_star)
        self.assertNotIn("Make live MCP ownership the only coordination authority", north_star)

    def test_orientation_keeps_north_star_distinct_from_operating_authority(self):
        self.assertIn("project direction", DIRECTIVE)
        self.assertIn("does not override current user instructions", DIRECTIVE)
        self.assertIn("or these operating rules", DIRECTIVE)


if __name__ == "__main__":
    unittest.main()
