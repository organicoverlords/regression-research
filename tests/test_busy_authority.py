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
        self.assertEqual(state["authority"], "mcp_busy_claim")
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

    def test_read_only_and_independent_work_do_not_need_claim(self):
        for operation in ("read_only", "independent_mutation"):
            result = admit_operation("worker-a", "repo:file-a", operation, [], policy=self.policy)
            self.assertEqual(result["decision"], "allow")

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
