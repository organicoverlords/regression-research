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

    def test_record_behavior_rule_cannot_mint_runtime_authority(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            proc = self.run_cli(
                bank, registry, "record", "--kind", "preference",
                "--scope", "assistant-orchestration/test", "--title", "Historical rule",
                "--text", "Historical rule.", "--source-message", "historical rule",
                "--interpretation", "Historical only.", "--confidence", "100",
                "--confidence-reason", "Explicit user instruction.", "--state", "PROVEN",
                "--evidence", "user-instruction:test", "--behavior-rule", check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("--behavior-rule is retired", proc.stdout)

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

    def test_promote_behavior_is_retired(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            entry = self.trusted_rule("mem-stranded")
            bank.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            proc = self.run_cli(bank, registry, "promote-behavior", "mem-stranded", check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("Vault runtime authority promotion is retired", proc.stdout)


    def test_promote_policy_is_retired(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            entry = self.trusted_rule("mem-policy")
            bank.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            proc = self.run_cli(bank, registry, "promote-policy", "mem-policy", check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("Vault runtime authority promotion is retired", proc.stdout)

    def test_superseded_historical_rule_stays_non_authoritative(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            old = self.trusted_rule("mem-old")
            new = self.trusted_rule("mem-new", supersedes=["mem-old"])
            bank.write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n", encoding="utf-8")
            hits = json.loads(self.run_cli(bank, registry, "behavior-search", "inherited work").stdout)
            self.assertEqual(hits, [])


    def test_rejected_rule_cannot_bypass_retirement(self):
        with tempfile.TemporaryDirectory() as raw:
            bank, registry = self.setup_paths(raw)
            entry = self.trusted_rule("mem-rejected", state="REJECTED")
            bank.write_text(json.dumps(entry) + "\n", encoding="utf-8")
            proc = self.run_cli(bank, registry, "promote-behavior", "mem-rejected", check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("Vault runtime authority promotion is retired", proc.stdout)


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
