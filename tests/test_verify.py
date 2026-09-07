import sys
import unittest
from unittest.mock import patch

from tools.verify import changed_files, run_pytest, select_areas, verify_busy, verify_memory, verify_stack


class VerifyTests(unittest.TestCase):
    def test_selects_only_affected_area(self):
        self.assertEqual(select_areas({"tools/stack_atlas.py"}), ["stack", "memory"])
        self.assertEqual(select_areas({"NORTH_STAR.md"}), ["stack"])
        self.assertEqual(select_areas({"AGENTS.md"}), ["stack"])
        self.assertEqual(select_areas({"tools/conversation_search.py"}), ["conversation"])
        self.assertEqual(select_areas({"tools/memory_context.py"}), ["memory"])
        self.assertEqual(
            select_areas({"03 Fixtures and Experiments/issue125-busy-coordinator/python/busy.py"}),
            ["busy"],
        )
        self.assertEqual(select_areas({"memory/README.md"}), ["memory"])
        self.assertEqual(select_areas({"02 Evidence/mcp-security-routing-events.jsonl"}), ["memory"])
        self.assertEqual(select_areas({"tools/mcp_reroute_evidence.py"}), ["memory"])
        self.assertEqual(select_areas({"tests/test_mcp_reroute_evidence.py"}), ["memory"])
        self.assertEqual(select_areas({"README.md"}), [])

    def test_timeline_changes_select_memory_verification(self):
        for path in (
            "tools/repo_timeline.py",
            "tests/test_repo_timeline.py",
            "tools/timeline_materializer.py",
            "tests/test_timeline_materializer.py",
            "tests/test_timeline_query_filters.py",
            "tests/test_timeline_recovery_issue649.py",
            "tests/test_issue675_query_cache_generation.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_areas({path}), ["memory"])

    def test_issue693_entry_fixture_selects_stack_verification(self):
        for path in (
            "tests/test_issue693_fresh_worker_entry.py",
            "tests/fixtures/issue693_fresh_worker_entry.json",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_areas({path}), ["stack"])

    def test_issue123_current_boundary_selects_stack_verification(self):
        for path in (
            "03 Fixtures and Experiments/issue123-current-vault-history-boundary.json",
            "01 Reports/2026-09-03_issue123-current-vault-history-boundary.md",
            "02 Evidence/issue123/2026-08-27_current-user-preference-coverage.md",
            "tests/test_issue123_current_vault_history_boundary.py",
            "tests/fixtures/issue123-small-response-shape.json",
            "tests/test_issue123_response_shape.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_areas({path}), ["stack"])

    def test_issue122_false_boundary_replay_selects_stack_verification(self):
        for path in (
            "03 Fixtures and Experiments/issue122-false-boundary-provenance.json",
            "tests/test_issue122_false_boundary_replay.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_areas({path}), ["stack"])

    def test_issue122_forensic_integrity_selects_stack_verification(self):
        for path in (
            "tests/test_issue122_forensic_integrity.py",
            "02 Evidence/issue122/2026-08-25_122229_EEST_pre-repair-memory-block.txt",
            "02 Evidence/issue122/2026-08-27_canonical-claim-evidence-ledger.md",
            ".gitattributes",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_areas({path}), ["stack"])

    def test_busy_alias_owner_changes_select_busy_verification(self):
        for path in (
            "03 Fixtures and Experiments/issue125-busy-coordinator/python/busy.py",
            "03 Fixtures and Experiments/issue125-busy-coordinator/rust/src/main.rs",
            "03 Fixtures and Experiments/issue125-busy-coordinator/tests/install_compatibility.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_areas({path}), ["busy"])

    def test_issue675_lesson_guards_select_memory_verification(self):
        for path in (
            "tests/test_issue675_lesson_lineage_safety.py",
            "tests/test_issue675_lesson_validation_safety.py",
            "tests/test_issue675_static_proof_safety.py",
        ):
            with self.subTest(path=path):
                self.assertEqual(select_areas({path}), ["memory"])

    @patch("tools.verify.run")
    def test_stack_verification_executes_issue693_entry_fixture(self, run):
        verify_stack()
        unittest_command = run.call_args_list[1].args[0]
        self.assertIn("tests.test_issue693_fresh_worker_entry", unittest_command)
        self.assertIn("tests.test_issue122_forensic_integrity", unittest_command)
        self.assertIn("tests.test_issue122_false_boundary_replay", unittest_command)
        self.assertIn("tests.test_issue123_current_vault_history_boundary", unittest_command)
        self.assertIn("tests.test_issue123_response_shape", unittest_command)

    @patch("tools.verify.run")
    @patch("tools.verify.run_pytest")
    def test_memory_verification_executes_timeline_regressions(self, pytest_run, run):
        verify_memory()
        test_paths = pytest_run.call_args.args[0]
        self.assertIn("tests/test_repo_timeline.py", test_paths)
        self.assertIn("tests/test_timeline_materializer.py", test_paths)
        self.assertIn("tests/test_timeline_query_filters.py", test_paths)
        self.assertIn("tests/test_timeline_recovery_issue649.py", test_paths)
        self.assertIn("tests/test_issue675_query_cache_generation.py", test_paths)
        self.assertIn("tests/test_mcp_reroute_evidence.py", test_paths)
        self.assertIn("tests/test_issue675_lesson_lineage_safety.py", test_paths)
        self.assertIn("tests/test_issue675_lesson_validation_safety.py", test_paths)
        self.assertIn("tests/test_issue675_static_proof_safety.py", test_paths)
        compile_command = run.call_args_list[0].args[0]
        self.assertIn("tools/repo_timeline.py", compile_command)
        self.assertIn("tools/timeline_materializer.py", compile_command)
        self.assertIn("tools/mcp_reroute_evidence.py", compile_command)
        self.assertIn([sys.executable, "tools/mcp_reroute_evidence.py", "verify"], [call.args[0] for call in run.call_args_list])

    @patch("tools.verify.run")
    def test_busy_verification_executes_alias_regressions(self, run_command):
        verify_busy()
        commands = [call.args[0] for call in run_command.call_args_list]
        root = "03 Fixtures and Experiments/issue125-busy-coordinator"
        compatibility = f"{root}/tests/install_compatibility.py"
        self.assertIn(
            [sys.executable, "-m", "py_compile", f"{root}/python/busy.py", compatibility],
            commands,
        )
        self.assertIn(["cargo", "test", "--release", "--manifest-path", f"{root}/rust/Cargo.toml"], commands)
        self.assertIn([sys.executable, compatibility], commands)

    def test_verifier_changes_run_every_area(self):
        self.assertEqual(
            select_areas({"tools/verify.py"}),
            ["stack", "memory", "conversation", "busy"],
        )

    def test_all_runs_every_area(self):
        self.assertEqual(select_areas(set(), run_all=True), ["stack", "memory", "conversation", "busy"])

    @patch("tools.verify.subprocess.check_output")
    def test_changed_files_normalizes_git_paths(self, check_output):
        check_output.side_effect = [
            "README.md\n",
            "tools\\verify.py\n",
            "tests/test_verify.py\n",
        ]
        self.assertEqual(
            changed_files("origin/main"),
            {"tools/verify.py", "tests/test_verify.py", "README.md"},
        )

    @patch("tools.verify.run")
    @patch("tools.verify.tempfile.TemporaryDirectory")
    def test_pytest_uses_isolated_basetemp(self, temporary_directory, run_command):
        temporary_directory.return_value.__enter__.return_value = r"C:\Temp\rr-pytest-unique"

        run_pytest(["tests/test_memory_bank.py"])

        temporary_directory.assert_called_once_with(prefix="regression-research-pytest-")
        self.assertEqual(
            run_command.call_args.args[0],
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--basetemp",
                r"C:\Temp\rr-pytest-unique",
                "tests/test_memory_bank.py",
            ],
        )


if __name__ == "__main__":
    unittest.main()
