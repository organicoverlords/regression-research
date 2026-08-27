import json
import math
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "02 Evidence" / "issue193" / "2026-08-25_refresh-vs-continuation-retrospective.json"


class Issue193RefreshRetrospectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_two_refresh_treatments_both_have_pca_and_route_loss(self):
        treatments = self.data["treatments"]
        self.assertEqual(len(treatments), 2)
        for case in treatments:
            self.assertTrue(case["active_ancestry_contains_refresh"])
            self.assertTrue(case["pca_context_citations_present_during_refresh_turn"])
            self.assertGreater(case["max_pca_citation_count_on_refresh_turn"], 0)
            self.assertGreater(case["seconds_continuation_to_visible_loss"], 0)
            self.assertLess(case["seconds_continuation_to_visible_loss"], 60)

    def test_same_time_current_ancestry_is_nonrefreshed_and_mcp0_healthy(self):
        control = self.data["same_time_control"]
        self.assertEqual(control["refresh_nodes_on_current_node_ancestry"], 0)
        self.assertGreater(control["refresh_nodes_any_mapping"], 0)
        self.assertEqual(control["tool_calls_in_window"], 12)
        self.assertEqual(control["tool_results_in_window"], 12)
        self.assertEqual(control["tool_result_status_counts"], {"finished_successfully": 12})
        self.assertEqual(len(control["mcp0_call_paths"]), 12)
        self.assertTrue(all("/MCP0/" in path for path in control["mcp0_call_paths"]))

    def test_later_go_controls_keep_tool_surface_without_loss_signal(self):
        controls = self.data["later_continuation_controls"]
        self.assertEqual(len(controls), 6)
        self.assertTrue(all(not case["classified_route_loss"] for case in controls))
        self.assertTrue(all(not case["connector_loss_signals"] for case in controls))
        self.assertTrue(all(case["post_continuation_tool_calls"] >= 32 for case in controls))

    def test_exploratory_separation_is_descriptive_not_causal(self):
        counts = self.data["descriptive_counts"]
        self.assertEqual((counts["refresh_treatment_route_loss"], counts["refresh_treatment_total"]), (2, 2))
        self.assertEqual((counts["later_control_route_loss"], counts["later_control_total"]), (0, 6))
        expected = math.comb(2, 2) * math.comb(6, 0) / math.comb(8, 2)
        self.assertAlmostEqual(counts["exploratory_one_sided_fisher_exact_p"], expected)
        self.assertIn("not_proven", self.data["interpretation"])
        self.assertIn("prospective", self.data["interpretation"]["not_proven"].lower())


if __name__ == "__main__":
    unittest.main()
