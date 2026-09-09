from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path

from tools.worker_report_history import _proof_artifact_fields, archive_finalized_report, audit_manual_current_reports, begin_timed_run, build_manual_sanity_projection, build_metrics_projection, build_parser, create_manual_run, reconcile_manual_current_reports, worker_history_events


class WorkerReportHistoryTests(unittest.TestCase):
    def test_manual_create_cli_is_registered(self):
        args = build_parser().parse_args([
            "create-manual", "--repo", "p3", "--stem", "same stem", "--run-mode", "continuation"
        ])
        self.assertEqual(args.command, "create-manual")
        self.assertEqual(args.repo, "p3")
        self.assertEqual(args.stem, "same stem")
        self.assertEqual(args.run_mode, "continuation")

    def test_manual_create_retries_same_exact_id_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "manual" / "current"
            fixed = datetime.fromisoformat("2026-09-07T04:18:39.635+03:00")
            with patch("tools.worker_report_history._manual_run_token", side_effect=("a" * 16, "a" * 16, "b" * 16)):
                first = create_manual_run(current, repo="p3", stem="p3-1068-converge", now=fixed)
                first_path = Path(first["report_path"])
                before = first_path.read_bytes()
                second = create_manual_run(current, repo="p3", stem="p3-1068-converge", now=fixed)
            self.assertNotEqual(first["run_id"], second["run_id"])
            self.assertEqual(first_path.read_bytes(), before)
            self.assertIn(b"start_evidence: CREATE_MANUAL_RUN", before)
            self.assertTrue(Path(second["report_path"]).exists())
            self.assertEqual(len(list(current.glob("*.md"))), 2)

    def test_manual_created_run_uses_observed_final_report_write_for_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            started = datetime.now().astimezone() - timedelta(minutes=10)
            created = create_manual_run(
                current, repo="regression-research", stem="duration-evidence", run_mode="continuation", now=started
            )
            report = Path(created["report_path"])
            text = report.read_text(encoding="utf-8")
            report.write_text(
                text.replace("state: RUNNING", "state: RUN_FINISHED").replace("outcome: in progress", "outcome: completed work"),
                encoding="utf-8",
            )
            observed_finish = started + timedelta(minutes=7, seconds=30)
            os.utime(report, (observed_finish.timestamp(), observed_finish.timestamp()))

            result = archive_finalized_report(report, history)
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            metrics = json.loads(Path(result["metrics_path"]).read_text(encoding="utf-8"))

            self.assertEqual(metadata["finished_at"], started.isoformat())
            self.assertEqual(metadata["reported_fields"]["last_activity_at"], started.isoformat())
            self.assertEqual(metadata["duration_minutes"], 7.5)
            self.assertEqual(metadata["duration_evidence"], "MACHINE_CREATED_START_TO_REPORT_FILE_MTIME")
            observed = datetime.fromisoformat(metadata["observed_finished_at"])
            self.assertLess(abs((observed - observed_finish).total_seconds()), 0.01)
            self.assertEqual(metrics["average_duration_minutes"], 7.5)

    def test_manual_same_stem_concurrent_creates_archive_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            fixed = datetime.now().astimezone()

            def create_one() -> dict[str, object]:
                return create_manual_run(
                    current,
                    repo="p3",
                    stem="p3-1068-converge",
                    scope="PR #1068 converged native respawn verification",
                    run_mode="continuation",
                    now=fixed,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                created = list(pool.map(lambda _: create_one(), range(2)))
            self.assertEqual(len({item["run_id"] for item in created}), 2)
            self.assertEqual(len(list(current.glob("*.md"))), 2)

            archive_paths = []
            for item in created:
                report = Path(str(item["report_path"]))
                text = report.read_text(encoding="utf-8")
                report.write_text(
                    text.replace("state: RUNNING", "state: RUN_FINISHED").replace("outcome: in progress", "outcome: useful work"),
                    encoding="utf-8",
                )
                result = archive_finalized_report(report, history)
                archive_paths.append(result["path"])
            self.assertEqual(len(set(archive_paths)), 2)
            self.assertFalse(any(Path(str(item["report_path"])).exists() for item in created))
            self.assertEqual(len(list((history / "_reports").glob("*.md"))), 2)

    def test_fresh_worker_contract_requires_canonical_manual_create_helper(self):
        contract = (Path(__file__).resolve().parents[1] / "04 Operating Contracts" / "fresh-worker-generation-launch.md").read_text(encoding="utf-8-sig")
        self.assertIn("worker_report_history.py create-manual", contract)
        self.assertIn("Do not handcraft manual run IDs or current report paths", contract)

    def test_manual_current_audit_never_treats_open_file_as_liveness(self):
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
                "state: TOOL_INTERVAL_OPEN\noutcome: in progress\nmutation: none\nvalidation: none\n"
                "remaining_gate: finish turn\nfinding_tags: proof\nfindings: current file alone is not liveness\n",
                encoding="utf-8",
            )
            audit = audit_manual_current_reports(current, history)
            self.assertEqual(audit["unfinalized_count"], 1)
            self.assertEqual(audit["reports"][0]["lifecycle_status"], "UNFINALIZED_OPEN")
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
            self.assertNotIn("manual-archived", by_id)
            self.assertNotIn("manual-unarchived", by_id)
            self.assertEqual(audit["unarchived_terminal_count"], 0)
            self.assertEqual(build_metrics_projection(history)["reports"], 2)


    def test_manual_current_audit_normalizes_legacy_running_to_open_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            run_id = "manual-legacy-running"
            (current / f"{run_id}.md").write_text(
                f"run_id: {run_id}\nstarted_at: 2026-09-05T10:00:00+00:00\n"
                "last_activity_at: 2026-09-05T10:10:00+00:00\nrepo: p3\nscope: legacy\n"
                "state: RUNNING\noutcome: legacy\nmutation: none\nvalidation: none\n"
                "remaining_gate: none\nfinding_tags: none\nfindings: legacy artifact\n",
                encoding="utf-8",
            )
            audit = audit_manual_current_reports(current, history)
            self.assertEqual(audit["reports"][0]["lifecycle_status"], "UNFINALIZED_OPEN")
            self.assertEqual(audit["reports"][0]["liveness"], "NOT_ESTABLISHED_BY_REPORT")

    def test_manual_reconcile_archives_old_terminal_and_keeps_recent_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            now = datetime.now().astimezone()
            old = now - timedelta(hours=1)
            terminal = current / "manual-terminal.md"
            terminal.write_text(
                f"run_id: manual-terminal\nstarted_at: {(old - timedelta(minutes=5)).isoformat()}\n"
                f"last_activity_at: {old.isoformat()}\nrepo: p3\nstate: RUN_FINISHED\noutcome: done\n",
                encoding="utf-8",
            )
            recent = current / "manual-recent.md"
            recent.write_text(
                f"run_id: manual-recent\nstarted_at: {now.isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\nrepo: p3\nstate: RUNNING\noutcome: active\n",
                encoding="utf-8",
            )
            result = reconcile_manual_current_reports(current, history, now=now)
            self.assertFalse(terminal.exists())
            self.assertTrue(recent.exists())
            self.assertEqual(result["action_count"], 1)
            self.assertEqual(result["actions"][0]["action"], "terminal_archived")
            self.assertEqual(build_metrics_projection(history)["reports"], 1)

    def test_manual_reconcile_preserves_stale_open_as_nonterminal_history_without_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            now = datetime.now().astimezone()
            old = now - timedelta(hours=7)
            report = current / "manual-stale.md"
            raw = (
                f"run_id: manual-stale\nstarted_at: {(old - timedelta(minutes=2)).isoformat()}\n"
                f"last_activity_at: {old.isoformat()}\nrepo: p3\nstate: TOOL_INTERVAL_OPEN\noutcome: interrupted\n"
            ).encode("utf-8")
            report.write_bytes(raw)
            result = reconcile_manual_current_reports(current, history, now=now)
            self.assertFalse(report.exists())
            self.assertEqual(result["actions"][0]["lifecycle_status"], "ABANDONED_OPEN")
            digest = result["actions"][0]["sha256"]
            archived = history / "_reports" / f"{digest}.md"
            metadata = json.loads((history / "_reports" / f"{digest}.json").read_text(encoding="utf-8"))
            self.assertEqual(archived.read_bytes(), raw)
            self.assertEqual(metadata["authority"], "NON_AUTHORITATIVE_REPORT_EVIDENCE")
            self.assertFalse(metadata["included_in_metrics"])
            self.assertEqual(metadata["lifecycle_status"], "ABANDONED_OPEN")
            self.assertEqual(build_metrics_projection(history)["reports"], 0)
            self.assertEqual(worker_history_events(history), [])

    def test_manual_reconcile_retires_invalid_legacy_snapshot_after_short_grace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            now = datetime.now().astimezone()
            old = now - timedelta(hours=2)
            report = current / "legacy-invalid.md"
            raw = (
                f"run_id: legacy-invalid\nstarted_at: {old.isoformat()}\n"
                f"last_activity_at: {old.isoformat()}\nstate: RUNNING\n"
            ).encode("utf-8")
            report.write_bytes(raw)
            result = reconcile_manual_current_reports(current, history, now=now)
            self.assertFalse(report.exists())
            self.assertEqual(result["actions"][0]["lifecycle_status"], "INVALID_CURRENT_SNAPSHOT")
            digest = result["actions"][0]["sha256"]
            self.assertEqual((history / "_reports" / f"{digest}.md").read_bytes(), raw)
            self.assertEqual(build_metrics_projection(history)["reports"], 0)

    def test_manual_archive_self_reconciles_old_current_debris(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            now = datetime.now().astimezone()
            old = now - timedelta(hours=7)
            stale = current / "manual-stale.md"
            stale.write_text(
                f"run_id: manual-stale\nstarted_at: {old.isoformat()}\nlast_activity_at: {old.isoformat()}\n"
                "repo: p3\nstate: RUNNING\noutcome: stale\n",
                encoding="utf-8",
            )
            fresh = current / "manual-fresh.md"
            fresh.write_text(
                f"run_id: manual-fresh\nstarted_at: {(now - timedelta(minutes=1)).isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\nrepo: p3\nstate: RUN_FINISHED\noutcome: done\n",
                encoding="utf-8",
            )
            archive_finalized_report(fresh, history)
            self.assertFalse(fresh.exists())
            self.assertFalse(stale.exists())
            metadata = list((history / "_reports").glob("*.json"))
            self.assertEqual(len(metadata), 2)
            lifecycle = {json.loads(path.read_text(encoding="utf-8"))["run_id"]: json.loads(path.read_text(encoding="utf-8")).get("lifecycle_status") for path in metadata}
            self.assertIsNone(lifecycle["manual-fresh"])
            self.assertEqual(lifecycle["manual-stale"], "ABANDONED_OPEN")
            self.assertEqual(build_metrics_projection(history)["reports"], 1)

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
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["authority"], "NON_AUTHORITATIVE_REPORT_EVIDENCE")

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

    def test_proof_index_aliases_are_normalized_into_history_navigation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "ProofRun.md"
            report.write_text(
                "worker: ProofRun\nstate: COMPLETE\noutcome: captures produced\n"
                "repo: organicoverlords/p3\nscope: p3#331\n"
                "proof_index: C:/proofs/capture-index.json\n"
                "proof_index_sha256: 71c5e7d9d75fde7ed857c052b0a05373615be3e296ef2db96157aa716513397f\n"
                "visual_proof_claim: PENDING_REVIEW\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, root / "history")
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["proof_artifact"], "C:/proofs/capture-index.json")
            self.assertEqual(
                metadata["proof_artifact_sha256"],
                "71c5e7d9d75fde7ed857c052b0a05373615be3e296ef2db96157aa716513397f",
            )
            self.assertEqual(metadata["visual_proof_claim"], "PENDING_REVIEW")
            event = worker_history_events(root / "history")[0]
            self.assertEqual(event["proof_artifact"], "C:/proofs/capture-index.json")
            self.assertEqual(event["proof_artifact_sha256"], metadata["proof_artifact_sha256"])
            self.assertIn("C:/proofs/capture-index.json", event["refs"])
            self.assertNotIn("visual_proof_pass", event)

    def test_video_manifest_alias_is_normalized_without_inventing_review_or_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = root / "Ash.md"
            legacy_manifest = r'"C:\P3Proofs\20260904-054340-video\manifest.json"'
            legacy_runtime = r'"C:\proof-worktree\visual-polish-runtime.mp4"'
            report.write_text(
                "worker: Repo Worker Ash\nstate: COMPLETE\noutcome: playable MP4 PROVEN; review pending\n"
                "repo: organicoverlords/p3\nscope: p3#803\n"
                f"video_manifest: {legacy_manifest}\n"
                f"runtime_proof: {legacy_runtime}\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, root / "history")
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            expected = r"C:\P3Proofs\20260904-054340-video\manifest.json"
            self.assertEqual(metadata["proof_artifact"], expected)
            self.assertIsNone(metadata["proof_artifact_sha256"])
            self.assertIsNone(metadata["visual_proof_run"])
            self.assertIsNone(metadata["visual_proof_review"])
            event = worker_history_events(root / "history")[0]
            self.assertEqual(event["proof_artifact"], expected)
            self.assertIsNone(event["proof_artifact_sha256"])
            self.assertIn(expected, event["refs"])
            self.assertNotIn("visual_proof_pass", event)

    def test_proof_artifact_precedence_over_proof_index_and_video_manifest(self):
        fields = {
            "proof_artifact": "C:/proofs/canonical.json",
            "proof_index": "C:/proofs/index.json",
            "video_manifest": '"C:\\\\P3Proofs\\\\run\\\\manifest.json"',
            "proof_artifact_sha256": "a" * 64,
            "proof_index_sha256": "b" * 64,
        }
        self.assertEqual(
            _proof_artifact_fields(fields),
            ("C:/proofs/canonical.json", "a" * 64),
        )

    def test_existing_v6_metadata_normalizes_video_manifest_from_reported_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history" / "_reports"
            history.mkdir(parents=True)
            payload = {
                "schema": "worker-report-history.v6",
                "report_sha256": "legacy-video-manifest",
                "worker": "Repo Worker Ash",
                "state": "COMPLETE",
                "outcome": "playable MP4 PROVEN; review pending",
                "repo": "organicoverlords/p3",
                "scope": "p3#803",
                "finished_at": "2026-09-04T05:44:52+00:00",
                "archived_at": "2026-09-04T05:45:00+00:00",
                "reported_fields": {
                    "video_manifest": '"C:\\\\P3Proofs\\\\20260904-054340-video\\\\manifest.json"',
                    "runtime_proof": '"C:\\\\proof-worktree\\\\visual-polish-runtime.mp4"',
                },
                "visual_proof_run": None,
                "visual_proof_review": None,
            }
            (history / "legacy-video-manifest.json").write_text(json.dumps(payload), encoding="utf-8")
            events = worker_history_events(root / "history")
            self.assertEqual(len(events), 1)
            expected = r"C:\P3Proofs\20260904-054340-video\manifest.json"
            self.assertEqual(events[0]["proof_artifact"], expected)
            self.assertIsNone(events[0]["proof_artifact_sha256"])
            self.assertIn(expected, events[0]["refs"])
            self.assertIsNone(events[0]["visual_proof_run"])
            self.assertIsNone(events[0]["visual_proof_review"])

    def test_existing_v6_metadata_normalizes_proof_index_from_reported_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history" / "_reports"
            history.mkdir(parents=True)
            payload = {
                "schema": "worker-report-history.v6",
                "population": "manual",
                "report_sha256": "legacy-proof",
                "run_id": "manual-proof-run",
                "display_label": "Proof run",
                "state": "RUN_FINISHED",
                "outcome": "12/12 captures produced; PENDING_REVIEW",
                "repo": "organicoverlords/p3",
                "scope": "p3#331",
                "finished_at": "2026-09-05T10:40:00+03:00",
                "archived_at": "2026-09-05T10:41:00+03:00",
                "reported_fields": {
                    "proof_index": "C:/proofs/capture-index.json",
                    "proof_index_sha256": "71c5e7d9d75fde7ed857c052b0a05373615be3e296ef2db96157aa716513397f",
                    "visual_proof_claim": "PENDING_REVIEW",
                },
            }
            (history / "legacy-proof.json").write_text(json.dumps(payload), encoding="utf-8")
            events = worker_history_events(root / "manual" / "history")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["proof_artifact"], "C:/proofs/capture-index.json")
            self.assertEqual(
                events[0]["proof_artifact_sha256"],
                "71c5e7d9d75fde7ed857c052b0a05373615be3e296ef2db96157aa716513397f",
            )
            self.assertIn("C:/proofs/capture-index.json", events[0]["refs"])

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

    def test_thin_manual_report_archives_without_execution_transcript_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "manual" / "current"
            history = root / "manual" / "history"
            current.mkdir(parents=True)
            run_id = "manual-thin-report"
            report = current / f"{run_id}.md"
            report.write_text(
                f"run_id: {run_id}\n"
                "started_at: 2026-09-05T10:00:00+00:00\n"
                "last_activity_at: 2026-09-05T10:05:00+00:00\n"
                "repo: p3\nstate: RUN_FINISHED\noutcome: useful work\n",
                encoding="utf-8",
            )
            result = archive_finalized_report(report, history)
            metadata = json.loads(Path(result["metadata_path"]).read_text(encoding="utf-8"))
            self.assertEqual(metadata["population"], "manual")
            self.assertEqual(metadata["duration_minutes"], 5.0)
            self.assertIsNone(metadata["mutation"])
            self.assertIsNone(metadata["validation"])
            self.assertIsNone(metadata["remaining_gate"])

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

    def test_timed_run_begin_normalizes_known_legacy_start_preamble(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "9" * 32
            now = datetime.now().astimezone()
            report = current / f"{automation_id}.md"
            report.write_text(
                "worker: Repo Worker Alder\n"
                f"automation_id: {automation_id}\n"
                f"started_at: {now.isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\n"
                "state: RUNNING\n"
                "finding_tags: []\n"
                "findings: []\n"
                "commits: []\n"
                "diffs: []\n"
                "tests: []\n"
                "failures: []\n"
                "anomalies: []\n"
                "route_problems: []\n"
                "resource_issues: []\n"
                "proof_gaps: []\n"
                "improvements: []\n",
                encoding="utf-8",
            )
            result = begin_timed_run(report)
            text = report.read_text(encoding="utf-8")
            receipt_exists = Path(result["receipt_path"]).exists()

        self.assertTrue(receipt_exists)
        self.assertIn("repo: startup-unresolved", text)
        self.assertIn("scope: startup scope selection pending", text)
        self.assertIn("outcome: in progress", text)
        self.assertIn("mutation: none yet", text)
        self.assertIn("validation: none yet", text)
        self.assertIn("remaining_gate: scope selection and execution pending", text)
        self.assertIn("finding_tags: none", text)
        self.assertIn("findings: none", text)
        self.assertIn("startup_schema_normalized: legacy_minimal_v1", text)

    def test_timed_run_begin_still_rejects_arbitrary_incomplete_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "7" * 32
            now = datetime.now().astimezone()
            report = current / f"{automation_id}.md"
            report.write_text(
                f"automation_id: {automation_id}\n"
                f"started_at: {now.isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\n"
                "state: RUNNING\n"
                "worker: Unknown\n"
                "commits: []\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing required canonical field"):
                begin_timed_run(report)
            self.assertFalse((root / ".supervision" / f"{automation_id}.start.json").exists())

    def test_timed_run_begin_rejects_partial_legacy_lookalike(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            current.mkdir()
            automation_id = "6" * 32
            now = datetime.now().astimezone()
            report = current / f"{automation_id}.md"
            report.write_text(
                "worker: Repo Worker Lookalike\n"
                f"automation_id: {automation_id}\n"
                f"started_at: {now.isoformat()}\n"
                f"last_activity_at: {now.isoformat()}\n"
                "state: RUNNING\n"
                "finding_tags: []\n"
                "findings: []\n"
                "commits: []\n"
                "diffs: []\n"
                "tests: []\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing required canonical field"):
                begin_timed_run(report)
            self.assertFalse((root / ".supervision" / f"{automation_id}.start.json").exists())

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
            self.assertFalse(report.exists())
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


    def test_manual_event_dedupe_tolerates_missing_archived_at_on_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history_root = root / "manual" / "history"
            reports = history_root / "_reports"
            reports.mkdir(parents=True)
            now = datetime.now().astimezone()
            base = {
                "schema": "worker-report-history.v6",
                "population": "manual",
                "run_id": "manual-missing-archived-at",
                "display_label": "Manual ChatGPT",
                "state": "RUN_FINISHED",
                "repo": "regression-research",
                "scope": "#569",
                "finished_at": (now - timedelta(minutes=2)).isoformat(),
            }
            malformed = {
                **base,
                "report_sha256": "aaa",
                "duration_minutes": 2.0,
                "outcome": "older malformed metadata",
            }
            valid = {
                **base,
                "report_sha256": "bbb",
                "archived_at": now.isoformat(),
                "duration_minutes": 3.0,
                "outcome": "newest valid metadata",
            }
            (reports / "aaa.json").write_text(json.dumps(malformed), encoding="utf-8")
            (reports / "bbb.json").write_text(json.dumps(valid), encoding="utf-8")

            events = worker_history_events(history_root)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["id"], "worker:bbb")
            self.assertEqual(events[0]["outcome"], "newest valid metadata")



    def test_timed_metrics_exclude_terminal_archives_without_machine_start_from_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history_root = root / "history"
            reports = history_root / "_reports"
            reports.mkdir(parents=True)
            now = datetime.now().astimezone()
            measured = {
                "schema": "worker-report-history.v6", "population": "timed", "report_sha256": "measured",
                "automation_id": "a" * 32, "display_label": "Measured", "state": "RUN_FINISHED",
                "observed_started_at": (now - timedelta(minutes=21)).isoformat(),
                "started_at": (now - timedelta(minutes=21)).isoformat(),
                "finished_at": (now - timedelta(minutes=1)).isoformat(), "archived_at": now.isoformat(),
                "duration_minutes": 20.0, "target_utilization_pct": 83.3, "finding_tags": ["proof"],
            }
            blocked = {
                "schema": "worker-report-history.v6", "population": "timed", "report_sha256": "blocked",
                "automation_id": "b" * 32, "display_label": "Blocked", "state": "BLOCKED",
                "started_at": (now - timedelta(minutes=2)).isoformat(),
                "finished_at": (now - timedelta(minutes=2)).isoformat(), "archived_at": now.isoformat(),
                "duration_minutes": 0.0, "target_utilization_pct": 0.0, "finding_tags": ["bug"],
            }
            (reports / "measured.json").write_text(json.dumps(measured), encoding="utf-8")
            (reports / "blocked.json").write_text(json.dumps(blocked), encoding="utf-8")

            metrics = build_metrics_projection(history_root)
            self.assertEqual(metrics["reports"], 2)
            self.assertEqual(metrics["runs_with_duration"], 1)
            self.assertEqual(metrics["min_duration_minutes"], 20.0)
            self.assertEqual(metrics["average_target_utilization_pct"], 83.3)
            self.assertEqual(metrics["finding_tag_counts"], {"bug": 1, "proof": 1})
            self.assertEqual(metrics["duration_filter"]["excluded_unmeasured_count"], 1)
            by_sha = {row["report_sha256"]: row for row in metrics["latest_reports"]}
            self.assertEqual(by_sha["measured"]["timing_evidence"], "MACHINE_OBSERVED_START")
            self.assertEqual(by_sha["measured"]["duration_minutes"], 20.0)
            self.assertEqual(by_sha["blocked"]["timing_evidence"], "UNMEASURED_NO_MACHINE_START")
            self.assertIsNone(by_sha["blocked"]["duration_minutes"])
            self.assertNotIn("target_utilization_pct", by_sha["blocked"])

    def test_manual_metrics_filter_three_hour_duration_outliers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history_root = root / "manual" / "history"
            reports = history_root / "_reports"
            reports.mkdir(parents=True)
            now = datetime.now().astimezone()
            for index, duration in enumerate((10.0, 180.0, 240.0)):
                started = now - timedelta(minutes=duration + 1)
                item = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": f"d{index}",
                    "run_id": f"duration-{index}", "state": "RUN_FINISHED", "repo": "vault",
                    "started_at": started.isoformat(), "finished_at": (now - timedelta(minutes=1)).isoformat(),
                    "archived_at": now.isoformat(), "duration_minutes": duration,
                }
                (reports / f"d{index}.json").write_text(json.dumps(item), encoding="utf-8")

            metrics = build_metrics_projection(history_root)
            self.assertEqual(metrics["reports"], 3)
            self.assertEqual(metrics["runs_with_duration"], 1)
            self.assertEqual(metrics["total_duration_minutes"], 10.0)
            self.assertEqual(metrics["average_duration_minutes"], 10.0)
            self.assertEqual(metrics["max_duration_minutes"], 10.0)
            self.assertEqual(metrics["duration_filter"]["exclude_at_or_above_minutes"], 180.0)
            self.assertEqual(metrics["duration_filter"]["excluded_count"], 2)

    def test_manual_sanity_since_boundary_sample_does_not_roll_back_to_insufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v2",
                "baseline_id": "persistent-sample",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "comparison_window_mode": "since_boundary",
                "metrics": {
                    "median_report_bytes": 1000.0, "mean_transcript_fields": 4.0,
                    "self_reported_lifecycle_anomaly_pct": 20.0,
                },
                "axes": {
                    "friction": {"metrics": {"median_report_bytes": 50.0, "mean_transcript_fields": 50.0}},
                    "operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 100.0}},
                },
                "sample_gates": {"minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20},
                "score_semantics": {"direction_threshold": 10.0},
            }), encoding="utf-8")
            for index in range(5):
                archive = reports / f"persist{index}.md"
                archive.write_text(f"run_id: persist{index}\nstate: RUN_FINISHED\noutcome: useful work\n", encoding="utf-8")
                meta = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": f"persist{index}",
                    "run_id": f"persist{index}", "started_at": f"2026-09-06T21:{10+index:02d}:00+03:00",
                    "finished_at": f"2026-09-06T21:{15+index:02d}:00+03:00", "duration_minutes": 5.0,
                    "archived_at": f"2026-09-06T21:{16+index:02d}:00+03:00", "archive_path": str(archive),
                    "reported_fields": {"run_id": f"persist{index}", "outcome": "useful work"}, "outcome": "useful work",
                }
                (reports / f"persist{index}.json").write_text(json.dumps(meta), encoding="utf-8")

            projected = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-07T08:00:00+03:00")
            )
            self.assertEqual(projected["comparison_window_mode"], "since_boundary")
            self.assertEqual(projected["post_run_count"], 5)
            self.assertEqual(projected["status"], "PROVISIONAL")

    def test_manual_sanity_requires_post_boundary_sample_and_then_scores_improvement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v2",
                "baseline_id": "test-baseline",
                "label": "test",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "metrics": {
                    "median_report_bytes": 1000.0,
                    "mean_transcript_fields": 4.0,
                    "self_reported_lifecycle_anomaly_pct": 20.0,
                    "micro_run_lt2_pct": 20.0,
                    "short_run_lt5_pct_guardrail": 30.0,
                    "median_tool_interval_minutes_guardrail": 8.0,
                },
                "axes": {
                    "friction": {"metrics": {"median_report_bytes": 50.0, "mean_transcript_fields": 50.0}},
                    "operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 100.0}},
                },
                "sample_gates": {"minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20},
                "score_semantics": {"direction_threshold": 10.0},
            }), encoding="utf-8")
            now = datetime.fromisoformat("2026-09-06T22:00:00+03:00")
            empty = build_manual_sanity_projection(history, baseline_path=baseline_path, now=now)
            self.assertEqual(empty["status"], "INSUFFICIENT_DATA")
            self.assertIsNone(empty["score_delta"])
            self.assertIsNone(empty["axes"]["friction"]["score_delta"])
            self.assertIsNone(empty["descriptive_delta"])
            for index in range(5):
                archive = reports / f"r{index}.md"
                archive.write_text(
                    f"run_id: r{index}\nstarted_at: 2026-09-06T21:{10+index:02d}:00+03:00\n"
                    f"last_activity_at: 2026-09-06T21:{15+index:02d}:00+03:00\nrepo: vault\n"
                    "state: RUN_FINISHED\noutcome: useful work\n",
                    encoding="utf-8",
                )
                meta = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": f"r{index}",
                    "run_id": f"r{index}", "started_at": f"2026-09-06T21:{10+index:02d}:00+03:00",
                    "finished_at": f"2026-09-06T21:{15+index:02d}:00+03:00", "duration_minutes": 5.0,
                    "archived_at": f"2026-09-06T21:{16+index:02d}:00+03:00", "archive_path": str(archive),
                    "reported_fields": {"run_id": f"r{index}", "outcome": "useful work"},
                    "outcome": "useful work",
                }
                (reports / f"r{index}.json").write_text(json.dumps(meta), encoding="utf-8")
            scored = build_manual_sanity_projection(history, baseline_path=baseline_path, now=now)
            self.assertEqual(scored["status"], "PROVISIONAL")
            self.assertEqual(scored["post_run_count"], 5)
            self.assertGreater(scored["score_delta"], 10.0)
            self.assertEqual(scored["direction"], "IMPROVED")
            self.assertEqual(scored["score_delta"], min(scored["axes"]["friction"]["score_delta"], scored["axes"]["operational"]["score_delta"]))
            self.assertEqual(scored["observation"]["mean_transcript_fields"], 0.0)
            self.assertEqual(scored["guardrails"]["short_run_lt5_pct"]["status"], "NOT_REGRESSED")


    def test_manual_sanity_friction_cannot_mask_operational_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v2",
                "baseline_id": "anti-gaming",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "metrics": {
                    "median_report_bytes": 1000.0, "mean_transcript_fields": 4.0,
                    "self_reported_lifecycle_anomaly_pct": 20.0, "micro_run_lt2_pct": 20.0,
                    "short_run_lt5_pct_guardrail": 30.0, "median_tool_interval_minutes_guardrail": 8.0,
                },
                "axes": {
                    "friction": {"metrics": {"median_report_bytes": 50.0, "mean_transcript_fields": 50.0}},
                    "operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 60.0, "micro_run_lt2_pct": 40.0}},
                },
                "sample_gates": {"minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20},
                "score_semantics": {"direction_threshold": 10.0},
            }), encoding="utf-8")
            for index in range(5):
                archive = reports / f"bad{index}.md"
                archive.write_text(
                    f"run_id: bad{index}\nstarted_at: 2026-09-06T21:{10+index:02d}:00+03:00\n"
                    f"last_activity_at: 2026-09-06T21:{11+index:02d}:00+03:00\nrepo: vault\n"
                    "state: RUN_FINISHED\noutcome: report opened late after tool work\n",
                    encoding="utf-8",
                )
                meta = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": f"bad{index}",
                    "run_id": f"bad{index}", "started_at": f"2026-09-06T21:{10+index:02d}:00+03:00",
                    "finished_at": f"2026-09-06T21:{11+index:02d}:00+03:00", "duration_minutes": 1.0,
                    "archived_at": f"2026-09-06T21:{12+index:02d}:00+03:00", "archive_path": str(archive),
                    "reported_fields": {"run_id": f"bad{index}", "outcome": "report opened late after tool work"},
                    "outcome": "report opened late after tool work",
                }
                (reports / f"bad{index}.json").write_text(json.dumps(meta), encoding="utf-8")
            scored = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-06T22:00:00+03:00")
            )
            self.assertGreater(scored["axes"]["friction"]["score_delta"], 0.0)
            self.assertLess(scored["axes"]["operational"]["score_delta"], 0.0)
            self.assertEqual(scored["score_delta"], scored["axes"]["operational"]["score_delta"])
            self.assertEqual(scored["direction"], "WORSE")
            self.assertEqual(scored["guardrails"]["short_run_lt5_pct"]["status"], "REGRESSED")


    def test_manual_sanity_regressed_guardrail_blocks_clean_improved_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v2",
                "baseline_id": "guardrail-veto",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "metrics": {
                    "median_report_bytes": 1000.0, "mean_transcript_fields": 4.0,
                    "self_reported_lifecycle_anomaly_pct": 20.0, "micro_run_lt2_pct": 20.0,
                    "short_run_lt5_pct_guardrail": 20.0, "median_tool_interval_minutes_guardrail": 8.0,
                },
                "axes": {
                    "friction": {"metrics": {"median_report_bytes": 50.0, "mean_transcript_fields": 50.0}},
                    "operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 60.0, "micro_run_lt2_pct": 40.0}},
                },
                "sample_gates": {"minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20},
                "score_semantics": {"direction_threshold": 10.0},
            }), encoding="utf-8")
            for index in range(5):
                archive = reports / f"short{index}.md"
                archive.write_text(
                    f"run_id: short{index}\nstarted_at: 2026-09-06T21:{10+index:02d}:00+03:00\n"
                    f"last_activity_at: 2026-09-06T21:{13+index:02d}:00+03:00\nrepo: vault\n"
                    "state: RUN_FINISHED\noutcome: useful work\n", encoding="utf-8",
                )
                meta = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": f"short{index}",
                    "run_id": f"short{index}", "started_at": f"2026-09-06T21:{10+index:02d}:00+03:00",
                    "finished_at": f"2026-09-06T21:{13+index:02d}:00+03:00", "duration_minutes": 3.0,
                    "archived_at": f"2026-09-06T21:{14+index:02d}:00+03:00", "archive_path": str(archive),
                    "reported_fields": {"run_id": f"short{index}", "outcome": "useful work"}, "outcome": "useful work",
                }
                (reports / f"short{index}.json").write_text(json.dumps(meta), encoding="utf-8")
            scored = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-06T22:00:00+03:00")
            )
            self.assertGreater(scored["score_delta"], 10.0)
            self.assertEqual(scored["guardrails"]["short_run_lt5_pct"]["status"], "REGRESSED")
            self.assertEqual(scored["direction"], "MIXED_GUARDRAIL_REGRESSION")



    def test_manual_sanity_behavior_headline_ignores_report_verbosity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v3",
                "baseline_id": "behavior-headline",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "metrics": {
                    "median_report_bytes": 100.0,
                    "mean_transcript_fields": 1.0,
                    "self_reported_lifecycle_anomaly_pct": 20.0,
                },
                "headline_axes": ["operational"],
                "axes": {
                    "operational": {
                        "scored": True,
                        "metrics": {"self_reported_lifecycle_anomaly_pct": 100.0},
                    },
                    "reporting": {
                        "scored": False,
                        "metrics": {"median_report_bytes": 50.0, "mean_transcript_fields": 50.0},
                    },
                },
                "sample_gates": {"minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20},
                "score_semantics": {"direction_threshold": 10.0},
            }), encoding="utf-8")
            for index in range(5):
                archive = reports / f"verbose{index}.md"
                archive.write_text(
                    f"run_id: verbose{index}\nstate: RUN_FINISHED\noutcome: useful work\n" + ("detail " * 200),
                    encoding="utf-8",
                )
                fields = {"scope": "x", "mutation": "x", "validation": "x", "remaining_gate": "x"}
                fields.update({"run_id": f"verbose{index}", "outcome": "useful work"})
                meta = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": f"verbose{index}",
                    "run_id": f"verbose{index}", "started_at": f"2026-09-06T21:{10+index:02d}:00+03:00",
                    "finished_at": f"2026-09-06T21:{15+index:02d}:00+03:00", "duration_minutes": 5.0,
                    "archived_at": f"2026-09-06T21:{16+index:02d}:00+03:00", "archive_path": str(archive),
                    "reported_fields": fields, "outcome": "useful work",
                    "report_bytes": 5000, "manual_transcript_field_count": 14,
                }
                (reports / f"verbose{index}.json").write_text(json.dumps(meta), encoding="utf-8")

            scored = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-06T22:00:00+03:00")
            )
            self.assertEqual(scored["headline_axes"], ["operational"])
            self.assertEqual(scored["diagnostic_axes"], ["reporting"])
            self.assertEqual(scored["score_delta"], 100.0)
            self.assertEqual(scored["axes"]["operational"]["score_delta"], 100.0)
            self.assertFalse(scored["axes"]["reporting"]["scored"])
            self.assertIsNone(scored["axes"]["reporting"]["score_delta"])
            self.assertLess(scored["axes"]["reporting"]["descriptive_delta"], 0.0)
            self.assertEqual(scored["direction"], "IMPROVED")

    def test_manual_sanity_behavior_headline_penalizes_lifecycle_mistakes_even_with_short_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v3",
                "baseline_id": "behavior-headline-regression",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "metrics": {
                    "median_report_bytes": 1000.0,
                    "mean_transcript_fields": 5.0,
                    "self_reported_lifecycle_anomaly_pct": 20.0,
                },
                "headline_axes": ["operational"],
                "axes": {
                    "operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 100.0}},
                    "reporting": {
                        "scored": False,
                        "metrics": {"median_report_bytes": 50.0, "mean_transcript_fields": 50.0},
                    },
                },
                "sample_gates": {"minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20},
                "score_semantics": {"direction_threshold": 10.0},
            }), encoding="utf-8")
            for index in range(5):
                archive = reports / f"badshort{index}.md"
                archive.write_text(
                    f"run_id: badshort{index}\nstate: RUN_FINISHED\noutcome: report opened late after tool work\n",
                    encoding="utf-8",
                )
                meta = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": f"badshort{index}",
                    "run_id": f"badshort{index}", "started_at": f"2026-09-06T21:{10+index:02d}:00+03:00",
                    "finished_at": f"2026-09-06T21:{15+index:02d}:00+03:00", "duration_minutes": 5.0,
                    "archived_at": f"2026-09-06T21:{16+index:02d}:00+03:00", "archive_path": str(archive),
                    "reported_fields": {"run_id": f"badshort{index}", "outcome": "report opened late after tool work"},
                    "outcome": "report opened late after tool work",
                    "report_bytes": 50, "manual_transcript_field_count": 1,
                }
                (reports / f"badshort{index}.json").write_text(json.dumps(meta), encoding="utf-8")

            scored = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-06T22:00:00+03:00")
            )
            self.assertEqual(scored["score_delta"], -100.0)
            self.assertEqual(scored["direction"], "WORSE")
            self.assertGreater(scored["axes"]["reporting"]["descriptive_delta"], 0.0)


    def test_manual_sanity_machine_lifecycle_is_matured_unscored_completeness_diagnostic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v3",
                "baseline_id": "machine-lifecycle-diagnostic",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "comparison_window_mode": "since_boundary",
                "metrics": {"self_reported_lifecycle_anomaly_pct": 20.0},
                "headline_axes": ["operational"],
                "axes": {"operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 100.0}}},
                "sample_gates": {"minimum_post_runs_for_provisional": 1, "minimum_post_runs_for_comparable": 2},
                "score_semantics": {"direction_threshold": 10.0},
                "machine_lifecycle_diagnostic": {
                    "instrumented_at": "2026-09-07T04:00:00+03:00",
                    "maturity_lag_hours": 6.0,
                    "recent_window_hours": 24.0,
                    "minimum_runs_for_comparable": 2,
                    "scored": False,
                },
            }), encoding="utf-8")

            def write_record(name, started, *, lifecycle=None, outcome="useful work"):
                payload = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": name,
                    "run_id": name, "started_at": started, "archived_at": "2026-09-08T12:00:00+03:00",
                    "state": "RUNNING" if lifecycle else "RUN_FINISHED", "outcome": outcome,
                    "reported_fields": {"run_id": name, "outcome": outcome},
                    "report_bytes": 100, "manual_transcript_field_count": 1,
                }
                if lifecycle:
                    payload.update({"lifecycle_status": lifecycle, "included_in_metrics": False})
                (reports / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")

            # Retrospective pre-boundary reference: visible but explicitly non-comparable.
            write_record("pre-terminal", "2026-09-06T18:00:00+03:00")
            write_record("pre-abandoned", "2026-09-06T19:00:00+03:00", lifecycle="ABANDONED_OPEN")
            # Mature prospective records: one terminal, one censored conversation, and one invalid observation.
            write_record("post-terminal", "2026-09-07T06:00:00+03:00")
            write_record("post-abandoned", "2026-09-07T07:00:00+03:00", lifecycle="ABANDONED_OPEN")
            write_record("post-invalid", "2026-09-07T08:00:00+03:00", lifecycle="INVALID_CURRENT_SNAPSHOT")
            # Too recent at now=12:00 with a six-hour maturity lag; excluded from failure denominator.
            write_record("too-recent-open", "2026-09-08T10:00:00+03:00", lifecycle="ABANDONED_OPEN")

            scored = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-08T12:00:00+03:00")
            )
            diagnostic = scored["machine_lifecycle"]
            self.assertFalse(diagnostic["scored"])
            self.assertEqual(diagnostic["reference_pre_boundary"]["coverage"], "RETROSPECTIVE_SURVIVOR_BIASED")
            self.assertFalse(diagnostic["reference_pre_boundary"]["comparable_baseline"])
            self.assertEqual(diagnostic["since_instrumentation"]["run_count"], 3)
            self.assertEqual(diagnostic["since_instrumentation"]["terminal_count"], 1)
            self.assertEqual(diagnostic["since_instrumentation"]["censored_count"], 1)
            self.assertEqual(diagnostic["since_instrumentation"]["invalid_observation_count"], 1)
            self.assertEqual(diagnostic["since_instrumentation"]["terminalized_pct"], 33.33)
            self.assertEqual(diagnostic["since_instrumentation"]["censored_pct"], 33.33)
            self.assertEqual(diagnostic["since_instrumentation"]["invalid_observation_pct"], 33.33)
            self.assertNotIn("terminalization_failure_pct", diagnostic["since_instrumentation"])
            self.assertEqual(diagnostic["since_instrumentation"]["excluded_too_recent_count"], 1)
            self.assertFalse(diagnostic["headline_population_relationship"]["directly_comparable"])
            # Headline still scores only terminalized revision-3 records; diagnostic cannot move it.
            self.assertEqual(scored["score_delta"], 100.0)

    def test_manual_sanity_abandoned_open_is_censored_not_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v3",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "comparison_window_mode": "since_boundary",
                "metrics": {"self_reported_lifecycle_anomaly_pct": 20.0},
                "headline_axes": ["operational"],
                "axes": {"operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 100.0}}},
                "sample_gates": {"minimum_post_runs_for_provisional": 1, "minimum_post_runs_for_comparable": 1},
                "score_semantics": {"direction_threshold": 10.0},
                "machine_lifecycle_diagnostic": {
                    "instrumented_at": "2026-09-07T04:00:00+03:00",
                    "maturity_lag_hours": 6.0,
                    "recent_window_hours": 24.0,
                    "minimum_runs_for_comparable": 1,
                    "scored": False,
                },
            }), encoding="utf-8")
            payload = {
                "schema": "worker-report-history.v1", "population": "manual", "run_id": "censored",
                "started_at": "2026-09-07T05:00:00+03:00", "archived_at": "2026-09-07T12:00:00+03:00",
                "state": "RUNNING", "outcome": "in progress", "lifecycle_status": "ABANDONED_OPEN",
                "included_in_metrics": False,
            }
            (reports / "censored.json").write_text(json.dumps(payload), encoding="utf-8")
            result = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-08T12:00:00+03:00")
            )["machine_lifecycle"]["since_instrumentation"]
            self.assertEqual(result["censored_count"], 1)
            self.assertEqual(result["censored_pct"], 100.0)
            self.assertEqual(result["terminal_count"], 0)
            self.assertEqual(result["invalid_observation_count"], 0)
            self.assertNotIn("nonterminal_failure_count", result)
            self.assertNotIn("terminalization_success_pct", result)
            self.assertNotIn("terminalization_failure_pct", result)

    def test_manual_sanity_can_demote_report_score_when_truth_authority_is_external(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v3",
                "baseline_id": "legacy-report-baseline",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "comparison_window_mode": "since_boundary",
                "metrics": {"self_reported_lifecycle_anomaly_pct": 20.0},
                "headline_axes": ["operational"],
                "axes": {"operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 100.0}}},
                "sample_gates": {"minimum_post_runs_for_provisional": 1, "minimum_post_runs_for_comparable": 1},
                "score_semantics": {"direction_threshold": 10.0},
                "headline_eligible": False,
                "score_role": "LEGACY_REPORT_DIAGNOSTIC_ONLY",
            }), encoding="utf-8")
            payload = {
                "schema": "worker-report-history.v4",
                "population": "manual",
                "run_id": "post-terminal",
                "started_at": "2026-09-07T06:00:00+03:00",
                "archived_at": "2026-09-07T06:05:00+03:00",
                "reported_fields": {"scope": "clean run", "mutation": "none", "validation": "ok", "remaining_gate": "none"},
                "report_bytes": 100,
                "manual_transcript_field_count": 4,
            }
            (reports / "post-terminal.json").write_text(json.dumps(payload), encoding="utf-8")

            result = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-07T12:00:00+03:00")
            )
            self.assertFalse(result["headline_eligible"])
            self.assertIsNone(result["score_delta"])
            self.assertIsNone(result["descriptive_delta"])
            self.assertEqual(result["direction"], "UNAVAILABLE_TRUTH_SCORE")
            self.assertEqual(result["truth_score_status"], "UNAVAILABLE_MCP_GITHUB_EVAL_NOT_CALIBRATED")
            self.assertEqual(result["legacy_report_score_delta"], 100.0)
            self.assertEqual(result["legacy_report_direction"], "IMPROVED")
            self.assertEqual(result["authority"]["worker_reports"], "AUXILIARY_METADATA_ONLY")
            self.assertEqual(result["authority"]["execution"], "MCP_DURABLE_PROCESS_RUNTIME_RECEIPTS")

    def test_continuation_projection_excludes_bounded_task_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "manual" / "history"
            reports = history / "_reports"
            reports.mkdir(parents=True)
            baseline_path = root / "baseline.json"
            baseline_path.write_text(json.dumps({
                "schema": "manual-worker-sanity-baseline.v2",
                "baseline_id": "continuation-separation",
                "boundary_at": "2026-09-06T21:00:00+03:00",
                "comparison_window_hours": 6.0,
                "metrics": {
                    "median_report_bytes": 1000.0, "mean_transcript_fields": 4.0,
                    "self_reported_lifecycle_anomaly_pct": 20.0, "micro_run_lt2_pct": 20.0,
                    "short_run_lt5_pct_guardrail": 20.0, "median_tool_interval_minutes_guardrail": 8.0,
                },
                "axes": {
                    "friction": {"metrics": {"median_report_bytes": 50.0, "mean_transcript_fields": 50.0}},
                    "operational": {"metrics": {"self_reported_lifecycle_anomaly_pct": 60.0, "micro_run_lt2_pct": 40.0}},
                },
                "sample_gates": {"minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20},
                "continuation_baseline": {
                    "baseline_run_count": 7, "median_duration_minutes": 18.78,
                    "short_run_lt5_pct": 0.0, "micro_run_lt2_pct": 0.0,
                    "sample_gates": {"minimum_post_runs_for_provisional": 5, "minimum_post_runs_for_comparable": 20},
                },
                "score_semantics": {"direction_threshold": 10.0},
            }), encoding="utf-8")

            fixtures = [
                ("go-explicit", 12.0, {"run_mode": "continuation"}, "normal run"),
                ("bounded-task", 1.0, {}, "quick verification"),
                ("manual-go2-legacy", 20.0, {}, "legacy continuation"),
                ("go-interrupted", 2.0, {"run_mode": "continuation", "stop_reason": "user_interrupted"}, "interrupted"),
            ]
            for index, (run_id, duration, extra, outcome) in enumerate(fixtures):
                archive = reports / f"c{index}.md"
                archive.write_text(f"run_id: {run_id}\nstate: RUN_FINISHED\noutcome: {outcome}\n", encoding="utf-8")
                fields = {"run_id": run_id, "outcome": outcome, **extra}
                meta = {
                    "schema": "worker-report-history.v6", "population": "manual", "report_sha256": f"c{index}",
                    "run_id": run_id, "started_at": f"2026-09-06T21:{10+index:02d}:00+03:00",
                    "finished_at": f"2026-09-06T21:{20+index:02d}:00+03:00", "duration_minutes": duration,
                    "archived_at": f"2026-09-06T21:{25+index:02d}:00+03:00", "archive_path": str(archive),
                    "reported_fields": fields, "outcome": outcome, "stop_reason": extra.get("stop_reason"),
                }
                (reports / f"c{index}.json").write_text(json.dumps(meta), encoding="utf-8")

            projected = build_manual_sanity_projection(
                history, baseline_path=baseline_path, now=datetime.fromisoformat("2026-09-06T22:00:00+03:00")
            )
            continuation = projected["continuation"]
            self.assertEqual(continuation["status"], "INSUFFICIENT_DATA")
            self.assertEqual(continuation["observation"]["identified_run_count"], 3)
            self.assertEqual(continuation["observation"]["eligible_run_count"], 2)
            self.assertEqual(continuation["observation"]["excluded_user_interrupted_count"], 1)
            self.assertEqual(continuation["observation"]["median_duration_minutes"], 16.0)
            self.assertEqual(continuation["observation"]["short_run_lt5_pct"], 0.0)
            self.assertEqual(continuation["observation"]["micro_run_lt2_pct"], 0.0)
            self.assertEqual(projected["guardrails"], {})


if __name__ == "__main__":
    unittest.main()
