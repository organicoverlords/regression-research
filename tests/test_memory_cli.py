import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class MemoryCliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.cli = self.root / "tools" / "memory_bank.py"

    def run_cli(self, bank: Path, *args: str, check: bool = False):
        return subprocess.run(
            [sys.executable, str(self.cli), "--bank", str(bank), *args],
            cwd=self.root, text=True, encoding="utf-8", capture_output=True, check=check,
        )

    def record_args(self, *, kind="lesson", scope="mcp", text="Investigate first.", state="PROVEN", source=None):
        source = source or text
        return [
            "record", "--kind", kind, "--scope", scope, "--text", text,
            "--source-message", source,
            "--interpretation", "Test fixture preserving the canonical recorder path.",
            "--confidence", "100", "--confidence-reason", "Deterministic test fixture.",
            "--state", state,
        ]

    def test_record_and_search_history_cli(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            created = json.loads(self.run_cli(bank, *self.record_args(), "--tag", "routing", "--evidence", "issue:7", check=True).stdout)
            self.assertEqual(created["scope"], "mcp")
            history = json.loads(self.run_cli(bank, "search", "routing", "--history", check=True).stdout)
            self.assertEqual(history[0]["text"], "Investigate first.")

    def test_correction_requires_supersedes_or_explicit_standalone(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            base = json.loads(self.run_cli(bank, *self.record_args(kind="fact", text="Old conclusion"), check=True).stdout)

            rejected = self.run_cli(bank, *self.record_args(kind="correction", text="Corrected conclusion"))
            self.assertEqual(rejected.returncode, 2, rejected.stderr)
            self.assertIn("correction must name at least one --supersedes", rejected.stdout)

            missing = self.run_cli(bank, *self.record_args(kind="correction", text="Corrected conclusion"), "--supersedes", "mem-does-not-exist")
            self.assertEqual(missing.returncode, 2, missing.stderr)
            self.assertIn("supersedes target not found", missing.stdout)

            linked = json.loads(self.run_cli(bank, *self.record_args(kind="correction", text="Corrected conclusion"), "--supersedes", base["id"], check=True).stdout)
            self.assertEqual(linked["supersedes"], [base["id"]])

            standalone = json.loads(self.run_cli(bank, *self.record_args(kind="correction", text="Standalone correction rule", state="PROVISIONAL"), "--standalone-correction", check=True).stdout)
            self.assertEqual(standalone["supersedes"], [])

    def test_record_cli_accepts_unicode_error(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            text = "error: as?dasdnasdnda MCP retry failed"
            created = json.loads(self.run_cli(bank, *self.record_args(text=text, state="PROVISIONAL"), check=True).stdout)
            self.assertEqual(created["text"], text)
            self.assertEqual(created["scope"], "mcp")
            self.assertEqual(created["state"], "PROVISIONAL")
            self.assertIn("assistant-recorded", created["tags"])
            self.assertIn("verbatim-source", created["tags"])
            self.assertEqual(len(bank.read_text(encoding="utf-8").splitlines()), 1)

    def test_record_cli_omits_legacy_behavior_metadata_and_rejects_behavior_flag(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            args = self.record_args(kind="preference", scope="assistant-orchestration/test", text="Test behavior type", source="Test behavior type")
            ordinary = json.loads(self.run_cli(bank, *args, "--evidence", "user-instruction:test", check=True).stdout)
            self.assertNotIn("behavior_rule", ordinary)
            typed = self.run_cli(bank, *args, "--behavior-rule")
            self.assertNotEqual(typed.returncode, 0)
            self.assertIn("unrecognized arguments: --behavior-rule", typed.stderr)

    def test_recent_alias_matches_recent_titles(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            self.run_cli(bank, *self.record_args(scope="memory", text="Recent compatibility note"), check=True)
            canonical = self.run_cli(bank, "recent-titles", check=True)
            alias = self.run_cli(bank, "recent", check=True)
            self.assertEqual(alias.stdout, canonical.stdout)

    def test_record_cli_preserves_verbatim_sources_and_interpretation(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            source1 = "like in this memory i would expect all the relevant messages to be added in the final memort after I add them one by one you know"
            source2 = "with spelling mistakes and all and your versoin can then explain why the memory exists and what you added etc"
            cmd = [
                "record", "--kind", "lesson", "--scope", "memory-governance",
                "--title", "Verbatim recorder provenance", "--project", "p3",
                "--expires-at", "2099-08-21T10:00:00+03:00",
                "--text", "Assistant memories keep source transcript and interpretation separate.",
                "--source-message", source1, "--source-message", source2,
                "--turn-task", "make it permanent that the original actual words are always included in every assistant recorder memory so there is no ambiguity afterwards",
                "--interpretation", "The user wants accumulated verbatim provenance, not cleaned-up paraphrases.",
                "--confidence", "99", "--confidence-reason", "The requirement was stated explicitly and refined over consecutive messages.",
                "--state", "PROVEN",
            ]
            created = json.loads(self.run_cli(bank, *cmd, check=True).stdout)
            self.assertEqual(created["source_messages"], [source1, source2])
            self.assertEqual(created["turn_task"], "make it permanent that the original actual words are always included in every assistant recorder memory so there is no ambiguity afterwards")
            self.assertEqual(created["interpretation"], "The user wants accumulated verbatim provenance, not cleaned-up paraphrases.")
            self.assertEqual(created["confidence"], 99)
            self.assertEqual(created["project"], "p3")
            self.assertEqual(created["expires_at"], "2099-08-21T10:00:00+03:00")
            self.assertIn("assistant-recorded", created["tags"])
            self.assertIn("verbatim-source", created["tags"])
            found = json.loads(self.run_cli(bank, "search", "versoin", "--history", check=True).stdout)
            self.assertEqual(found[0]["id"], created["id"])

    def test_search_history_preserves_twenty_result_cap(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            from tools.memory_bank import append_entry
            for index in range(25):
                append_entry(bank, {
                    "kind": "lesson", "scope": "history-test", "tags": [],
                    "text": f"bounded historical result {index}", "state": "PROVEN",
                    "evidence": [], "supersedes": [],
                })
            hits = json.loads(self.run_cli(bank, "search", "bounded", "--history", "--limit", "999", check=True).stdout)
            self.assertEqual(len(hits), 20)


if __name__ == "__main__":
    unittest.main()
