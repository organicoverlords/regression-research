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

    def test_literal_slopwall_record_requires_diagnosis_and_prevention_lesson(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            source = "slopwall tämä vastaus ei tehnyt pyydettyä työtä"
            rejected = self.run_cli(
                bank,
                *self.record_args(kind="correction", text="Be concise and answer better.", source=source),
                "--tag", "slopwall", "--standalone-correction",
            )
            self.assertEqual(rejected.returncode, 2, rejected.stderr)
            self.assertIn("Rejected behavior:", rejected.stdout)
            self.assertIn("Mechanism uncertainty:", rejected.stdout)
            self.assertIn("Prevention lesson:", rejected.stdout)
            self.assertIn("answer better", rejected.stdout)

    def test_literal_slopwall_record_accepts_complete_learning_loop_and_adds_tag(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            source = "SLOPWALL: lopeta reitin selittely ja tee työ"
            text = (
                "Rejected behavior: assistant stayed on a blocked transport and narrated route discovery instead of doing the requested inspection. "
                "Best-supported mechanism: route selection did not pivot after direct evidence showed the first transport was blocked. "
                "Prevention lesson: when a low-level route is blocked and a supported read-only owner path exists, switch to that path and return the operational result first."
            )
            created = json.loads(self.run_cli(
                bank,
                *self.record_args(kind="correction", text=text, source=source),
                "--standalone-correction",
                check=True,
            ).stdout)
            self.assertIn("slopwall", created["tags"])
            self.assertEqual(created["text"], text)
            self.assertEqual(created["source_messages"], [source])

    def test_slopwall_tag_requires_literal_source_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            text = (
                "Rejected behavior: assistant selected the wrong route and displaced the requested result. "
                "Mechanism: route selection stopped at the first blocked transport instead of using the supported owner path. "
                "Prevention lesson: switch to the supported owner path after a bounded low-level route failure."
            )
            result = self.run_cli(
                bank,
                *self.record_args(kind="correction", text=text, source="this answer used the wrong route"),
                "--tag", "slopwall", "--standalone-correction",
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("verbatim --source-message containing literal slopwall", result.stdout)

    def test_tagged_slopwall_must_be_recorded_as_correction(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            text = (
                "Rejected behavior: assistant displaced the requested result with process narration. "
                "Mechanism uncertainty: the observable selection failure is proven but a deeper internal cause is not. "
                "Prevention lesson: keep the inherited task live and return the missing substantive result before process detail."
            )
            result = self.run_cli(bank, *self.record_args(kind="lesson", text=text, source="slopwall"), "--tag", "slopwall")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("literal slopwall must be recorded with --kind correction", result.stdout)

    def test_meta_slopwall_reference_without_correction_tag_remains_ordinary_memory(self):
        with tempfile.TemporaryDirectory() as d:
            bank = Path(d) / "bank.jsonl"
            created = json.loads(self.run_cli(
                bank,
                *self.record_args(kind="lesson", text="Slopwall history distinguishes corrective incidents from meta references.", source="what does slopwall mean?"),
                check=True,
            ).stdout)
            self.assertEqual(created["kind"], "lesson")
            self.assertNotIn("slopwall", created["tags"])

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
