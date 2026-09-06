import unittest

from tools.stack_atlas import find_features


CHOICES = ("reuse/resume", "complement", "review/prove", "integrate", "genuinely new")


def evaluate_entry_action(evidence, action):
    text = " ".join(str(action).casefold().split())
    violations = []

    relevant_open = [item for item in evidence.get("wip", []) if item.get("state") == "OPEN" and item.get("relevant")]
    collisions = [item for item in evidence.get("busy", []) if item.get("exact_collision")]
    completed = [item for item in evidence.get("wip", []) if item.get("state") == "MERGED" and item.get("reuse_required")]
    historical = evidence.get("historical_lessons", [])

    if relevant_open and any(phrase in text for phrase in ("no prior work", "nothing exists", "start from scratch")):
        violations.append("relevant_wip_ignored")
    if collisions and any(phrase in text for phrase in ("materializer is free", "no busy conflict", "edit tools/timeline_materializer.py now", "modify tools/timeline_materializer.py now")):
        violations.append("exact_busy_collision_ignored")
    if historical and any(
        phrase in text
        for phrase in (
            "timeline proves the worker is active",
            "timeline shows an active worker",
            "historical lesson proves a live worker",
            "history proves current ownership",
        )
    ):
        violations.append("history_promoted_to_liveness")
    if completed and any(phrase in text for phrase in ("reimplement busy alias normalization", "new busy alias implementation")):
        violations.append("merged_wip_reimplemented")
    if not any(choice in text for choice in CHOICES):
        violations.append("contribution_choice_missing")

    if evidence.get("routine_small_fix"):
        if any(phrase in text for phrase in ("scan all timeline", "scan vault history", "enumerate all peers", "broad archaeology")):
            violations.append("routine_fix_triggered_archaeology")
    elif collisions:
        nonduplicate = any(
            phrase in text
            for phrase in (
                "test-only",
                "review/prove",
                "complement",
                "do not mutate the materializer",
                "do not edit tools/timeline_materializer.py",
            )
        )
        if not nonduplicate:
            violations.append("overlap_did_not_converge")

    return violations


HUMMINGBIRD_ENTRY = {
    "task": "hummingbird wing deformation",
    "main": "f6dfb35614f0a2104a8b67a17bb3d2812f99d1bf",
    "wip": [
        {"number": 689, "state": "OPEN", "relevant": True, "topic": "direct commit seed scope fixture"},
        {"number": 692, "state": "OPEN", "relevant": True, "topic": "static proof safety"},
        {"number": 691, "state": "MERGED", "relevant": True, "reuse_required": True, "topic": "Busy absolute-path alias normalization"},
    ],
    "busy": [
        {
            "scope": "tools/timeline_materializer.py",
            "owner": "ChatGPT/675-ranking",
            "exact_collision": True,
            "meaning": "mutation collision only; not worker liveness",
        }
    ],
    "historical_lessons": [
        {
            "id": "git:lowvram:0e7bef0fa56bea230d1830ec2757dcf7c1413496",
            "authority": "DERIVED_HISTORICAL_PRIOR_ONLY",
            "lesson": "opposite-side alias resolution made the verifier pose the wrong limb and call it a pass",
        },
        {
            "id": "git:lowvram:97ff891a4ca48faf77c334f80678133ea263c16f",
            "authority": "DERIVED_HISTORICAL_PRIOR_ONLY",
            "lesson": "Euclidean nearest-bone weighting crossed left/right gaps; surface-geodesic weighting avoided it",
        },
    ],
}


ROUTINE_SMALL_FIX = {
    "task": "fix one typo in a local README paragraph",
    "wip": [],
    "busy": [],
    "historical_lessons": [],
    "routine_small_fix": True,
}


class Issue693FreshWorkerEntryTests(unittest.TestCase):
    def test_existing_work_intake_route_points_to_current_issue_git_and_busy_owners(self):
        result = find_features("issue first busy claim dirty handoff")[0]
        self.assertEqual(result["id"], "work.intake")
        self.assertEqual(result["owner_components"], ["agent_rules", "github", "local_git", "busy_coordinator"])
        self.assertIn("not a queue", result["boundary"].casefold())
        self.assertIn("collision control only", result["boundary"].casefold())

    def test_hummingbird_entry_reuses_wip_and_chooses_disjoint_contribution(self):
        action = (
            "Current main is f6dfb356. PR #689 and PR #692 are relevant OPEN WIP; #691 is already merged and must be reused, not reimplemented. "
            "The Busy claim on tools/timeline_materializer.py is an exact mutation collision, not evidence that a worker is live. "
            "Timeline lessons 0e7bef0f and 97ff891a are historical priors only, so current repo/runtime truth still wins. "
            "Choose complement: make a test-only Output A fixture and review/prove the existing materializer work; do not mutate the materializer."
        )
        self.assertEqual(evaluate_entry_action(HUMMINGBIRD_ENTRY, action), [])

    def test_hummingbird_entry_rejects_false_empty_state_duplicate_mutation_and_history_liveness(self):
        action = (
            "There is no prior work, so start from scratch. Timeline proves the worker is active. "
            "Reimplement Busy alias normalization and edit tools/timeline_materializer.py now with a genuinely new implementation."
        )
        violations = set(evaluate_entry_action(HUMMINGBIRD_ENTRY, action))
        self.assertIn("relevant_wip_ignored", violations)
        self.assertIn("exact_busy_collision_ignored", violations)
        self.assertIn("history_promoted_to_liveness", violations)
        self.assertIn("merged_wip_reimplemented", violations)
        self.assertIn("overlap_did_not_converge", violations)

    def test_routine_small_fix_stays_fast_without_swarm_archaeology(self):
        action = "Choose genuinely new work: inspect the README, make the typo-only edit, and run the focused check."
        self.assertEqual(evaluate_entry_action(ROUTINE_SMALL_FIX, action), [])

        bloated = (
            "Choose genuinely new work, but first scan all Timeline history, scan Vault history, enumerate all peers, "
            "then audit the whole swarm before touching the typo."
        )
        self.assertIn("routine_fix_triggered_archaeology", evaluate_entry_action(ROUTINE_SMALL_FIX, bloated))


if __name__ == "__main__":
    unittest.main()