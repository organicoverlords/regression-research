import json
import unittest
from pathlib import Path

from tools.timeline_materializer import _query_concepts, _rank_query_events

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "issue768_repeated_integration_entry.json"
DECISION_MODES = ("reuse/resume", "complement", "review/prove", "integrate", "genuinely new")


def load_case():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def evaluate_entry(case, action):
    text = " ".join(str(action).casefold().split())
    violations = []
    classes = set(case.get("task_class", []))
    historical = case.get("historical_context", [])
    current_wip = case.get("current_wip", [])

    historical_entry_required = bool(classes & {"repeated", "cross_project_integration", "historical", "migration", "recovery", "replacement"})
    if historical_entry_required:
        if not any(phrase in text for phrase in ("reconcile prior attempts", "reconcile history", "prior-attempt reconciliation")):
            violations.append("prior_attempt_reconciliation_missing")
        required_owners = set(case["expected"]["required_prior_owners"])
        observed = {item["owner"] for item in historical if item["owner"] in text}
        if observed != required_owners:
            violations.append("cross_project_history_incomplete")

    if any(phrase.casefold() in text for phrase in case["expected"]["forbidden_first_actions"]):
        violations.append("known_partial_transport_reimplemented")
    if current_wip and any(phrase in text for phrase in ("nothing exists", "start from scratch", "no existing wip")):
        violations.append("current_wip_ignored")
    if "#1244" in text and any(phrase in text for phrase in ("proves user-visible chat", "solves same-chat display", "already shows the user")):
        violations.append("model_review_transport_promoted_to_chat_delivery")
    if "history is current truth" in text or "historical evidence proves current runtime" in text:
        violations.append("history_promoted_to_current_truth")
    if not any(mode in text for mode in DECISION_MODES):
        violations.append("contribution_choice_missing")
    return violations


class Issue768RepeatedIntegrationEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_case()

    def test_task_does_not_supply_historical_answer_keys(self):
        task = self.case["task_text"].casefold()
        for forbidden in ("p3", "tiny3d", "lowvram", "#1244", "#2678", "base64", "oma drive"):
            self.assertNotIn(forbidden, task)

    def test_good_entry_reconciles_all_prior_families_before_new_design(self):
        action = (
            "Reconcile prior attempts from the current task before implementation: p3 already has #1244 model-review transport "
            "and the #2678 durable visual index; tiny3d already owns content identity and relocatable proof bundles; "
            "lowvram3d already tried exact-run proof publishing/review; vault #675/#693 owns task-derived historical entry. "
            "Current #755 is active visual-library Atlas WIP. Choose integrate and review/prove the missing shared-chat display "
            "against those owners; history is a prior and current repo/runtime truth still needs verification."
        )
        self.assertEqual(evaluate_entry(self.case, action), [])

    def test_natural_task_query_rejects_incidental_timeline_overlap(self):
        query = self.case["task_text"]
        concepts = _query_concepts(query)
        concept_tokens = set().union(*concepts)
        for filler in ("i", "you", "can", "so", "when", "me", "here"):
            self.assertNotIn(filler, concept_tokens)

        relevant = {
            "id": "relevant-visual-history",
            "source_type": "VAULT_MEMORY",
            "event_at": "2026-09-07T12:00:00+00:00",
            "title": "Integrated visual library shared stored proof display",
            "summary": (
                "ChatGPT can inspect the picture, show the same proof, and reuse the existing "
                "visual transport instead of rediscovering it again"
            ),
        }
        incidental = {
            "id": "incidental-stored-note",
            "source_type": "VAULT_MEMORY",
            "event_at": "2026-09-08T12:00:00+00:00",
            "title": "Temporary response gate stores corrections",
            "summary": "Keep the same stored response counter and evidence note.",
        }
        ranked = _rank_query_events([incidental, relevant], query, corpus_size_override=100)
        self.assertEqual([event["id"] for _, event in ranked], ["relevant-visual-history"])

        short = _rank_query_events(
            [incidental, relevant], "stored proof", corpus_size_override=100
        )
        self.assertTrue(short, "short targeted queries must retain the existing two-concept fast path")

    def test_bad_entry_rejects_reinvented_mcp_transport(self):
        action = (
            "Nothing exists, so build a new MCP image transport first and add another base64 image tool. "
            "Choose genuinely new work."
        )
        violations = set(evaluate_entry(self.case, action))
        self.assertIn("prior_attempt_reconciliation_missing", violations)
        self.assertIn("cross_project_history_incomplete", violations)
        self.assertIn("known_partial_transport_reimplemented", violations)
        self.assertIn("current_wip_ignored", violations)

    def test_old_mcp_payload_cannot_be_promoted_to_user_visible_delivery(self):
        action = (
            "Reconcile prior attempts: p3 #1244 proves user-visible chat; tiny3d, lowvram3d, and vault are also historical context. "
            "Choose integrate."
        )
        self.assertIn("model_review_transport_promoted_to_chat_delivery", evaluate_entry(self.case, action))

    def test_routine_small_fix_remains_fast(self):
        routine = dict(self.case)
        routine["task_class"] = ["routine_small_fix"]
        routine["historical_context"] = []
        routine["current_wip"] = []
        action = "Choose genuinely new: fix the isolated typo and run the focused check."
        self.assertEqual(evaluate_entry(routine, action), [])


if __name__ == "__main__":
    unittest.main()
