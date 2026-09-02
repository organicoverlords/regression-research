import json
import unittest
from pathlib import Path

from tools.issue193_refresh_result import (
    CANARY_DEFINITIONS,
    EXACT_REFRESH_STIMULUS,
    MIN_INDEPENDENT_TREATMENT_PAIRS_FOR_H1_SUPPORT,
    PROHIBITED_METHOD_CATEGORIES,
    PROHIBITED_MUTATION_CATEGORIES,
    REQUIRED_MEASUREMENTS,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "03 Fixtures and Experiments" / "issue193-prospective-refresh-binding-protocol.json"


class Issue193RefreshProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(PROTOCOL.read_text(encoding="utf-8"))

    def test_control_and_treatment_use_same_bounded_canaries(self):
        phases = {phase["id"]: phase["sequence"] for phase in self.data["phases"]}
        self.assertEqual(phases["control"][0], "canaries")
        self.assertEqual(phases["control"][-1], "same_canaries")
        self.assertEqual(phases["treatment"][0], "canaries")
        self.assertEqual(phases["treatment"][-1], "same_canaries")
        self.assertTrue(all(canary["max_calls_per_phase"] <= 1 for canary in self.data["canaries"]))
        self.assertEqual(self.data["recovery_limit"], "maximum one rediscovery after failure; no extra retries")

    def test_runtime_contract_matches_preregistration(self):
        fixture_canaries = {canary["id"]: {k: v for k, v in canary.items() if k != "id"} for canary in self.data["canaries"]}
        self.assertEqual(CANARY_DEFINITIONS, fixture_canaries)
        self.assertEqual(REQUIRED_MEASUREMENTS, set(self.data["measurements"]))
        self.assertEqual(EXACT_REFRESH_STIMULUS, self.data["exact_refresh_stimulus"])
        self.assertEqual(
            MIN_INDEPENDENT_TREATMENT_PAIRS_FOR_H1_SUPPORT,
            self.data["pairing"]["minimum_independent_treatment_pairs_for_H1_support"],
        )

    def test_treatment_is_exact_and_support_requires_replication(self):
        self.assertEqual(self.data["exact_refresh_stimulus"], "refresh your memory")
        self.assertEqual(self.data["pairing"]["minimum_independent_treatment_pairs_for_H1_support"], 2)
        rule = self.data["decision_rule"]
        self.assertIn("controls remain stable", rule["support_H1"])
        self.assertIn("reproduction only", rule["single_occurrence"])
        self.assertIn("failures occur before treatment", rule["weaken_H1"])

    def test_protocol_keeps_live_configuration_unchanged(self):
        prohibited = set(self.data["prohibited_mutations"])
        self.assertEqual(prohibited, PROHIBITED_MUTATION_CATEGORIES)
        self.assertTrue({"ChatGPT memory", "Personal Instructions", "Settings", "server topology", "Tailscale", "connector deployment"} <= prohibited)
        self.assertEqual(self.data["stop_rule"], "stop on first route-surface change")
        self.assertEqual(set(self.data["prohibited_methods"]), PROHIBITED_METHOD_CATEGORIES)
        self.assertIn("concurrency/load test", self.data["prohibited_methods"])
        self.assertIn("worker creation", self.data["prohibited_methods"])
        self.assertIn("server restarts", self.data["prohibited_methods"])

    def test_measurements_separate_client_surface_from_local_arrival(self):
        measurements = set(self.data["measurements"])
        self.assertIn("direct_recipient_callable", measurements)
        self.assertIn("matching_local_request_start", measurements)
        self.assertIn("sibling_route_health", measurements)
        self.assertIn("exact_client_error_class", measurements)


if __name__ == "__main__":
    unittest.main()
