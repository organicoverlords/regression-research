import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES_ROOT = Path(r"C:\Users\Lauri\.agents")


class NorthStarEntryTests(unittest.TestCase):
    def test_agents_points_to_canonical_shared_contract(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn(r"C:\Users\Lauri\.agents\RULES.md", agents)
        self.assertIn(r"C:\Users\Lauri\.agents\AGENTS.md", agents)
        self.assertIn("https://github.com/organicoverlords/agents", agents)
        self.assertIn("pointer-only", agents)

    def test_shared_rules_keep_live_authority_and_history_boundary(self):
        rules = (RULES_ROOT / "RULES.md").read_text(encoding="utf-8")
        self.assertIn("Current explicit user instruction defines the objective.", rules)
        self.assertIn("Current repo/runtime/tool evidence defines current facts.", rules)
        self.assertIn("Vault history are evidence only", rules)
        self.assertIn("Stack Atlas", rules)

    def test_shared_contract_keeps_go_open_ended_and_stop_task_level(self):
        rules = (RULES_ROOT / "RULES.md").read_text(encoding="utf-8")
        agents = (RULES_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("a `go` turn is not a one-slice checkpoint", rules)
        self.assertIn("Stop only for a concrete task-level blocker", rules)
        self.assertIn("continue through nonblocking waits instead of polling or stopping early", agents)

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
        north_star = (ROOT / "NORTH_STAR.md").read_text(encoding="utf-8")
        rules = (RULES_ROOT / "RULES.md").read_text(encoding="utf-8")
        self.assertIn("Status: **PRODUCT DIRECTION.**", north_star)
        self.assertIn("Current explicit user instruction defines the objective.", rules)
        self.assertIn("Current repo/runtime/tool evidence defines current facts.", rules)


if __name__ == "__main__":
    unittest.main()
