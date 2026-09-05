from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.worker_report_history import archive_finalized_report, worker_history_events


class WorkerReportHistoryTests(unittest.TestCase):
    def test_archives_exact_finalized_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Juniper.md"
            raw = b"worker: Juniper\r\nstate: COMPLETE\r\noutcome: SUBSTANTIVE_PROGRESS\r\n"
            report.write_bytes(raw)
            result = archive_finalized_report(report, root / "history")
            archived = Path(result["path"])
            self.assertTrue(result["archived"])
            self.assertEqual(archived.parent.name, "_reports")
            self.assertEqual(archived.read_bytes(), raw)

    def test_derives_runtime_and_preserves_reported_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Cedar.md"
            report.write_text(
                "worker: Cedar\nstate: COMPLETE\nstarted_at: 2026-09-02T18:00:00+03:00\n"
                "last_activity_at: 2026-09-02T18:23:30+03:00\nrepo: organicoverlords/p3\n"
                "scope: p3#414\noutcome: SUBSTANTIVE_PROGRESS\nmutations: PR #764 merged\n"
                "validation: focused PASS\nremaining_heavy_gate: runtime proof\n"
                "stop_reason: SUBSTANTIVE_SLICES_PUBLISHED\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, root / "history")
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["schema"], "worker-report-history.v6")
            self.assertEqual(metadata["duration_seconds"], 1410.0)
            self.assertEqual(metadata["duration_minutes"], 23.5)
            self.assertEqual(metadata["target_run_minutes"], 24.0)
            self.assertEqual(metadata["target_utilization_pct"], 97.9)
            self.assertEqual(metadata["mutation"], "PR #764 merged")
            self.assertEqual(metadata["remaining_gate"], "runtime proof")
            self.assertEqual(metadata["stop_reason"], "SUBSTANTIVE_SLICES_PUBLISHED")
            self.assertEqual(metadata["reported_fields"]["stop_reason"], "SUBSTANTIVE_SLICES_PUBLISHED")
            self.assertNotIn("pending_gate_classes", metadata)
            self.assertNotIn("tool_failures_total", metadata)
            self.assertNotIn("early_stop", metadata)

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

    def test_history_metadata_becomes_timeline_event_and_reads_v5_raw_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history" / "_reports"
            history.mkdir(parents=True)
            payload = {
                "schema": "worker-report-history.v5", "report_sha256": "abc", "worker": "Cedar",
                "state": "COMPLETE", "outcome": "SUBSTANTIVE_PROGRESS",
                "finished_at": "2099-01-01T00:23:00+00:00", "archived_at": "2099-01-01T00:23:02+00:00",
                "duration_minutes": 23.0, "target_run_minutes": 24.0, "target_utilization_pct": 95.8,
                "repo": "organicoverlords/p3", "scope": "p3#414", "last_event": "PR #764 merged",
                "remaining_gate": "none", "reported_stop_reason": "SUBSTANTIVE_SLICES_PUBLISHED", "stop_reason": "OTHER",
            }
            (history / "abc.json").write_text(json.dumps(payload), encoding="utf-8")
            event = worker_history_events(root / "history")[0]
            self.assertEqual(event["source_type"], "WORKER_REPORT")
            self.assertEqual(event["project"], "p3")
            self.assertEqual(event["duration_minutes"], 23.0)
            self.assertEqual(event["target_utilization_pct"], 95.8)
            self.assertEqual(event["remaining_gate"], "none")
            self.assertEqual(event["stop_reason"], "SUBSTANTIVE_SLICES_PUBLISHED")

    def test_current_report_rejects_missing_canonical_fields_and_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "0123456789abcdef0123456789abcdef"
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstate: COMPLETE\noutcome: SUBSTANTIVE_PROGRESS\n"
                "repo: p3\nscope: p3#803\nmutations: changed gameplay\nvalidation: PASS\n"
                "remaining_heavy_gate: runtime proof\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "started_at.*last_activity_at.*mutation.*remaining_gate"):
                archive_finalized_report(report, root / "history")

    def test_current_report_requires_filename_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            report = current / "0123456789abcdef0123456789abcdef.md"
            report.write_text(
                "automation_id: fedcba9876543210fedcba9876543210\n"
                "started_at: 2099-01-01T00:00:00+00:00\nlast_activity_at: 2099-01-01T00:23:00+00:00\n"
                "repo: p3\nscope: p3#803\nstate: COMPLETE\noutcome: SUBSTANTIVE_PROGRESS\n"
                "mutation: changed gameplay\nvalidation: PASS\nremaining_gate: none\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "automation_id does not match filename"):
                archive_finalized_report(report, root / "history")

    def test_current_report_rejects_invalid_or_reversed_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "0123456789abcdef0123456789abcdef"
            report = current / f"{automation_id}.md"
            common = (
                f"automation_id: {automation_id}\nrepo: p3\nscope: p3#803\nstate: COMPLETE\n"
                "outcome: SUBSTANTIVE_PROGRESS\nmutation: changed gameplay\nvalidation: PASS\nremaining_gate: none\n"
            )
            report.write_text(common + "started_at: not-a-time\nlast_activity_at: 2099-01-01T00:23:00+00:00\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "started_at is not a valid"):
                archive_finalized_report(report, root / "history")
            report.write_text(common + "started_at: 2099-01-01T00:24:00+00:00\nlast_activity_at: 2099-01-01T00:23:00+00:00\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "precedes started_at"):
                archive_finalized_report(report, root / "history")

    def test_valid_current_report_archives_and_derives_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "0123456789abcdef0123456789abcdef"
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\ndisplay_label: Birch\n"
                "started_at: 2099-01-01T00:00:00+00:00\nlast_activity_at: 2099-01-01T00:23:00+00:00\n"
                "repo: p3\nscope: p3#803\nstate: COMPLETE\noutcome: SUBSTANTIVE_PROGRESS\n"
                "mutation: changed gameplay\nvalidation: PASS\nremaining_gate: none\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, root / "history")
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["duration_minutes"], 23.0)
            self.assertEqual(metadata["target_utilization_pct"], 95.8)


    def test_premature_run_finished_rejects_local_contention_stop_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            cases = (
                ("5.55", "2099-01-01T00:05:33+00:00", "Useful bounded window exhausted; heavy runtime acceptance remains a separate resource-dependent gate."),
                ("13.52", "2099-01-01T00:13:31+00:00", "Bounded selection found no additional safe mutation while collision ownership was unavailable and the heavy runtime lane was occupied."),
                ("7.03", "2099-01-01T00:07:02+00:00", "Useful independent work window exhausted while heavy Unreal lane remained occupied."),
            )
            for suffix, finished_at, stop_reason in cases:
                with self.subTest(duration=suffix):
                    automation_id = (suffix.replace(".", "") + "0" * 32)[:32]
                    report = current / f"{automation_id}.md"
                    report.write_text(
                        f"automation_id: {automation_id}\nstarted_at: 2099-01-01T00:00:00+00:00\n"
                        f"last_activity_at: {finished_at}\nrepo: p3\nscope: p3#960\nstate: RUN_FINISHED\n"
                        "outcome: validated existing WIP\nmutation: no source mutation\nvalidation: PASS\n"
                        f"remaining_gate: heavy runtime acceptance\nstop_reason: {stop_reason}\n",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(ValueError, "this run is NOT finished"):
                        archive_finalized_report(report, root / "history")
                    current_text = report.read_text(encoding="utf-8")
                    self.assertIn("state: RUNNING", current_text)
                    self.assertNotIn("state: RUN_FINISHED", current_text)
                    self.assertFalse((root / "history" / "_reports").exists())

    def test_run_finished_allows_on_target_or_true_terminal_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            cases = (
                ("a" * 32, "2099-01-01T00:20:00+00:00", "heavy runtime lane occupied"),
                ("b" * 32, "2099-01-01T00:05:00+00:00", "user interrupted the run"),
                ("c" * 32, "2099-01-01T00:05:00+00:00", "task-level blocker proven after safe existing execution surfaces and independent useful work were exhausted"),
            )
            for automation_id, finished_at, stop_reason in cases:
                with self.subTest(automation_id=automation_id):
                    report = current / f"{automation_id}.md"
                    report.write_text(
                        f"automation_id: {automation_id}\nstarted_at: 2099-01-01T00:00:00+00:00\n"
                        f"last_activity_at: {finished_at}\nrepo: p3\nscope: p3#960\nstate: RUN_FINISHED\n"
                        "outcome: useful work\nmutation: no source mutation\nvalidation: PASS\n"
                        f"remaining_gate: none\nstop_reason: {stop_reason}\n",
                        encoding="utf-8",
                    )
                    self.assertTrue(archive_finalized_report(report, root / "history")["ok"])

    def test_running_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Cedar.md"
            report.write_text("worker: Cedar\nstate: RUNNING\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                archive_finalized_report(report, root / "history")


if __name__ == "__main__":
    unittest.main()
