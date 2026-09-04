import copy
import unittest

from tools.capability_routing import CapabilityRoutingError, load_policy, validate_policy


class CapabilityRoutingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy()

    def test_current_policy_validates(self):
        self.assertIs(validate_policy(self.policy), self.policy)

    def test_required_capabilities_cannot_disappear(self):
        candidate = copy.deepcopy(self.policy)
        del candidate["capabilities"]["source_read"]
        with self.assertRaisesRegex(CapabilityRoutingError, "missing capabilities"):
            validate_policy(candidate)

    def test_coordination_keeps_one_authority(self):
        candidate = copy.deepcopy(self.policy)
        candidate["capabilities"]["coordination"]["ordered_adapter_roles"] = ["live_ownership", "alternate_ownership"]
        with self.assertRaisesRegex(CapabilityRoutingError, "coordination must have exactly one authority"):
            validate_policy(candidate)

    def test_memory_read_and_write_boundaries_are_validated(self):
        read_candidate = copy.deepcopy(self.policy)
        read_candidate["capabilities"]["memory_read"]["side_effects"] = "allowed"
        with self.assertRaisesRegex(CapabilityRoutingError, "memory reads must be side-effect free"):
            validate_policy(read_candidate)

        write_candidate = copy.deepcopy(self.policy)
        write_candidate["capabilities"]["memory_write"]["requires"] = "implicit"
        with self.assertRaisesRegex(CapabilityRoutingError, "memory writes must require explicit user authorization"):
            validate_policy(write_candidate)

    def test_core_policy_rejects_provider_specific_adapter_roles(self):
        candidate = copy.deepcopy(self.policy)
        candidate["capabilities"]["source_read"]["ordered_adapter_roles"] = ["github_read"]
        with self.assertRaisesRegex(CapabilityRoutingError, "provider/tool name leaked"):
            validate_policy(candidate)


if __name__ == "__main__":
    unittest.main()
