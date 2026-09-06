import json
import unittest
from pathlib import Path

from tools.stack_atlas import find_features


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "issue693_fresh_worker_entry.json"
CHOICES = ("reuse/resume", "complement", "review/prove", "integrate", "genuinely new")


def load_corpus():
    return json.loads(CORPUS.read_text(encoding="utf-8-sig"))


def case_to_evidence(case):
    current = case.get("current_truth", {})
    return {
        "task": case.get("task_text"),
        "main": (current.get("main") or {}).get("sha"),
        "wip": [
            {
                "number": item.get("number"),
                "state": item.get("state"),
                "relevant": True,
                "reuse_required": bool(item.get("reuse_required")),
            }
            for item in current.get("wip", [])
        ],
        "busy": [
            {
                "scope": item.get("scope"),
                "owner": item.get("actor"),
                "exact_collision": bool(item.get("exact_mutation_collision")),
                "meaning": "mutation collision only; not worker liveness",
            }
            for item in current.get("busy", [])
        ],
        "historical_lessons": case.get("historical_prior", []),
        "routine_small_fix": case.get("id") == "routine-small-fix-negative-control",
    }


def evaluate_reconstruction_action(case, action):
    text = " ".join(str(action).casefold().split())
    violations = []
    reconstruction = case.get("reconstruction", {})

    evidence_terms = {
        "runtime/listener continuity": ("runtime", "listener"),
        "MCP transport/error shape": ("transport",),
        "supervisor/restart boundaries": ("supervisor", "restart"),
        "worker completion/handoff output": ("worker", "handoff", "completion"),
        "repo PR/commit/merge throughput": ("commit", "merge", "throughput"),
        "configuration/deployment boundaries": ("configuration", "deployment", "cutover"),
    }
    missing_classes = [
        evidence_class
        for evidence_class in reconstruction.get("required_evidence_classes", [])
        if not any(term in text for term in evidence_terms[evidence_class])
    ]
    if missing_classes:
        violations.append("evidence_class_inventory_incomplete")

    if not any(phrase in text for phrase in ("candidate interval", "candidate window", "candidate period")):
        violations.append("candidate_intervals_missing")
    if not any(phrase in text for phrase in ("source completeness", "telemetry is incomplete", "enospc", "absence is unknown")):
        violations.append("source_completeness_not_checked")
    if not any(
        phrase in text
        for phrase in (
            "repo head is not runtime identity",
            "git head is not runtime identity",
            "serving runtime separately from repo head",
            "runtime identity separately from git head",
        )
    ):
        violations.append("runtime_repo_identity_conflated")

    for classification in reconstruction.get("classification_buckets", []):
        if classification not in text:
            violations.append("operating_state_classes_collapsed")
            break

    forbidden_anchors = (
        "user said working so the period is",
        "direct wording proves the period",
        "backend health proves the period",
        "one successful tool call proves",
        "repo head proves the serving runtime",
        "no transport rows means no activity",
    )
    if any(anchor in text for anchor in forbidden_anchors):
        violations.append("single_source_anchor_promoted")

    return violations


def evaluate_entry_action(evidence, action):
    text = " ".join(str(action).casefold().split())
    violations = []

    relevant_open = [item for item in evidence.get("wip", []) if item.get("state") == "OPEN" and item.get("relevant")]
    collisions = [item for item in evidence.get("busy", []) if item.get("exact_collision")]
    completed = [item for item in evidence.get("wip", []) if item.get("state") == "MERGED" and item.get("reuse_required")]
    historical = evidence.get("historical_lessons", [])

    if relevant_open and any(phrase in text for phrase in ("no prior work", "nothing exists", "start from scratch")):
        violations.append("relevant_wip_ignored")
    if collisions and any(
        phrase in text
        for phrase in (
            "materializer is free",
            "no busy conflict",
            "edit tools/timeline_materializer.py now",
            "modify tools/timeline_materializer.py now",
        )
    ):
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


class Issue693FreshWorkerEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load_corpus()
        cls.cases = {case["id"]: case for case in cls.corpus["cases"]}
        cls.hummingbird = case_to_evidence(cls.cases["hummingbird-overlap-current-wip"])
        cls.routine = case_to_evidence(cls.cases["routine-small-fix-negative-control"])
        cls.reconstruction = cls.cases["heterogeneous-period-reconstruction-regression"]

    def test_existing_work_intake_route_points_to_current_issue_git_and_busy_owners(self):
        result = find_features("issue first busy claim dirty handoff")[0]
        self.assertEqual(result["id"], "work.intake")
        self.assertEqual(result["owner_components"], ["agent_rules", "github", "local_git", "busy_coordinator"])
        self.assertIn("not a queue", result["boundary"].casefold())
        self.assertIn("collision control only", result["boundary"].casefold())

    def test_corpus_uses_issue_contribution_vocabulary_and_real_snapshot(self):
        self.assertEqual(tuple(self.corpus["contribution_modes"]), CHOICES)
        case = self.cases["hummingbird-overlap-current-wip"]
        self.assertEqual(case["task_text"], "hummingbird wing deformation")
        self.assertEqual(case["current_truth"]["main"]["sha"], "f6dfb35614f0a2104a8b67a17bb3d2812f99d1bf")
        self.assertEqual({item["number"] for item in case["current_truth"]["wip"]}, {689, 691, 692})

    def test_corpus_never_promotes_busy_or_history_to_liveness(self):
        case = self.cases["hummingbird-overlap-current-wip"]
        self.assertEqual(case["current_truth"]["peer_activity"]["status"], "UNKNOWN")
        self.assertTrue(all(item["liveness_inference"] == "FORBIDDEN" for item in case["current_truth"]["busy"]))
        self.assertTrue(all(item["authority"] == "HISTORICAL_PRIOR_ONLY" for item in case["historical_prior"]))
        self.assertTrue(case["expected"]["live_truth_still_required"])

    def test_hummingbird_entry_reuses_wip_and_chooses_disjoint_contribution(self):
        action = (
            "Current main is f6dfb356. PR #689 and PR #692 are relevant OPEN WIP; #691 is already merged and must be reused, not reimplemented. "
            "The Busy claim on tools/timeline_materializer.py is an exact mutation collision, not evidence that a worker is live. "
            "Timeline lessons 0e7bef0f and 97ff891a are historical priors only, so current repo/runtime truth still wins. "
            "Choose complement: make a test-only Output A fixture and review/prove the existing materializer work; do not mutate the materializer."
        )
        self.assertEqual(evaluate_entry_action(self.hummingbird, action), [])

    def test_hummingbird_entry_rejects_false_empty_state_duplicate_mutation_and_history_liveness(self):
        action = (
            "There is no prior work, so start from scratch. Timeline proves the worker is active. "
            "Reimplement Busy alias normalization and edit tools/timeline_materializer.py now with a genuinely new implementation."
        )
        violations = set(evaluate_entry_action(self.hummingbird, action))
        self.assertIn("relevant_wip_ignored", violations)
        self.assertIn("exact_busy_collision_ignored", violations)
        self.assertIn("history_promoted_to_liveness", violations)
        self.assertIn("merged_wip_reimplemented", violations)
        self.assertIn("overlap_did_not_converge", violations)

    def test_reconstruction_case_requires_cross_source_interval_model_before_narrow_archaeology(self):
        action = (
            "Inventory runtime/listener continuity, transport errors, supervisor/restart boundaries, worker completion/handoff output, "
            "commit/merge throughput, and configuration/deployment cutovers. Build candidate intervals from those hard transitions, "
            "then compare sustained behavior across the sources. Check source completeness: transport telemetry is incomplete because "
            "of ENOSPC, so absence is unknown rather than negative evidence. Identify the serving runtime separately from repo HEAD; "
            "repo HEAD is not runtime identity. Classify intervals as working/productive, degraded but usable, or broken/unusable. "
            "Only after the interval model exists should narrow archaeology identify the exact transition or rollback target."
        )
        self.assertEqual(evaluate_reconstruction_action(self.reconstruction, action), [])

    def test_reconstruction_case_rejects_single_source_shortcuts_and_missing_telemetry_as_negative_evidence(self):
        action = (
            "Search direct wording first. User said working so the period is the matching timestamp. Backend health proves the period. "
            "Repo HEAD proves the serving runtime, and no transport rows means no activity. Choose one interval immediately."
        )
        violations = set(evaluate_reconstruction_action(self.reconstruction, action))
        self.assertIn("evidence_class_inventory_incomplete", violations)
        self.assertIn("candidate_intervals_missing", violations)
        self.assertIn("source_completeness_not_checked", violations)
        self.assertIn("runtime_repo_identity_conflated", violations)
        self.assertIn("operating_state_classes_collapsed", violations)
        self.assertIn("single_source_anchor_promoted", violations)


    def test_routine_small_fix_stays_fast_without_swarm_archaeology(self):
        action = "Choose genuinely new work: inspect the README, make the typo-only edit, and run the focused check."
        self.assertEqual(evaluate_entry_action(self.routine, action), [])

        bloated = (
            "Choose genuinely new work, but first scan all Timeline history, scan Vault history, enumerate all peers, "
            "then audit the whole swarm before touching the typo."
        )
        self.assertIn("routine_fix_triggered_archaeology", evaluate_entry_action(self.routine, bloated))


if __name__ == "__main__":
    unittest.main()