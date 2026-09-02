import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTIVE = (
    "- In this repository, before substantive stack/policy, BUSY/MCP, plugin-routing, "
    "memory-boundary, or regression work, read the current `NORTH_STAR.md` and use it as "
    "project direction. It does not override current user instructions, live repo/runtime "
    "evidence, or these operating rules."
)

NAVIGATION_HEADING = "### Navigation minimap"
ATLAS_ORDER = "Stack Atlas -> smallest relevant live authority -> targeted Vault history only when needed"
SEARCH_BEFORE_INVENTING = "If a capability seems missing, search Atlas before designing another"


INVESTIGATION_BOUNDARY = (
    "- Read-only investigation and analysis remain unclaimed. Use the standalone BusyCoordinator "
    "for mutation according to the shared coordination rule; do not create claims merely to think, "
    "inspect, or answer."
)

BIG_CHANGE_INTERRUPT = (
    "- Before a large or hard-to-reverse mutation or landing step, such as a broad rebase/rewrite, "
    "architecture/control-plane/startup/memory change, large multi-file change, or PR merge, re-check "
    "the current user instruction and the exact BusyCoordinator scope, including scope-visible pending "
    "handoffs/findings. A newer stop, superseding handoff, or scope change interrupts immediately: "
    "preserve current work and do not continue, rebase, push, or merge from stale task state. This is "
    "a boundary check, not per-command polling; ordinary small edits do not repeatedly poll the coordinator."
)


class NorthStarEntryTests(unittest.TestCase):
    def test_agents_requires_current_north_star_before_substantive_stack_work(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(DIRECTIVE), 1)


    def test_vault_is_optional_history_not_startup(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(NAVIGATION_HEADING), 1)
        self.assertEqual(agents.count(ATLAS_ORDER), 1)
        self.assertEqual(agents.count(SEARCH_BEFORE_INVENTING), 1)
        self.assertNotIn("memory_bank.py bootstrap", agents)
        self.assertIn("Vault is history/evidence", agents)


    def test_read_only_investigation_never_claims_busy(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(INVESTIGATION_BOUNDARY), 1)
        self.assertIn("Read-only investigation and analysis remain unclaimed", INVESTIGATION_BOUNDARY)
        self.assertIn("standalone BusyCoordinator", INVESTIGATION_BOUNDARY)
        self.assertIn("do not create claims merely to think, inspect, or answer", INVESTIGATION_BOUNDARY)


    def test_large_worker_changes_recheck_current_interrupt_state(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertEqual(agents.count(BIG_CHANGE_INTERRUPT), 1)
        self.assertIn("scope-visible pending handoffs/findings", BIG_CHANGE_INTERRUPT)
        self.assertIn("newer stop, superseding handoff, or scope change", BIG_CHANGE_INTERRUPT)
        self.assertIn("not per-command polling", BIG_CHANGE_INTERRUPT)
        self.assertIn("do not continue, rebase, push, or merge from stale task state", BIG_CHANGE_INTERRUPT)

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
