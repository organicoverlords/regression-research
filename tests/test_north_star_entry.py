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

    def test_shared_contract_keeps_go_scoped_and_stop_immediate(self):
        rules = (RULES_ROOT / "RULES.md").read_text(encoding="utf-8")
        agents = (RULES_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("For an ongoing manual/on-demand swarm `go`/`continue`", rules)
        self.assertIn("the inherited scope is the user's established project/product engineering goal", rules)
        self.assertIn("not the currently open issue/PR/branch/worktree", rules)
        self.assertIn("the next highest-value safe supported contribution from canonical open issues or the repo North Star", rules)
        self.assertIn("A worker has no issue lane to defend", rules)
        self.assertIn("`stop` means stop immediately", rules)
        self.assertIn("follow the `go`/`continue` completion and yield semantics in `RULES.md`", agents)

    def test_north_star_is_pointer_only_to_canonical_agents_product_direction(self):
        north_star = (ROOT / "NORTH_STAR.md").read_text(encoding="utf-8")
        self.assertIn("# Assistant Stack North Star", north_star)
        self.assertIn("compatibility pointer only", north_star)
        self.assertIn("organicoverlords/agents@main", north_star)
        self.assertIn("docs/repos/regression-research/NORTH_STAR.md", north_star)
        self.assertIn("docs/repos/regression-research/STACK_ATLAS_NORTH_STAR.md", north_star)
        self.assertNotIn("## What finished looks like", north_star)
        self.assertNotIn("## Current focus", north_star)

    def test_orientation_keeps_canonical_north_star_distinct_from_operating_authority(self):
        north_star = (ROOT / "NORTH_STAR.md").read_text(encoding="utf-8")
        rules = (RULES_ROOT / "RULES.md").read_text(encoding="utf-8")
        self.assertIn("Current repository/runtime/issue/tool evidence remains live execution truth", north_star)
        self.assertIn("Current explicit user instruction defines the objective.", rules)
        self.assertIn("Current repo/runtime/tool evidence defines current facts.", rules)


if __name__ == "__main__":
    unittest.main()
