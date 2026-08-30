import json
import unittest
from pathlib import Path

from tools.capability_routing import (
    CapabilityRoutingError,
    load_policy,
    resolve_reachable_roles,
    select_adapter,
    validate_policy,
)


ROOT = Path(__file__).resolve().parents[1]


class CapabilityRoutingTests(unittest.TestCase):
    def setUp(self):
        self.policy = validate_policy(load_policy())

    def test_primary_route_is_selected_when_available(self):
        result = select_adapter(
            "source_read",
            {"source_native_read", "verified_local_read", "public_read"},
            policy=self.policy,
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["adapter_role"], "source_native_read")

    def test_failed_primary_uses_only_declared_fallback(self):
        result = select_adapter(
            "source_read",
            {"source_native_read", "verified_local_read", "public_read"},
            failed_roles={"source_native_read"},
            policy=self.policy,
        )
        self.assertEqual(result["adapter_role"], "verified_local_read")

    def test_coordination_failure_never_invents_second_authority(self):
        result = select_adapter("coordination", set(), policy=self.policy)
        self.assertEqual(result["status"], "degraded")
        self.assertIsNone(result["adapter_role"])
        self.assertEqual(result["fallback_mode"], "no_second_authority")
        self.assertEqual(result["next_action"], "continue_read_only_and_independent_work")

    def test_process_only_surface_can_reach_live_ownership_indirectly(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "capability-routing-indirect-route.json").read_text(encoding="utf-8")
        )
        result = select_adapter(
            fixture["capability"],
            fixture["visible_roles"],
            role_providers=fixture["role_providers"],
            policy=self.policy,
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["adapter_role"], "live_ownership")

    def test_failed_process_provider_does_not_fabricate_coordination(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "capability-routing-indirect-route.json").read_text(encoding="utf-8")
        )
        result = select_adapter(
            fixture["capability"],
            fixture["visible_roles"],
            role_providers=fixture["role_providers"],
            failed_roles={"process_execution"},
            policy=self.policy,
        )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["fallback_mode"], "no_second_authority")

    def test_generator_failed_provider_does_not_get_consumed_before_reachability(self):
        fixture = json.loads(
            (ROOT / "tests" / "fixtures" / "capability-routing-indirect-route.json").read_text(encoding="utf-8")
        )
        result = select_adapter(
            fixture["capability"],
            fixture["visible_roles"],
            role_providers=fixture["role_providers"],
            failed_roles=(role for role in ["process_execution"]),
            policy=self.policy,
        )
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["fallback_mode"], "no_second_authority")

    def test_reachable_roles_expand_only_from_reachable_providers(self):
        reachable = resolve_reachable_roles(
            {"outer_transport"},
            role_providers={
                "outer_transport": ["process_execution"],
                "process_execution": ["live_ownership"],
            },
        )
        self.assertEqual(reachable, {"outer_transport", "process_execution", "live_ownership"})

    def test_failed_process_provider_keeps_sibling_provider_reachable(self):
        result = select_adapter(
            "coordination",
            {"direct_process_start", "interactive_process_session"},
            failed_roles={"direct_process_start"},
            role_providers={
                "direct_process_start": ["process_execution"],
                "interactive_process_session": ["process_execution"],
                "process_execution": ["live_ownership"],
            },
            policy=self.policy,
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["adapter_role"], "live_ownership")

    def test_role_provider_generators_survive_validation_and_remain_reachable(self):
        reachable = resolve_reachable_roles(
            {"outer_transport"},
            role_providers={
                "outer_transport": (role for role in ["process_execution"]),
                "process_execution": (role for role in ["live_ownership"]),
            },
        )
        self.assertEqual(reachable, {"outer_transport", "process_execution", "live_ownership"})

    def test_string_role_provider_is_rejected_instead_of_split_into_characters(self):
        with self.assertRaisesRegex(CapabilityRoutingError, "iterable of role strings, not a string"):
            resolve_reachable_roles(
                {"outer_transport"},
                role_providers={"outer_transport": "live_ownership"},
            )

    def test_string_available_roles_is_rejected(self):
        with self.assertRaisesRegex(CapabilityRoutingError, "iterable of role strings, not a string"):
            resolve_reachable_roles("outer_transport")

    def test_one_capability_failure_does_not_collapse_another(self):
        failed_source = select_adapter("source_read", set(), policy=self.policy)
        healthy_validation = select_adapter(
            "runtime_validate",
            {"local_runtime_validation"},
            policy=self.policy,
        )
        self.assertEqual(failed_source["status"], "degraded")
        self.assertEqual(failed_source["failure_scope"], "capability_local")
        self.assertEqual(healthy_validation["status"], "selected")
        self.assertEqual(healthy_validation["adapter_role"], "local_runtime_validation")

    def test_memory_read_is_side_effect_free_and_write_is_explicit(self):
        capabilities = self.policy["capabilities"]
        self.assertEqual(capabilities["memory_read"]["side_effects"], "forbidden")
        self.assertEqual(capabilities["memory_write"]["requires"], "explicit_user_authorization")

    def test_unknown_capability_fails_closed_without_affecting_known_routes(self):
        with self.assertRaises(CapabilityRoutingError):
            select_adapter("imaginary_capability", set(), policy=self.policy)
        healthy = select_adapter("schedule", {"scheduler_adapter"}, policy=self.policy)
        self.assertEqual(healthy["status"], "selected")

    def test_core_policy_contains_no_provider_specific_adapter_roles(self):
        validate_policy(self.policy)


if __name__ == "__main__":
    unittest.main()
