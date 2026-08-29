import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "memory_bank.py"


class MemoryAuthorityPipelineTests(unittest.TestCase):
    def setup_paths(self, raw: str):
        root = Path(raw)
        bank = root / "bank.jsonl"
        registry = root / "authority.json"
        registry.write_text(json.dumps({
            "schema_version": 1,
            "purpose": "test authority registry",
            "user_explicit_ids": [],
            "canonical_policy_ids": [],
        }) + "\n", encoding="utf-8")
        return bank, registry

    def run_cli(self, bank: Path, registry: Path, *args: str, check: bool = True):
        return subprocess.run(
            [sys.executable, str(CLI), "--bank", str(bank), "--authority-registry", str(registry), *args],
            cwd=ROOT, text=True, encoding="utf-8", capture_output=True, check=check,
        )

    @staticmethod
    def trusted_rule(ident: str, *, state: str = "PROVEN", supersedes=None):
        return {
            "id": ident,
            "timestamp": "2026-08-29T06:00:00+03:00",
            "kind": "preference",
            "scope": "assistant-orchestration/test",
            "tags": ["assistant-recorded", "verbatim-source"],
            "title": "Keep inherited work intact",
            "text": "Keep inherited work intact after a correction.",
            "state": state,
            "evidence": ["user-instruction:test"],
            "supersedes": list(supersedes or []),
            "behavior_rule": True,
            "source_messages": ["keep the rest of the task intact"],
            "interpretation": "Direct user behavior rule.",
            "confidence": 100,
            "confidence_reason": "Explicit user instruction.",
        }

    def test_record_behavior_rule_is_authoritative_after_fresh_reload(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            created = self.run_cli(
                bank, registry, "record",
                "--kind", "preference", "--scope", "assistant-orchestration/test",
                "--title", "Verify before completion", "--text", "Verify the actual result before completion.",
                "--source-message", "verify the actual result before saying it is done",
                "--interpretation", "Direct behavior rule.", "--confidence", "100",
                "--confidence-reason", "Explicit user instruction.", "--state", "PROVEN",
                "--evidence", "user-instruction:test", "--behavior-rule",
            )
            entry = json.loads(created.stdout)
            self.assertIn("BEHAVIOR_AUTHORITY USER_EXPLICIT", created.stderr)

            validated = json.loads(self.run_cli(bank, registry, "authority-validate").stdout)
            self.assertEqual(validated["status"], "PROVEN")
            self.assertEqual(validated["typed_uncurated"], [])

            hits = json.loads(self.run_cli(bank, registry, "behavior-search", "verify actual result").stdout)
            self.assertEqual(hits[0]["id"], entry["id"])
            self.assertEqual(hits[0]["behavioral_authority"]["role"], "USER_EXPLICIT")

            bootstrap = json.loads(self.run_cli(bank, registry, "bootstrap").stdout)
            self.assertEqual([item["id"] for item in bootstrap["behavior_profile"]], [entry["id"]])

    def test_raw_typed_record_cannot_mint_authority(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            forged = self.trusted_rule("mem-forged")
            bank.write_text(json.dumps(forged) + "\n", encoding="utf-8")
            hits = json.loads(self.run_cli(bank, registry, "behavior-search", "inherited work").stdout)
            self.assertEqual(hits, [])
            rejected = self.run_cli(bank, registry, "authority-validate", check=False)
            self.assertEqual(rejected.returncode, 2)
            payload = json.loads(rejected.stdout)
            self.assertEqual(payload["typed_uncurated"], ["mem-forged"])

    def test_promote_behavior_repairs_a_stranded_trusted_record(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            entry = self.trusted_rule("mem-stranded")
            bank.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            promoted = json.loads(self.run_cli(bank, registry, "promote-behavior", "mem-stranded").stdout)
            self.assertEqual(promoted["behavioral_authority"]["role"], "USER_EXPLICIT")
            fresh = json.loads(self.run_cli(bank, registry, "behavior-search", "inherited work").stdout)
            self.assertEqual(fresh[0]["id"], "mem-stranded")

    def test_promote_policy_requires_canonical_provenance(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            policy = {
                "id": "mem-policy", "timestamp": "2026-08-29T06:00:00+03:00", "kind": "decision",
                "scope": "policy", "tags": [], "title": "Canonical test policy", "text": "Use canonical test policy.",
                "state": "PROVEN", "evidence": ["shared-policy:test"], "supersedes": [],
            }
            bank.write_text(json.dumps(policy) + "\n", encoding="utf-8")
            promoted = json.loads(self.run_cli(bank, registry, "promote-policy", "mem-policy").stdout)
            self.assertEqual(promoted["behavioral_authority"]["role"], "CANONICAL_POLICY")

    def test_superseded_curated_rule_is_not_current(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            old = self.trusted_rule("mem-old")
            new = self.trusted_rule("mem-new", supersedes=["mem-old"])
            bank.write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n", encoding="utf-8")
            self.run_cli(bank, registry, "promote-behavior", "mem-old")
            self.run_cli(bank, registry, "promote-behavior", "mem-new")
            hits = json.loads(self.run_cli(bank, registry, "behavior-search", "inherited work").stdout)
            ids = [item["id"] for item in hits]
            self.assertIn("mem-new", ids)
            self.assertNotIn("mem-old", ids)

    def test_rejected_rule_cannot_be_newly_promoted(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            entry = self.trusted_rule("mem-rejected", state="REJECTED")
            bank.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            proc = self.run_cli(bank, registry, "promote-behavior", "mem-rejected", check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("rejected records cannot be promoted", proc.stdout)

    def test_registry_orphan_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            registry.write_text(json.dumps({
                "schema_version": 1, "purpose": "test", "user_explicit_ids": ["missing"], "canonical_policy_ids": []
            }) + "\n", encoding="utf-8")
            proc = self.run_cli(bank, registry, "authority-validate", check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("user authority id missing from bank: missing", proc.stdout)


if __name__ == "__main__":
    unittest.main()
