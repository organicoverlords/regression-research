import unittest

from tools.busy_authority import BusyAuthorityError, admit_operation, load_policy, resolve_scope, validate_policy


class BusyAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.policy = validate_policy(load_policy())

    def test_github_busy_projection_without_live_claim_is_stale_and_non_authoritative(self):
        projection = {"surface": "github_issue_title", "scope": "repo:file-a", "owner": "worker-a"}
        state = resolve_scope("repo:file-a", [], [projection], policy=self.policy)
        self.assertEqual(state["state"], "unclaimed")
        self.assertIsNone(state["owner"])
        self.assertEqual(state["stale_projections"], [projection])

    def test_matching_projection_never_replaces_live_claim_authority(self):
        claim = {"scope": "repo:file-a", "owner": "worker-a", "live": True}
        projection = {"surface": "github_issue_title", "scope": "repo:file-a", "owner": "worker-a"}
        state = resolve_scope("repo:file-a", [claim], [projection], policy=self.policy)
        self.assertEqual(state["state"], "owned")
        self.assertEqual(state["owner"], "worker-a")
        self.assertEqual(state["authority"], "standalone_busy_coordinator")
        self.assertEqual(state["consistent_projections"], [projection])

    def test_conflicting_projection_loses_to_live_claim(self):
        claim = {"scope": "repo:file-a", "owner": "worker-a", "live": True}
        projection = {"surface": "github_issue_comment", "scope": "repo:file-a", "owner": "worker-b"}
        state = resolve_scope("repo:file-a", [claim], [projection], policy=self.policy)
        self.assertEqual(state["owner"], "worker-a")
        self.assertEqual(state["stale_projections"], [projection])

    def test_actor_with_exact_live_claim_may_mutate_shared_scope(self):
        claim = {"scope": "repo:file-a", "owner": "worker-a", "live": True}
        result = admit_operation("worker-a", "repo:file-a", "shared_mutation", [claim], policy=self.policy)
        self.assertEqual(result["decision"], "allow")

    def test_other_actor_live_claim_requires_yield(self):
        claim = {"scope": "repo:file-a", "owner": "worker-a", "live": True}
        result = admit_operation("worker-b", "repo:file-a", "shared_mutation", [claim], policy=self.policy)
        self.assertEqual(result["decision"], "yield")
        self.assertEqual(result["owner"], "worker-a")

    def test_unclaimed_shared_scope_requires_real_claim_even_if_projection_exists(self):
        projection = {"surface": "branch", "scope": "repo:file-a", "owner": "worker-a"}
        result = admit_operation("worker-a", "repo:file-a", "shared_mutation", [], [projection], policy=self.policy)
        self.assertEqual(result["decision"], "claim_required")
        self.assertEqual(result["stale_projections"], [projection])

    def test_read_only_and_unclaimed_independent_work_do_not_need_claim(self):
        for operation in ("read_only", "independent_mutation"):
            result = admit_operation("worker-a", "repo:file-a", operation, [], policy=self.policy)
            self.assertEqual(result["decision"], "allow")

    def test_independent_mutation_yields_to_exact_other_owner(self):
        claim = {"scope": "repo:file-a", "owner": "worker-a", "live": True}
        result = admit_operation("worker-b", "repo:file-a", "independent_mutation", [claim], policy=self.policy)
        self.assertEqual(result["decision"], "yield")
        self.assertEqual(result["reason"], "another_actor_holds_exact_live_claim")
        self.assertEqual(result["owner"], "worker-a")

    def test_independent_mutation_by_exact_owner_remains_claim_optional(self):
        claim = {"scope": "repo:file-a", "owner": "worker-a", "live": True}
        result = admit_operation("worker-a", "repo:file-a", "independent_mutation", [claim], policy=self.policy)
        self.assertEqual(result["decision"], "allow")
        self.assertEqual(result["reason"], "claim_not_required")

    def test_policy_uses_standalone_busy_coordinator_as_live_authority(self):
        self.assertEqual(self.policy["live_authority"], "standalone_busy_coordinator")

    def test_ownership_resolution_explicitly_does_not_prove_worker_execution(self):
        claim = {"scope": "repo:file-a", "owner": "worker-a", "live": True}
        state = resolve_scope("repo:file-a", [claim], policy=self.policy)
        self.assertEqual(state["authority_scope"], "ownership_only")
        self.assertFalse(state["proves_worker_execution"])
        self.assertTrue(self.policy["invariants"]["ownership_claim_never_proves_worker_execution"])

    def test_substantive_investigation_is_read_only_for_busy_ownership(self):
        for coordination_available in (True, False):
            result = admit_operation(
                "worker-a",
                "repo:issue-125",
                "substantive_investigation",
                [{"scope": "repo:issue-125", "owner": "worker-b", "live": True}],
                coordination_available=coordination_available,
                policy=self.policy,
            )
            self.assertEqual(result["decision"], "allow")
            self.assertEqual(result["reason"], "claim_not_required")

    def test_coordination_outage_creates_no_second_authority(self):
        projection = {"surface": "github_issue_title", "scope": "repo:file-a", "owner": "worker-a"}
        result = admit_operation(
            "worker-a",
            "repo:file-a",
            "shared_mutation",
            [],
            [projection],
            coordination_available=False,
            policy=self.policy,
        )
        self.assertEqual(result["decision"], "defer_shared_mutation")
        self.assertEqual(result["reason"], "coordination_unavailable_no_fallback_authority")

    def test_different_scope_claim_does_not_block(self):
        claim = {"scope": "repo:file-b", "owner": "worker-b", "live": True}
        result = admit_operation("worker-a", "repo:file-a", "shared_mutation", [claim], policy=self.policy)
        self.assertEqual(result["decision"], "claim_required")

    def test_duplicate_live_claims_for_exact_scope_fail_closed(self):
        claims = [
            {"scope": "repo:file-a", "owner": "worker-a", "live": True},
            {"scope": "repo:file-a", "owner": "worker-b", "live": True},
        ]
        with self.assertRaises(BusyAuthorityError):
            resolve_scope("repo:file-a", claims, policy=self.policy)


if __name__ == "__main__":
    unittest.main()
