import json
import tempfile
import unittest
from pathlib import Path

from tools.manual_authoritative_sanity_eval import (
    evaluate_github_pr_payload,
    load_mcp_receipts,
    score_trace,
    compose_components,
)


def receipt(command, *, process_id, started_at, outcome="success", exit_code=0, caller="caller-a", complete=True, cwd="C:/work"):
    return {
        "version": 1,
        "process_id": process_id,
        "caller_id": caller,
        "audit_schema": "process-output-evidence.v1",
        "evidence_completeness": "complete" if complete else "partial",
        "execution_outcome": outcome,
        "exit_code": exit_code,
        "command": command,
        "cwd": cwd,
        "started_at": started_at,
        "finished_at": started_at,
    }


class AuthoritativeSanityEvalTests(unittest.TestCase):
    def test_receipts_filter_to_authoritative_caller_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            items = [
                receipt("one", process_id="1", started_at="2026-09-10T00:00:00+00:00"),
                receipt("two", process_id="2", started_at="2026-09-10T00:01:00+00:00", caller="other"),
                receipt("three", process_id="3", started_at="2026-09-10T00:02:00+00:00", complete=False),
            ]
            for i, item in enumerate(items):
                (root / f"{i}.json").write_text(json.dumps(item), encoding="utf-8")
            rows, coverage = load_mcp_receipts(root, caller_id="caller-a")
            self.assertEqual([row["process_id"] for row in rows], ["1"])
            self.assertEqual(coverage["excluded_incomplete_receipts"], 1)
            self.assertEqual(coverage["excluded_by_scope"], 1)

    def test_trace_hard_and_soft_are_separate(self):
        rows = [receipt("swarm_route.py route", process_id="1", started_at="2026-09-10T00:00:00+00:00")]
        for row in rows:
            row["_started_dt"] = __import__("datetime").datetime.fromisoformat(row["started_at"])
        spec = {"spec_id": "x", "checks": [
            {"type": "command_present", "pattern": "swarm_route", "categories": ["routing"]},
            {"type": "command_present", "pattern": "pytest", "categories": ["validation"]},
        ]}
        result = score_trace(spec, rows, coverage_mode="exhaustive")
        self.assertFalse(result["hard_satisfied"])
        self.assertEqual(result["soft_satisfaction_rate"], 50.0)

    def test_successful_command_requires_success_receipt(self):
        row = receipt("pytest -q", process_id="1", started_at="2026-09-10T00:00:00+00:00", outcome="nonzero_exit", exit_code=1)
        row["_started_dt"] = __import__("datetime").datetime.fromisoformat(row["started_at"])
        spec = {"checks": [{"type": "successful_command_present", "pattern": "pytest"}]}
        self.assertFalse(score_trace(spec, [row], coverage_mode="exhaustive")["hard_satisfied"])

    def test_ordered_commands_and_precedes_use_receipt_order(self):
        rows = []
        for i, command in enumerate(["busy-python.cmd claim x", "git add x", "git commit -m x"]):
            row = receipt(command, process_id=str(i), started_at=f"2026-09-10T00:0{i}:00+00:00")
            row["_started_dt"] = __import__("datetime").datetime.fromisoformat(row["started_at"])
            rows.append(row)
        spec = {"checks": [
            {"type": "ordered_commands", "patterns": ["busy-.*claim", "git add", "git commit"]},
            {"type": "command_precedes", "before_pattern": "busy-.*claim", "after_pattern": "git commit"},
        ]}
        self.assertTrue(score_trace(spec, rows)["hard_satisfied"])

    def test_command_absent_is_a_real_negative_constraint(self):
        row = receipt("git status", process_id="1", started_at="2026-09-10T00:00:00+00:00")
        row["_started_dt"] = __import__("datetime").datetime.fromisoformat(row["started_at"])
        spec = {"checks": [{"type": "command_absent", "pattern": r"git\s+reset\s+--hard"}]}
        self.assertTrue(score_trace(spec, [row], coverage_mode="exhaustive")["hard_satisfied"])

    def test_github_merge_is_convergence_even_with_nonrequired_failed_check(self):
        payload = {
            "number": 10, "state": "MERGED", "baseRefName": "main", "mergeCommit": {"oid": "abc"},
            "statusCheckRollup": [{"name": "verify", "workflowName": "changelog-landing", "status": "COMPLETED", "conclusion": "FAILURE"}],
        }
        result = evaluate_github_pr_payload(payload)
        self.assertTrue(result["convergence_pass"])
        self.assertIsNone(result["required_checks_pass"])
        self.assertEqual(result["observed_checks"]["bad_completed"], 1)

    def test_required_check_must_be_green_when_configured(self):
        payload = {
            "number": 10, "state": "MERGED", "mergeCommit": {"oid": "abc"},
            "statusCheckRollup": [{"name": "acceptance", "workflowName": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}],
        }
        self.assertTrue(evaluate_github_pr_payload(payload, required_checks=["ci/acceptance"])["required_checks_pass"])
        self.assertFalse(evaluate_github_pr_payload(payload, required_checks=["ci/missing"])["required_checks_pass"])

    def test_pending_required_check_is_not_failure_but_not_pass(self):
        payload = {
            "number": 10, "state": "MERGED", "mergeCommit": {"oid": "abc"},
            "statusCheckRollup": [{"name": "acceptance", "workflowName": "ci", "status": "IN_PROGRESS", "conclusion": ""}],
        }
        result = evaluate_github_pr_payload(payload, required_checks=["ci/acceptance"])
        self.assertIsNone(result["required_checks_pass"])
        self.assertIsNone(result["required_checks"][0]["passed"])
        self.assertEqual(result["required_checks"][0]["status"], "PENDING")


    def test_partial_coverage_missing_positive_is_unknown_not_failure(self):
        spec = {"checks": [{"type": "command_present", "pattern": "pytest"}]}
        result = score_trace(spec, [], coverage_mode="partial")
        self.assertIsNone(result["hard_satisfied"])
        self.assertIsNone(result["soft_satisfaction_rate"])
        self.assertEqual(result["unknown_check_count"], 1)
        self.assertEqual(result["checks"][0]["status"], "UNKNOWN")

    def test_partial_coverage_cannot_prove_command_absent(self):
        spec = {"checks": [{"type": "command_absent", "pattern": r"git\s+reset\s+--hard"}]}
        result = score_trace(spec, [], coverage_mode="partial")
        self.assertIsNone(result["hard_satisfied"])
        self.assertEqual(result["checks"][0]["status"], "UNKNOWN")

    def test_partial_coverage_can_prove_negative_constraint_violation(self):
        row = receipt("git reset --hard HEAD~1", process_id="1", started_at="2026-09-10T00:00:00+00:00")
        row["_started_dt"] = __import__("datetime").datetime.fromisoformat(row["started_at"])
        spec = {"checks": [{"type": "command_absent", "pattern": r"git\s+reset\s+--hard"}]}
        result = score_trace(spec, [row], coverage_mode="partial")
        self.assertFalse(result["hard_satisfied"])
        self.assertEqual(result["checks"][0]["status"], "FAIL")

    def test_exhaustive_claim_degrades_when_authoritative_receipt_has_gap(self):
        spec = {"checks": [{"type": "command_absent", "pattern": "forbidden"}]}
        coverage = {"excluded_incomplete_receipts": 1, "unreadable_candidate_receipts": 0}
        result = score_trace(spec, [], coverage, coverage_mode="exhaustive")
        self.assertEqual(result["coverage_mode_effective"], "partial")
        self.assertTrue(result["coverage"]["exhaustive_claim_degraded"])
        self.assertIsNone(result["hard_satisfied"])

    def test_open_github_pr_is_pending_not_failure(self):
        payload = {"number": 11, "state": "OPEN", "mergeCommit": None, "statusCheckRollup": []}
        result = evaluate_github_pr_payload(payload)
        self.assertEqual(result["convergence_status"], "PENDING")
        self.assertIsNone(result["convergence_pass"])

    def test_composed_result_has_no_aggregate_score_and_no_report_input(self):
        result = compose_components({"hard_satisfied": True}, [{"convergence_pass": True}])
        self.assertEqual(result["calibration_status"], "NOT_CALIBRATED")
        self.assertIsNone(result["aggregate_score"])
        self.assertFalse(result["worker_report_input_used"])


if __name__ == "__main__":
    unittest.main()
