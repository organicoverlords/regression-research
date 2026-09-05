from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tools.worker_report_history import archive_finalized_report, audit_manual_current_reports, begin_timed_run, build_metrics_projection, worker_history_events


class WorkerReportHistoryTests(unittest.TestCase):
    def test_manual_current_audit_never_treats_running_file_as_liveness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            run_id = "manual-test-running"
            report = current / f"{run_id}.md"
            report.write_text(
                f"run_id: {run_id}\nstarted_at: 2026-09-05T10:00:00+00:00\n"
                "last_activity_at: 2026-09-05T10:10:00+00:00\nrepo: p3\nscope: test\n"
                "state: RUNNING\noutcome: RUNNING\nmutation: none\nvalidation: none\n"
                "remaining_gate: finish turn\nfinding_tags: proof\nfindings: current file alone is not liveness\n",
                encoding="utf-8",
            )
            audit = audit_manual_current_reports(current, history)
            self.assertEqual(audit["unfinalized_count"], 1)
            self.assertEqual(audit["reports"][0]["lifecycle_status"], "UNFINALIZED_RUNNING")
            self.assertEqual(audit["reports"][0]["liveness"], "NOT_ESTABLISHED_BY_REPORT")

    def test_manual_current_audit_distinguishes_archived_pointer_and_unarchived_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            for run_id in ("manual-archived", "manual-unarchived"):
                report = current / f"{run_id}.md"
                report.write_text(
                    f"run_id: {run_id}\nstarted_at: 2026-09-05T10:00:00+00:00\n"
                    "last_activity_at: 2026-09-05T10:10:00+00:00\nrepo: p3\nscope: test\n"
                    "state: RUN_FINISHED\noutcome: done\nmutation: none\nvalidation: PASS\n"
                    "remaining_gate: none\nfinding_tags: proof\nfindings: terminal manual report fixture\nstop_reason: done\n",
                    encoding="utf-8",
                )
            archive_finalized_report(current / "manual-archived.md", history)
            audit = audit_manual_current_reports(current, history)
            by_id = {row["run_id"]: row for row in audit["reports"]}
            self.assertEqual(by_id["manual-archived"]["lifecycle_status"], "ARCHIVED_CURRENT_POINTER")
            self.assertEqual(by_id["manual-unarchived"]["lifecycle_status"], "UNARCHIVED_TERMINAL")
            self.assertEqual(audit["unarchived_terminal_count"], 1)

    @staticmethod
    def _write_timed_start_receipt(
        report: Path, observed_started_at: str, *, reported_started_at: str | None = None
    ) -> Path:
        receipt = report.parent.parent / ".supervision" / f"{report.stem}.start.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(
            json.dumps({
                "schema": "worker-run-start.v1",
                "automation_id": report.stem,
                "observed_started_at": observed_started_at,
                "reported_started_at": reported_started_at or observed_started_at,
                "initial_report_sha256": "fixture",
            }) + "\n",
            encoding="utf-8",
        )
        observed = datetime.fromisoformat(observed_started_at.replace("Z", "+00:00"))
        os.utime(receipt, (observed.timestamp(), observed.timestamp()))
        return receipt

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

    def test_current_report_rejects_duplicate_canonical_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "0123456789abcdef0123456789abcdef"
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\n"
                "started_at: 2099-01-01T00:00:00+00:00\nlast_activity_at: 2099-01-01T00:20:00+00:00\n"
                "repo: p3\nscope: p3#500\nstate: RUN_FINISHED\noutcome: useful work\n"
                "mutation: changed gameplay\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: premature finalization rejected; run continuing\n"
                "stop_reason: useful work window materially exhausted\n",
                encoding="utf-8",
            )
            before = report.read_bytes()
            with self.assertRaisesRegex(ValueError, r"duplicate canonical field\(s\): stop_reason"):
                archive_finalized_report(report, root / "history")
            self.assertEqual(report.read_bytes(), before)
            self.assertFalse((root / "history" / "_reports").exists())

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
                ("5.55", "2020-01-01T00:05:33+00:00", "Useful bounded window exhausted; heavy runtime acceptance remains a separate resource-dependent gate."),
                ("13.52", "2020-01-01T00:13:31+00:00", "Bounded selection found no additional safe mutation while collision ownership was unavailable and the heavy runtime lane was occupied."),
                ("7.03", "2020-01-01T00:07:02+00:00", "Useful independent work window exhausted while heavy Unreal lane remained occupied."),
            )
            for suffix, finished_at, stop_reason in cases:
                with self.subTest(duration=suffix):
                    automation_id = (suffix.replace(".", "") + "0" * 32)[:32]
                    report = current / f"{automation_id}.md"
                    report.write_text(
                        f"automation_id: {automation_id}\nstarted_at: 2020-01-01T00:00:00+00:00\n"
                        f"last_activity_at: {finished_at}\nrepo: p3\nscope: p3#960\nstate: RUN_FINISHED\n"
                        "outcome: validated existing WIP\nmutation: no source mutation\nvalidation: PASS\n"
                        f"remaining_gate: heavy runtime acceptance\nstop_reason: {stop_reason}\n",
                        encoding="utf-8",
                    )
                    self._write_timed_start_receipt(report, "2020-01-01T00:00:00+00:00")
                    with self.assertRaisesRegex(ValueError, "this run is NOT finished"):
                        archive_finalized_report(report, root / "history")
                    current_text = report.read_text(encoding="utf-8")
                    self.assertIn("state: RUNNING", current_text)
                    self.assertNotIn("state: RUN_FINISHED", current_text)
                    self.assertIn("stop_reason: premature finalization rejected; run continuing", current_text)
                    self.assertNotIn(stop_reason, current_text)
                    self.assertFalse((root / "history" / "_reports").exists())

    def test_run_finished_rejects_future_last_activity_and_restores_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "f" * 32
            now = datetime.now().astimezone()
            started = now - timedelta(minutes=1)
            future = now + timedelta(minutes=20)
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {started.isoformat()}\n"
                f"last_activity_at: {future.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                "outcome: useful work\nmutation: changed gameplay\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: useful work window materially exhausted\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "last_activity_at is in the future.*NOT finished"):
                archive_finalized_report(report, root / "history")
            current_text = report.read_text(encoding="utf-8")
            self.assertIn("state: RUNNING", current_text)
            self.assertIn("stop_reason: premature finalization rejected; run continuing", current_text)
            self.assertFalse((root / "history" / "_reports").exists())

    def test_run_finished_rejects_claimed_activity_after_report_write_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            now = datetime.now().astimezone()
            cases = (
                ("a" * 32, "started_at", now - timedelta(minutes=5), now - timedelta(minutes=2), now - timedelta(minutes=10)),
                ("b" * 32, "last_activity_at", now - timedelta(minutes=25), now - timedelta(minutes=2), now - timedelta(minutes=10)),
            )
            for automation_id, invalid_field, started, last_activity, written_at in cases:
                with self.subTest(invalid_field=invalid_field):
                    report = current / f"{automation_id}.md"
                    report.write_text(
                        f"automation_id: {automation_id}\nstarted_at: {started.isoformat()}\n"
                        f"last_activity_at: {last_activity.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                        "outcome: useful work\nmutation: changed gameplay\nvalidation: PASS\nremaining_gate: none\n"
                        "stop_reason: useful work window materially exhausted\n",
                        encoding="utf-8",
                    )
                    os.utime(report, (written_at.timestamp(), written_at.timestamp()))
                    with self.assertRaisesRegex(ValueError, rf"{invalid_field} occurs after report file write time.*NOT finished"):
                        archive_finalized_report(report, root / "history")
                    current_text = report.read_text(encoding="utf-8")
                    self.assertIn("state: RUNNING", current_text)
                    self.assertIn("stop_reason: premature finalization rejected; run continuing", current_text)
                    self.assertFalse((root / "history" / "_reports").exists())

    def test_timed_run_begin_allows_earlier_reported_start_but_observes_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "1" * 32
            now = datetime.now().astimezone()
            reported_started = now - timedelta(minutes=20)
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {reported_started.isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUNNING\n"
                "outcome: starting\nmutation: none\nvalidation: pending\nremaining_gate: none\n",
                encoding="utf-8",
            )
            result = begin_timed_run(report)
            observed = datetime.fromisoformat(result["observed_started_at"])
            self.assertGreaterEqual(observed, now)
            self.assertGreater((observed - reported_started).total_seconds(), 19 * 60)
            self.assertTrue(Path(result["receipt_path"]).exists())

    def test_timed_run_begin_rejects_future_reported_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "f" * 32
            future = datetime.now().astimezone() + timedelta(minutes=5)
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {future.isoformat()}\n"
                f"last_activity_at: {future.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUNNING\n"
                "outcome: starting\nmutation: none\nvalidation: pending\nremaining_gate: none\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "started_at is in the future"):
                begin_timed_run(report)
            self.assertFalse((root / ".supervision" / f"{automation_id}.start.json").exists())

    def test_timed_run_finished_requires_machine_start_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "2" * 32
            now = datetime.now().astimezone()
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {(now - timedelta(minutes=20)).isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                "outcome: claimed work\nmutation: none\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: useful work window materially exhausted\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "requires machine start evidence"):
                archive_finalized_report(report, root / "history")
            self.assertIn("state: RUNNING", report.read_text(encoding="utf-8"))
            self.assertFalse((root / "history" / "_reports").exists())

    def test_timed_run_backdated_start_after_begin_cannot_inflate_utilization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "3" * 32
            observed_window = datetime.now().astimezone()
            started = observed_window - timedelta(minutes=20)
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {started.isoformat()}\n"
                f"last_activity_at: {started.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUNNING\n"
                "outcome: starting\nmutation: none\nvalidation: pending\nremaining_gate: none\n",
                encoding="utf-8",
            )
            begin_timed_run(report)
            finished = datetime.now().astimezone()
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {(started - timedelta(minutes=20)).isoformat()}\n"
                f"last_activity_at: {finished.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                "outcome: claimed work\nmutation: none\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: useful work window materially exhausted\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "reported started_at changed after timed run begin"):
                archive_finalized_report(report, root / "history")
            self.assertTrue((root / ".supervision" / f"{automation_id}.start.json").exists())
            self.assertIn("state: RUNNING", report.read_text(encoding="utf-8"))

    def test_timed_run_rejects_stale_receipt_from_prior_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "5" * 32
            now = datetime.now().astimezone()
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {(now - timedelta(minutes=5)).isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                "outcome: claimed work\nmutation: none\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: useful work window materially exhausted\n",
                encoding="utf-8",
            )
            stale_observed = (now - timedelta(minutes=60)).isoformat()
            current_started = (now - timedelta(minutes=5)).isoformat()
            receipt = self._write_timed_start_receipt(
                report, stale_observed, reported_started_at=current_started
            )
            with self.assertRaisesRegex(ValueError, "start receipt is stale for this generation"):
                archive_finalized_report(report, root / "history")
            self.assertTrue(receipt.exists())
            self.assertIn("state: RUNNING", report.read_text(encoding="utf-8"))
            self.assertFalse((root / "history" / "_reports").exists())

    def test_timed_run_rejects_receipt_payload_backdated_before_file_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "8" * 32
            now = datetime.now().astimezone()
            started = now - timedelta(minutes=20)
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {started.isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                "outcome: claimed work\nmutation: none\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: useful work window materially exhausted\n",
                encoding="utf-8",
            )
            receipt = current.parent / ".supervision" / f"{automation_id}.start.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(
                json.dumps({
                    "schema": "worker-run-start.v1",
                    "automation_id": automation_id,
                    "observed_started_at": started.isoformat(),
                    "reported_started_at": started.isoformat(),
                    "initial_report_sha256": "forged",
                }) + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "does not match receipt file write time"):
                archive_finalized_report(report, root / "history")
            self.assertTrue(receipt.exists())
            self.assertIn("state: RUNNING", report.read_text(encoding="utf-8"))
            self.assertFalse((root / "history" / "_reports").exists())

    def test_late_begin_cannot_self_attest_true_no_safe_work_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "6" * 32
            now = datetime.now().astimezone()
            reported_started = now - timedelta(minutes=18)
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {reported_started.isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUNNING\n"
                "outcome: active\nmutation: product work\nvalidation: PASS\nremaining_gate: none\n",
                encoding="utf-8",
            )
            begin = begin_timed_run(report)
            finished = datetime.now().astimezone()
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {reported_started.isoformat()}\n"
                f"last_activity_at: {finished.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                "outcome: claimed work\nmutation: product work\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: task-level blocker proven after safe existing execution surfaces and independent useful work were exhausted\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "late begin cannot establish early-stop eligibility"):
                archive_finalized_report(report, root / "history")
            self.assertTrue(Path(begin["receipt_path"]).exists())
            self.assertIn("state: RUNNING", report.read_text(encoding="utf-8"))
            self.assertFalse((root / "history" / "_reports").exists())

    def test_timed_run_archive_uses_observed_start_and_consumes_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "4" * 32
            started = datetime.now().astimezone() - timedelta(minutes=20)
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {started.isoformat()}\n"
                f"last_activity_at: {started.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUNNING\n"
                "outcome: starting\nmutation: none\nvalidation: pending\nremaining_gate: none\n",
                encoding="utf-8",
            )
            begin_result = begin_timed_run(report)
            receipt = Path(begin_result["receipt_path"])
            finished = datetime.now().astimezone()
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: {started.isoformat()}\n"
                f"last_activity_at: {finished.isoformat()}\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                "outcome: interrupted\nmutation: none\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: user interrupted the run\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, root / "history")
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            self.assertTrue(result["ok"])
            self.assertEqual(metadata["observed_started_at"], begin_result["observed_started_at"])
            self.assertLess(metadata["duration_minutes"], 0.1)
            self.assertFalse(receipt.exists())

    def test_metrics_and_events_ignore_archives_with_future_finish_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history" / "_reports"
            history.mkdir(parents=True)
            now = datetime.now().astimezone()
            good = {
                "schema": "worker-report-history.v6", "report_sha256": "good", "automation_id": "a" * 32,
                "display_label": "Good", "state": "RUN_FINISHED", "outcome": "useful work",
                "finished_at": (now - timedelta(minutes=2)).isoformat(), "archived_at": (now - timedelta(minutes=1)).isoformat(),
                "duration_minutes": 20.0, "target_utilization_pct": 83.3, "repo": "p3", "scope": "p3#500",
                "stop_reason": "useful work window materially exhausted",
            }
            impossible = {
                **good, "report_sha256": "impossible", "automation_id": "b" * 32, "display_label": "Impossible",
                "finished_at": (now + timedelta(minutes=20)).isoformat(), "archived_at": now.isoformat(),
            }
            (history / "good.json").write_text(json.dumps(good), encoding="utf-8")
            (history / "impossible.json").write_text(json.dumps(impossible), encoding="utf-8")
            metrics = build_metrics_projection(root / "history")
            self.assertEqual(metrics["reports"], 1)
            self.assertEqual(metrics["latest_reports"][0]["report_sha256"], "good")
            events = worker_history_events(root / "history")
            self.assertEqual([event["id"] for event in events], ["worker:good"])

    def test_run_finished_allows_on_target_or_true_terminal_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            cases = (
                ("a" * 32, "2020-01-01T00:20:00+00:00", "heavy runtime lane occupied"),
                ("b" * 32, "2020-01-01T00:05:00+00:00", "user interrupted the run"),
                ("c" * 32, "2020-01-01T00:05:00+00:00", "task-level blocker proven after safe existing execution surfaces and independent useful work were exhausted"),
            )
            for automation_id, finished_at, stop_reason in cases:
                with self.subTest(automation_id=automation_id):
                    report = current / f"{automation_id}.md"
                    report.write_text(
                        f"automation_id: {automation_id}\nstarted_at: 2020-01-01T00:00:00+00:00\n"
                        f"last_activity_at: {finished_at}\nrepo: p3\nscope: p3#960\nstate: RUN_FINISHED\n"
                        "outcome: useful work\nmutation: no source mutation\nvalidation: PASS\n"
                        f"remaining_gate: none\nstop_reason: {stop_reason}\n",
                        encoding="utf-8",
                    )
                    self._write_timed_start_receipt(report, "2020-01-01T00:00:00+00:00")
                    self.assertTrue(archive_finalized_report(report, root / "history")["ok"])

    def test_on_target_run_finished_rejects_stale_continuation_stop_reason_without_reopening_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "d" * 32
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: 2020-01-01T00:00:00+00:00\n"
                "last_activity_at: 2020-01-01T00:20:00+00:00\nrepo: p3\nscope: p3#500\nstate: RUN_FINISHED\n"
                "outcome: useful work\nmutation: changed gameplay\nvalidation: PASS\nremaining_gate: none\n"
                "stop_reason: premature finalization rejected; run continuing\n",
                encoding="utf-8",
            )
            self._write_timed_start_receipt(report, "2020-01-01T00:00:00+00:00")
            with self.assertRaisesRegex(ValueError, "continuation stop_reason sentinel"):
                archive_finalized_report(report, root / "history")
            current_text = report.read_text(encoding="utf-8")
            self.assertIn("state: RUN_FINISHED", current_text)
            self.assertIn("stop_reason: premature finalization rejected; run continuing", current_text)
            self.assertFalse((root / "history" / "_reports").exists())

            report.write_text(
                current_text.replace(
                    "stop_reason: premature finalization rejected; run continuing",
                    "stop_reason: useful work window materially exhausted",
                ),
                encoding="utf-8",
            )
            result = archive_finalized_report(report, root / "history")
            self.assertTrue(result["ok"])
            self.assertTrue(result["archived"])

    def test_running_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Cedar.md"
            report.write_text("worker: Cedar\nstate: RUNNING\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                archive_finalized_report(report, root / "history")


    def test_timed_reports_preserve_findings_and_utilization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "e" * 32
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\nstarted_at: 2020-01-01T00:00:00+00:00\n"
                "last_activity_at: 2020-01-01T00:20:00+00:00\nrepo: p3\nscope: p3#523\nstate: RUN_FINISHED\n"
                "outcome: useful work\nmutation: fixed wrapper\nvalidation: PASS\nremaining_gate: none\n"
                "finding_tags: bug, wrapper_anomaly\nfindings: wrapper launched an incompatible child path\n"
                "stop_reason: useful work window materially exhausted\n",
                encoding="utf-8",
            )
            self._write_timed_start_receipt(report, "2020-01-01T00:00:00+00:00")
            result = archive_finalized_report(report, root / "history")
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            metrics = json.loads(Path(result["metrics_path"]).read_text(encoding="utf-8"))
            self.assertEqual(result["population"], "timed")
            self.assertEqual(metadata["finding_tags"], ["bug", "wrapper_anomaly"])
            self.assertEqual(metadata["target_run_minutes"], 24.0)
            self.assertEqual(metadata["target_utilization_pct"], 83.3)
            self.assertEqual(metrics["finding_tag_counts"], {"bug": 1, "wrapper_anomaly": 1})
            self.assertIn("average_target_utilization_pct", metrics)

    def test_manual_reports_track_duration_and_findings_without_timed_utilization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            run_id = "manual-20260905-001"
            report = current / f"{run_id}.md"
            report.write_text(
                f"run_id: {run_id}\ndisplay_label: Manual ChatGPT\nstarted_at: 2020-01-01T00:00:00+00:00\n"
                "last_activity_at: 2020-01-01T00:07:30+00:00\nrepo: regression-research\nscope: #523\nstate: RUN_FINISHED\n"
                "outcome: useful work\nmutation: added manual reporting\nvalidation: PASS\nremaining_gate: none\n"
                "finding_tags: route_problem, improvement\nfindings: route fallback was noisy; reporting separation improved\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, history)
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            metrics = json.loads(Path(result["metrics_path"]).read_text(encoding="utf-8"))
            self.assertEqual(result["population"], "manual")
            self.assertEqual(metadata["population"], "manual")
            self.assertEqual(metadata["run_id"], run_id)
            self.assertEqual(metadata["duration_minutes"], 7.5)
            self.assertNotIn("target_run_minutes", metadata)
            self.assertNotIn("target_utilization_pct", metadata)
            self.assertEqual(metrics["schema"], "manual-worker-report-metrics.v1")
            self.assertEqual(metrics["population"], "manual")
            self.assertEqual(metrics["finding_tag_counts"], {"improvement": 1, "route_problem": 1})
            self.assertNotIn("average_target_utilization_pct", metrics)
            self.assertNotIn("target_utilization_pct", metrics["latest_reports"][0])

    def test_timed_and_manual_metrics_ignore_foreign_population_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = datetime.now().astimezone().isoformat()
            timed_history = root / "history" / "_reports"
            manual_history = root / "manual" / "history" / "_reports"
            timed_history.mkdir(parents=True)
            manual_history.mkdir(parents=True)
            manual_record = {
                "schema": "worker-report-history.v6", "population": "manual", "report_sha256": "manual-in-timed",
                "archived_at": now, "finished_at": now, "duration_minutes": 5.0,
            }
            timed_record = {
                "schema": "worker-report-history.v6", "population": "timed", "report_sha256": "timed-in-manual",
                "archived_at": now, "finished_at": now, "duration_minutes": 20.0, "target_utilization_pct": 83.3,
            }
            (timed_history / "manual.json").write_text(json.dumps(manual_record), encoding="utf-8")
            (manual_history / "timed.json").write_text(json.dumps(timed_record), encoding="utf-8")
            self.assertEqual(build_metrics_projection(root / "history")["reports"], 0)
            manual_metrics = build_metrics_projection(root / "manual" / "history")
            self.assertEqual(manual_metrics["reports"], 0)
            self.assertNotIn("average_target_utilization_pct", manual_metrics)


    def test_manual_finding_tag_aliases_normalize_to_canonical_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            run_id = "manual-aliases"
            report = current / f"{run_id}.md"
            report.write_text(
                f"run_id: {run_id}\nstarted_at: 2026-09-05T09:00:00+03:00\n"
                "last_activity_at: 2026-09-05T09:01:00+03:00\nrepo: regression-research\nscope: #559\nstate: RUN_FINISHED\n"
                "outcome: useful work\nmutation: none\nvalidation: PASS\nremaining_gate: none\n"
                "finding_tags: collision, resource_issue, proof_gap, convergence, product\nfindings: observed aliases\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, history)
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["finding_tags"], ["contention", "improvement", "other", "proof", "resource"])

    def test_unknown_finding_tag_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            current.mkdir(parents=True)
            run_id = "manual-unknown-tag"
            report = current / f"{run_id}.md"
            report.write_text(
                f"run_id: {run_id}\nstarted_at: 2026-09-05T09:00:00+03:00\n"
                "last_activity_at: 2026-09-05T09:01:00+03:00\nrepo: regression-research\nscope: #559\nstate: RUN_FINISHED\n"
                "outcome: useful work\nmutation: none\nvalidation: PASS\nremaining_gate: none\n"
                "finding_tags: definitely_not_a_real_tag\nfindings: invalid\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown finding_tags"):
                archive_finalized_report(report, root / "manual" / "history")

    def test_manual_metrics_and_events_dedupe_same_run_id_to_newest_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history_root = root / "manual" / "history"
            reports = history_root / "_reports"
            reports.mkdir(parents=True)
            now = datetime.now().astimezone()
            base = {
                "schema": "worker-report-history.v6",
                "population": "manual",
                "run_id": "manual-same-logical-run",
                "display_label": "Manual ChatGPT",
                "state": "RUN_FINISHED",
                "repo": "regression-research",
                "scope": "#559",
                "finished_at": (now - timedelta(minutes=2)).isoformat(),
            }
            older = {
                **base,
                "report_sha256": "aaa",
                "archived_at": (now - timedelta(minutes=1)).isoformat(),
                "duration_minutes": 3.0,
                "outcome": "stale correction target",
                "finding_tags": ["bug"],
            }
            newer = {
                **base,
                "report_sha256": "bbb",
                "archived_at": now.isoformat(),
                "duration_minutes": 7.0,
                "outcome": "corrected logical run",
                "finding_tags": ["improvement"],
            }
            (reports / "aaa.json").write_text(json.dumps(older), encoding="utf-8")
            (reports / "bbb.json").write_text(json.dumps(newer), encoding="utf-8")

            metrics = build_metrics_projection(history_root)
            self.assertEqual(metrics["reports"], 1)
            self.assertEqual(metrics["runs_with_duration"], 1)
            self.assertEqual(metrics["average_duration_minutes"], 7.0)
            self.assertEqual(metrics["finding_tag_counts"], {"improvement": 1})
            self.assertEqual(metrics["latest_reports"][0]["report_sha256"], "bbb")

            events = worker_history_events(history_root)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["id"], "worker:bbb")
            self.assertEqual(events[0]["outcome"], "corrected logical run")



if __name__ == "__main__":
    unittest.main()
