import json
import tempfile
import unittest
from pathlib import Path

from tools.fresh_chat_regression_matrix import DEFAULT_SPEC, analyze_snapshot, check_case, run_matrix

ROOT = Path(__file__).resolve().parents[1]


def _message(role, text, t, recipient="all", slug="gpt-5-6-thinking", effort="extended"):
    return {
        "author": {"role": role},
        "create_time": t,
        "recipient": recipient,
        "content": {"content_type": "text", "parts": [text]},
        "metadata": {"resolved_model_slug": slug, "thinking_effort": effort},
    }


class FreshChatRegressionMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(DEFAULT_SPEC.read_text(encoding="utf-8-sig"))

    def test_matrix_has_good_and_exact_mode_later_controls(self):
        cases = self.spec["cases"]
        self.assertGreaterEqual(len(cases), 7)
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        self.assertGreaterEqual(sum(case["phase"] == "recovered_good" for case in cases), 3)
        later = [case for case in cases if case["phase"] == "later_policy_stack"]
        self.assertGreaterEqual(len(later), 3)
        self.assertTrue(all(case["expected_default_model"] == "gpt-5-6-thinking" for case in later))
        self.assertTrue(all(case["required_thinking_effort"] == "extended" for case in later))
        behaviors = {case["behavior"] for case in later}
        self.assertIn("sustained_execution", behaviors)
        self.assertIn("route_selection_regression", behaviors)
        self.assertIn("unsupported_mutation_claim", behaviors)

    def test_forensic_invariants_prevent_report_as_authority_and_tool_count_as_quality(self):
        joined = " ".join(self.spec["forensic_invariants"]).lower()
        self.assertIn("primary instruction bytes", joined)
        self.assertIn("incident-report", joined)
        self.assertIn("tool-call volume", joined)
        self.assertIn("mutation requires", joined)

    def test_analyze_snapshot_uses_first_user_turn_and_counts_tool_recipients(self):
        payload = {
            "conversation_id": "c1", "title": "synthetic", "default_model_slug": "gpt-5-6-thinking",
            "mapping": {
                "u1": {"message": _message("user", "work on test", 100.0)},
                "a1": {"message": _message("assistant", "starting", 101.0)},
                "t1": {"message": _message("assistant", "{}", 102.0, recipient="MCP0.start_process")},
                "a2": {"message": _message("assistant", "done", 110.0)},
                "u2": {"message": _message("user", "go", 120.0)},
            },
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "conv.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            got = analyze_snapshot(path, payload)
        self.assertEqual(got["prompt"], "work on test")
        self.assertEqual(got["tool_calls"], 1)
        self.assertEqual(got["time_to_first_tool_s"], 2.0)
        self.assertEqual(got["turn_duration_s"], 10.0)
        self.assertEqual(got["next_user"], "go")
        self.assertEqual(got["model_family"], "gpt-5-6")

    def test_unsupported_mutation_case_requires_zero_tools_and_claim_text(self):
        case = next(c for c in self.spec["cases"] if c["behavior"] == "unsupported_mutation_claim")
        measured = {
            "prompt": case["expected_prompt"], "default_model": case["expected_default_model"],
            "model_family": "gpt-5-6", "model_slugs": ["gpt-5-6-thinking"],
            "thinking_efforts": ["extended"], "tool_calls": 0, "time_to_first_tool_s": None,
            "turn_duration_s": 60.0, "next_user": "please reverse that", "final_text": "Added to the Vault memory corpus",
        }
        self.assertEqual(check_case(case, measured), [])
        measured["tool_calls"] = 1
        self.assertTrue(any("tool_calls" in failure for failure in check_case(case, measured)))

    def test_run_matrix_selects_latest_duplicate_snapshot(self):
        case = {
            "id": "synthetic", "phase": "test", "day": "2026-08-25", "conversation_id": "cid",
            "expected_prompt": "go", "expected_default_model": "gpt-5-6-thinking", "required_model_family": "gpt-5-6",
            "required_model_slugs": ["gpt-5-6-thinking"], "required_thinking_effort": "extended",
            "behavior": "sustained_execution", "min_tool_calls": 1, "max_time_to_first_tool_s": 5.0, "purpose": "test"
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); day = root / "2026-08-25"; day.mkdir()
            base = {"conversation_id": "cid", "title": "x", "default_model_slug": "gpt-5-6-thinking", "update_time": 1,
                    "mapping": {"u": {"message": _message("user", "go", 1.0)}, "a": {"message": _message("assistant", "done", 2.0)}}}
            (day / "old.json").write_text(json.dumps(base), encoding="utf-8")
            newer = json.loads(json.dumps(base)); newer["update_time"] = 2; newer["mapping"]["t"] = {"message": _message("assistant", "{}", 1.5, recipient="MCP0.start_process")}
            (day / "new.json").write_text(json.dumps(newer), encoding="utf-8")
            spec_path = root / "spec.json"; spec_path.write_text(json.dumps({"issue": 122, "cases": [case]}), encoding="utf-8")
            result = run_matrix(root, spec_path)
        self.assertEqual(result["summary"], {"cases": 1, "passed": 1, "failed": 0})
        self.assertEqual(result["cases"][0]["snapshot"], "new.json")


if __name__ == "__main__":
    unittest.main()
