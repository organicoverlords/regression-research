import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import tools.memory_classification as memory_classification

from tools.memory_classification import classify_entry, infer_single_project


class MemoryClassificationTests(unittest.TestCase):
    @staticmethod
    def entry(**overrides):
        base = {
            "id": "x",
            "timestamp": "2026-08-29T01:00:00+03:00",
            "kind": "lesson",
            "scope": "global",
            "tags": [],
            "text": "Durable lesson.",
            "state": "PROVEN",
            "evidence": ["report:x"],
            "supersedes": [],
        }
        base.update(overrides)
        return base

    def test_project_is_inferred_only_from_descriptors(self):
        p3 = self.entry(scope="p3/build", title="P3 build rule")
        result = classify_entry(p3)
        self.assertEqual(result["projects"], ["p3"])
        self.assertEqual(result["primary_domain"], "project:p3")
        self.assertEqual(infer_single_project(p3), "p3")

        body_only = self.entry(text="P3 is mentioned only as an example inside the body.")
        body_result = classify_entry(body_only)
        self.assertEqual(body_result["projects"], [])
        self.assertEqual(infer_single_project(body_only), None)

    def test_nexus_project_is_inferred_from_nexus_and_devboard_descriptors(self):
        for scope in ("nexus/canvas", "devboard/canvas"):
            with self.subTest(scope=scope):
                entry = self.entry(scope=scope, title="Nexus canvas navigation")
                result = classify_entry(entry)
                self.assertEqual(result["projects"], ["nexus"])
                self.assertEqual(result["primary_domain"], "project:nexus")
                self.assertEqual(infer_single_project(entry), "nexus")

    def test_explicit_project_wins_and_role_is_descriptor_scoped(self):
        entry = self.entry(project="tiny3d", scope="worker/runtime", title="Worker runtime rule")
        result = classify_entry(entry)
        self.assertEqual(result["projects"], ["tiny3d"])
        self.assertEqual(result["roles"], ["worker"])
        self.assertEqual(result["primary_domain"], "project:tiny3d")

    def test_explicit_project_can_keep_structured_cross_project_scope(self):
        entry = self.entry(
            project="p3",
            scope="p3-tiny3d-visual-camera-retakes",
            tags=["visual-proof", "tiny3d"],
            title="Saved camera proof settings",
        )
        result = classify_entry(entry)
        self.assertEqual(result["projects"], ["p3", "tiny3d"])
        self.assertEqual(result["primary_domain"], "cross-project")
        self.assertIn("multiple_project_descriptors", result["review_reasons"])
        self.assertIsNone(infer_single_project(entry))

    def test_explicit_project_ignores_incidental_other_project_title(self):
        entry = self.entry(
            project="tiny3d",
            scope="tiny3d/build",
            title="P3 mentioned only as an example",
        )
        result = classify_entry(entry)
        self.assertEqual(result["projects"], ["tiny3d"])
        self.assertEqual(result["primary_domain"], "project:tiny3d")

    def test_incident_and_checkpoint_categories_are_bounded(self):
        incident = classify_entry(self.entry(scope="assistant-orchestration/slopwall-test", title="SLOPWALL incident"))
        self.assertEqual(incident["semantic_category"], "INCIDENT")
        self.assertEqual(incident["primary_domain"], "assistant-orchestration")

        checkpoint = classify_entry(self.entry(kind="status", scope="tool-availability/checkpoint", title="Tool checkpoint"))
        self.assertEqual(checkpoint["semantic_category"], "CHECKPOINT")
        self.assertEqual(checkpoint["durability"], "EPHEMERAL")

    def test_provisional_is_review_not_silently_promoted(self):
        result = classify_entry(self.entry(state="PROVISIONAL", scope="mcp", text="Possible routing explanation."))
        self.assertEqual(result["durability"], "REVIEW")
        self.assertIn("claim_state_provisional", result["review_reasons"])
        self.assertEqual(result["confidence"], "REVIEW")

    def test_sensitivity_distinguishes_secret_values_from_generic_discussion(self):
        secret = classify_entry(self.entry(text="token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"))
        self.assertEqual(secret["sensitivity"], "EXCLUDE")
        generic = classify_entry(self.entry(text="A connector credential failure is evidence about routing only."))
        self.assertEqual(generic["sensitivity"], "REVIEW")
        self.assertIn("sensitivity_pattern_requires_review", generic["review_reasons"])

    def test_grouped_sensitivity_matchers_preserve_legacy_pattern_outcomes(self):
        samples = [
            "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
            "gho_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
            "sk-ABCDEFGHIJKLMN123456",
            "password=CorrectHorseBatteryStaple123",
            "password is CorrectHorse123!",
            "access token is ABCDEFGHIJKLMNOPQRSTUV",
            "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
            "-----BEGIN RSA PRIVATE KEY-----",
            "123-45-6789",
            "1234 5678 9012 3456",
            "credentials are stored elsewhere",
            "private key rotation policy",
            "owner@example.com",
            "Bearer authentication token",
            "password is confidential",
            "ordinary connector routing lesson",
        ]

        def legacy(text, patterns):
            return any(pattern.search(text) for pattern in patterns)

        for text in samples:
            with self.subTest(text=text):
                self.assertEqual(
                    any(matcher.search(text) for matcher in memory_classification._STRONG_SENSITIVE_MATCHERS),
                    legacy(text, memory_classification._STRONG_SENSITIVE_PATTERNS),
                )
                self.assertEqual(
                    any(matcher.search(text) for matcher in memory_classification._REVIEW_SENSITIVE_MATCHERS),
                    legacy(text, memory_classification._REVIEW_SENSITIVE_PATTERNS),
                )

    def test_sensitivity_rejects_natural_language_password_and_bearer_token(self):
        password = classify_entry(self.entry(text="my password is CorrectHorseBatteryStaple123!"))
        bearer = classify_entry(self.entry(text="Bearer abcdefghijklmnopqrstuvwxyz0123456789"))
        self.assertEqual(password["sensitivity"], "EXCLUDE")
        self.assertEqual(bearer["sensitivity"], "EXCLUDE")
        self.assertEqual(classify_entry(self.entry(text="password is confidential"))["sensitivity"], "CLEAR")
        self.assertEqual(classify_entry(self.entry(text="Bearer authentication token"))["sensitivity"], "CLEAR")

    def test_sensitivity_scans_verbatim_source_messages(self):
        entry = self.entry(text="safe summary")
        entry.update({
            "tags": ["assistant-recorded", "verbatim-source"],
            "source_messages": ["password=SUPERSECRET123"],
            "interpretation": "safe",
            "confidence": 100,
            "confidence_reason": "test",
        })
        self.assertEqual(classify_entry(entry)["sensitivity"], "EXCLUDE")

    def test_cli_classifies_one_bank_id_incrementally(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            entry = self.entry(id="mem-one", scope="p3/build", title="P3 build rule")
            bank.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            cli = Path(__file__).resolve().parents[1] / "tools" / "memory_classification.py"
            proc = subprocess.run(
                [sys.executable, str(cli), "--bank", str(bank), "--id", "mem-one"],
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["id"], "mem-one")
            self.assertEqual(payload["classification"]["primary_domain"], "project:p3")

    def test_expired_entry_is_historical(self):
        result = classify_entry(self.entry(expires_at="2026-08-01T00:00:00+03:00"))
        self.assertTrue(result["expired"])
        self.assertEqual(result["durability"], "HISTORICAL")


if __name__ == "__main__":
    unittest.main()
