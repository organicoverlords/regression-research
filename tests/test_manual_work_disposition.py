from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.manual_work_disposition import BINDING_SCHEMA, binding_summary, capture_binding, capture_trace, load_binding, load_trace
from tools.worker_report_history import _archive_manual_nonterminal_snapshot, audit_manual_current_reports


class ManualWorkDispositionTests(unittest.TestCase):
    def _write_receipt(self, root: Path, *, name: str, pid: int, run_id: str, caller: str = "caller_exact") -> Path:
        receipt = {
            "version": 1,
            "process_id": name,
            "pid": pid,
            "caller_id": caller,
            "request_id": "request_exact",
            "command": "python tools\\worker_report_history.py create-manual --repo regression-research",
            "cwd": r"C:\repo",
            "stdout": json.dumps({"ok": True, "run_id": run_id}) + "\n",
            "stderr": "",
            "exit_code": 0,
            "started_at": "2026-09-09T05:42:56.987Z",
            "finished_at": "2026-09-09T05:42:57.415Z",
        }
        path = root / f"{name}.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        return path

    def test_capture_binding_requires_pid_and_stdout_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipts = root / "receipts"
            manual = root / "worker-reports" / "manual"
            receipts.mkdir(parents=True)
            self._write_receipt(receipts, name="wrong-run", pid=3210, run_id="manual-other")
            source = self._write_receipt(receipts, name="exact-process", pid=3210, run_id="manual-target")

            result = capture_binding(
                run_id="manual-target",
                creator_child_pid=3210,
                receipt_dir=receipts,
                manual_root=manual,
                timeout_seconds=0,
            )
            self.assertTrue(result["ok"])
            binding = load_binding(manual, "manual-target")
            self.assertIsNotNone(binding)
            assert binding is not None
            self.assertEqual(binding["schema"], BINDING_SCHEMA)
            self.assertEqual(binding["caller_id"], "caller_exact")
            self.assertEqual(binding["create_process_id"], "exact-process")
            self.assertEqual(binding["mcp_process_pid"], 3210)
            self.assertEqual(binding["receipt_file"], source.name)
            self.assertEqual(binding["binding_basis"], "mcp_process_receipt_create_manual_stdout_run_id")
            self.assertEqual(binding_summary(binding)["status"], "BOUND")

    def test_capture_binding_fails_closed_when_run_id_does_not_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipts = root / "receipts"
            manual = root / "manual"
            receipts.mkdir(parents=True)
            self._write_receipt(receipts, name="wrong", pid=99, run_id="manual-other")
            result = capture_binding(
                run_id="manual-target",
                creator_child_pid=99,
                receipt_dir=receipts,
                manual_root=manual,
                timeout_seconds=0,
            )
            self.assertFalse(result["ok"])
            self.assertIsNone(load_binding(manual, "manual-target"))

    def test_capture_trace_segments_same_caller_by_manual_control_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipts = root / "receipts"
            manual = root / "manual"
            receipts.mkdir(parents=True)
            run_id = "manual-trace"
            self._write_receipt(receipts, name="create-trace", pid=1, run_id=run_id, caller="caller_trace")
            binding = capture_binding(
                run_id=run_id, creator_child_pid=11, receipt_dir=receipts, manual_root=manual, timeout_seconds=0
            )
            self.assertTrue(binding["ok"])

            def write(name: str, command: str, stdout: str = "", stderr: str = "", caller: str = "caller_trace", started: str = "2026-09-09T05:43:00Z") -> None:
                payload = {
                    "version": 1, "process_id": name, "pid": 10, "caller_id": caller, "request_id": f"req-{name}",
                    "command": command, "cwd": r"C:\repo", "stdout": stdout, "stderr": stderr, "exit_code": 0,
                    "started_at": started, "finished_at": started,
                }
                (receipts / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")

            write(
                "route",
                "python tools\\swarm_route.py route --work-id rr-849 --kind portable",
                json.dumps({"work_id": "rr-849", "decision_id": "decision-1", "route": "omen", "kind": "portable"}) + "\n",
                started="2026-09-09T05:43:01Z",
            )
            write(
                "commit",
                "git commit -m identity",
                "[chatgpt/849 abcdef1] identity\n",
                started="2026-09-09T05:43:02Z",
            )
            write(
                "pr",
                "gh pr create --repo organicoverlords/regression-research --title x --body y",
                "https://github.com/organicoverlords/regression-research/pull/852\n",
                started="2026-09-09T05:43:03Z",
            )
            write(
                "other-caller",
                "python tools\\swarm_exec.py --work-id foreign --kind portable -- echo no",
                caller="caller_other",
                started="2026-09-09T05:43:04Z",
            )
            write(
                "next-create",
                "python tools\\worker_report_history.py create-manual --repo p3",
                json.dumps({"ok": True, "run_id": "manual-next"}) + "\n",
                started="2026-09-09T05:43:05Z",
            )
            write(
                "after-boundary",
                "python tools\\swarm_exec.py --work-id wrong --kind portable -- echo no",
                started="2026-09-09T05:43:06Z",
            )

            result = capture_trace(run_id=run_id, receipt_dir=receipts, manual_root=manual)
            self.assertTrue(result["ok"])
            trace = load_trace(manual, run_id)
            self.assertIsNotNone(trace)
            assert trace is not None
            self.assertEqual(trace["caller_id"], "caller_trace")
            self.assertEqual(trace["boundary"], "NEXT_MANUAL_CREATE:manual-next")
            self.assertTrue(trace["complete_through_boundary"])
            self.assertEqual(trace["work_ids"], ["rr-849"])
            self.assertEqual(trace["commit_shas"], ["abcdef1"])
            self.assertEqual(trace["github_refs"], ["https://github.com/organicoverlords/regression-research/pull/852"])
            self.assertEqual(trace["route_decisions"][0]["decision_id"], "decision-1")
            self.assertNotIn("wrong", trace["work_ids"])
            self.assertNotIn("foreign", trace["work_ids"])
            process_ids = {item["process_id"] for item in trace["processes"]}
            self.assertIn("create-trace", process_ids)
            self.assertIn("route", process_ids)
            self.assertNotIn("next-create", process_ids)


    def test_manual_current_audit_surfaces_exact_binding_without_claiming_liveness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual = root / "worker-reports" / "manual"
            current = manual / "current"
            history = manual / "history"
            current.mkdir(parents=True)
            run_id = "manual-bound"
            (current / f"{run_id}.md").write_text(
                f"run_id: {run_id}\n"
                "started_at: 2026-09-09T05:00:00+00:00\n"
                "last_activity_at: 2026-09-09T05:00:00+00:00\n"
                "repo: regression-research\nstate: RUNNING\noutcome: in progress\n",
                encoding="utf-8",
            )
            receipts = root / "receipts"
            receipts.mkdir()
            self._write_receipt(receipts, name="create-process", pid=17, run_id=run_id)
            capture_binding(
                run_id=run_id,
                creator_child_pid=17,
                receipt_dir=receipts,
                manual_root=manual,
                timeout_seconds=0,
            )

            audit = audit_manual_current_reports(current, history)
            row = audit["reports"][0]
            self.assertEqual(row["identity"]["status"], "BOUND")
            self.assertEqual(row["identity"]["caller_id"], "caller_exact")
            self.assertEqual(row["liveness"], "NOT_ESTABLISHED_BY_REPORT")

    def test_abandoned_archive_carries_exact_identity_as_derived_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manual = root / "worker-reports" / "manual"
            current = manual / "current"
            history = manual / "history"
            current.mkdir(parents=True)
            run_id = "manual-stale-bound"
            report = current / f"{run_id}.md"
            report.write_text(
                f"run_id: {run_id}\n"
                "started_at: 2026-09-09T01:00:00+00:00\n"
                "last_activity_at: 2026-09-09T01:00:00+00:00\n"
                "repo: regression-research\nstate: RUNNING\noutcome: in progress\n",
                encoding="utf-8",
            )
            receipts = root / "receipts"
            receipts.mkdir()
            self._write_receipt(receipts, name="create-stale", pid=23, run_id=run_id)
            capture_binding(
                run_id=run_id,
                creator_child_pid=23,
                receipt_dir=receipts,
                manual_root=manual,
                timeout_seconds=0,
            )

            with patch.dict(os.environ, {"MCP_PROCESS_RECEIPT_DIR": str(receipts)}):
                archived = _archive_manual_nonterminal_snapshot(report, history, lifecycle_status="ABANDONED_OPEN")
            metadata = json.loads(
                (history / "_reports" / f"{archived['sha256']}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["lifecycle_status"], "ABANDONED_OPEN")
            self.assertEqual(metadata["manual_identity"]["status"], "BOUND")
            self.assertEqual(metadata["manual_identity"]["create_process_id"], "create-stale")
            self.assertEqual(metadata["authority"], "NON_AUTHORITATIVE_REPORT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
