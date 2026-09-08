import json
import unittest
from pathlib import Path

from tools.timeline_materializer import _lesson_packet, _query_concepts, _rank_query_events

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

    def test_lesson_packet_does_not_expand_unanchored_proof_noise(self):
        query = self.case["task_text"]
        seed = {
            "id": "seed:visual-library",
            "source_type": "VAULT_MEMORY",
            "project": "tiny3d",
            "event_at": "2026-09-07T12:00:00+00:00",
            "title": "Tiny3D exact library show and attribution gap",
            "summary": "Integrated stored visual proof display transport",
            "scope": "tiny3d issue 9",
        }
        supporting_seed = {
            "id": "seed:response-gate",
            "source_type": "VAULT_MEMORY",
            "project": "vault",
            "event_at": "2026-09-06T12:00:00+00:00",
            "title": "Shared response gate",
            "summary": "Stored presentation response counter",
            "scope": "assistant orchestration presentation",
        }
        relevant = {
            "id": "git:tiny3d:proof-library",
            "source_type": "GIT_COMMIT",
            "project": "tiny3d",
            "event_at": "2026-09-05T12:00:00+00:00",
            "title": "Integrate stored visual proof library transport",
            "summary": "Integrate stored visual proof library transport",
            "body": "Persist exact proof bytes in a durable library bundle and reuse the existing display transport.",
            "sha": "a" * 40,
        }
        relevant_two = {
            "id": "git:tiny3d:proof-index",
            "source_type": "GIT_COMMIT",
            "project": "tiny3d",
            "event_at": "2026-09-04T12:00:00+00:00",
            "title": "Index stored proof pictures for library display",
            "summary": "Index stored proof pictures for library display",
            "body": "Bounded retrieval preserves exact picture identity before shared inspection and display.",
            "sha": "b" * 40,
        }
        incidental = {
            "id": "git:lowvram:geometry",
            "source_type": "GIT_COMMIT",
            "project": "lowvram",
            "event_at": "2026-09-03T12:00:00+00:00",
            "title": "Harden geometry evaluation and orientation handling",
            "summary": "Harden geometry evaluation and orientation handling",
            "body": (
                "A visual proof render exposed incorrect orientation. The repair inspects the image and "
                "stores evidence, but it is only a geometry evaluation lesson."
            ),
            "sha": "c" * 40,
        }
        worker_noise = {
            "id": "worker:visual-proof-noise",
            "source_type": "WORKER_REPORT",
            "project": "p3",
            "event_at": "2026-09-08T12:00:00+00:00",
            "title": "Visual proof library transport integration worker report",
            "summary": "Stored proof picture review and shared display were mentioned during a broad convergence run.",
            "findings": "The actual work was unrelated runtime acceptance, packaging, and worker orchestration.",
        }
        packet = _lesson_packet(
            query,
            selected=[seed, supporting_seed],
            candidates=[seed, supporting_seed, relevant, relevant_two, incidental, worker_noise],
            query_index=None,
            limit=8,
        )
        ids = {item["source_event_id"] for item in packet["items"]}
        self.assertIn("git:tiny3d:proof-library", ids)
        self.assertIn("git:tiny3d:proof-index", ids)
        self.assertNotIn("git:lowvram:geometry", ids)
        self.assertNotIn("worker:visual-proof-noise", ids)

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
