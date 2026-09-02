from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.worker_report_history import archive_finalized_report, summarize_history


class WorkerReportHistoryTests(unittest.TestCase):
    def test_archives_exact_finalized_bytes_under_worker_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Juniper.md"
            raw = b"worker: Juniper\r\nstate: COMPLETE\r\noutcome: SUBSTANTIVE_PROGRESS\r\n"
            report.write_bytes(raw)
            result = archive_finalized_report(report, root / "history")
            archived = Path(result["path"])
            self.assertTrue(result["archived"])
            self.assertEqual(archived.parent.name, "Juniper")
            self.assertEqual(archived.read_bytes(), raw)

    def test_derives_duration_and_useful_metadata_without_worker_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Cedar.md"
            report.write_text(
                "worker: Cedar\nstate: COMPLETE\nstarted_at: 2026-09-02T18:00:00+03:00\n"
                "last_activity_at: 2026-09-02T18:23:30+03:00\nrepo: organicoverlords/p3\n"
                "scope: p3#414\noutcome: SUBSTANTIVE_PROGRESS\nmutation: PR #764 merged\n"
                "validation: focused PASS\nremaining_gate: none\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, root / "history")
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["duration_seconds"], 1410.0)
            self.assertEqual(metadata["duration_minutes"], 23.5)
            self.assertEqual(metadata["target_run_minutes"], 24.0)
            self.assertEqual(metadata["target_utilization_pct"], 97.9)
            self.assertEqual(metadata["mutation"], "PR #764 merged")

    def test_identical_report_deduplicates_and_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Alder.md"
            report.write_text("worker: Alder\nstate: WAITING\noutcome: SUBSTANTIVE_PROGRESS\n", encoding="utf-8")
            first = archive_finalized_report(report, root / "history")
            archived = Path(first["path"])
            metadata = Path(first["metadata_path"])
            first_mtime = archived.stat().st_mtime_ns
            metadata_mtime = metadata.stat().st_mtime_ns
            second = archive_finalized_report(report, root / "history")
            self.assertFalse(second["archived"])
            self.assertTrue(second["deduplicated"])
            self.assertFalse(second["metadata_created"])
            self.assertEqual(archived.stat().st_mtime_ns, first_mtime)
            self.assertEqual(metadata.stat().st_mtime_ns, metadata_mtime)

    def test_blocked_and_legacy_done_remain_archivable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for worker, state in (("Ember", "BLOCKED"), ("Harbor", "DONE")):
                report = root / f"{worker}.md"
                report.write_text(f"worker: {worker}\nstate: {state}\n", encoding="utf-8")
                self.assertTrue(archive_finalized_report(report, root / "history")["ok"])

    def test_archive_updates_shared_metrics_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Juniper.md"
            report.write_text(
                "worker: Juniper\nstate: COMPLETE\nstarted_at: 2099-01-01T00:00:00+00:00\n"
                "last_activity_at: 2099-01-01T00:22:48+00:00\nrepo: organicoverlords/regression-research\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, root / "history")
            metrics_path = Path(result["fleet_metrics_path"])
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertEqual(metrics["target_run_minutes"], 24.0)
            self.assertEqual(metrics["captured_runs"], 1)
            self.assertEqual(metrics["average_duration_minutes"], 22.8)
            self.assertEqual(metrics["average_target_utilization_pct"], 95.0)
            self.assertEqual(metrics["by_worker_latest"]["Juniper"]["duration_minutes"], 22.8)

    def test_summary_keeps_capacity_distinct_from_uptime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history" / "Alder"
            history.mkdir(parents=True)
            payload = {
                "schema": "worker-report-history.v2", "worker": "Alder",
                "finished_at": "2099-01-01T01:00:00+00:00", "duration_minutes": 24.0,
                "target_utilization_pct": 100.0,
            }
            (history / "a.json").write_text(json.dumps(payload), encoding="utf-8")
            summary = summarize_history(root / "history", hours=1)
            self.assertEqual(summary["average_target_utilization_pct"], 100.0)
            self.assertEqual(summary["capacity_pct_of_one_continuous_worker"], 40.0)
            self.assertNotIn("uptime", summary)

    def test_running_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Cedar.md"
            report.write_text("worker: Cedar\nstate: RUNNING\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                archive_finalized_report(report, root / "history")


if __name__ == "__main__":
    unittest.main()
