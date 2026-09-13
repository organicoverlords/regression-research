from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.timeline_materializer import (
    LOCK_STALE_MINUTES,
    SCHEMA,
    _acquire_lock,
    build_work_graph,
    materialize,
    query_materialized,
)


class TimelineIssue649RecoveryTests(unittest.TestCase):
    SOURCES = (
        "repos",
        "workers",
        "artifacts",
        "local_artifacts",
        "library_artifacts",
        "machine",
        "github",
        "mcp",
        "mcp_history",
        "runner_logs",
        "coordinator",
    )

    @staticmethod
    def _minimal_overview() -> dict[str, object]:
        return {
            "contract": "history only",
            "eligible_entries": 0,
            "incident_rollups": [],
            "recent": [],
            "projects": [],
            "recurring_tags": [],
        }

    def _write_previous_store(self, root: Path, *, generated_at: str, events: list[dict] | None = None) -> Path:
        (root / "memory").mkdir(parents=True, exist_ok=True)
        state = root / ".state" / "timeline"
        state.mkdir(parents=True, exist_ok=True)
        (state / "timeline-store.json").write_text(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "generated_at": generated_at,
                    "source_watermarks": {source: generated_at for source in self.SOURCES},
                    "ingestion": {"backfill_incomplete_sources": []},
                    "timeline": {"events": list(events or [])},
                }
            ),
            encoding="utf-8",
        )
        return state

    def _empty_refresh_patches(self):
        clean = {"events": 0, "saturated": False, "errors": []}
        return (
            patch("tools.timeline_materializer.discover_repo_specs", return_value=[]),
            patch("tools.timeline_materializer.load_bank", return_value=[]),
            patch("tools.timeline_materializer.collect_repo_history", return_value={"events": [], "coverage": {}}),
            patch("tools.timeline_materializer.worker_history_events", return_value=[]),
            patch("tools.timeline_materializer.tracked_artifact_events", return_value=[]),
            patch("tools.timeline_materializer.local_artifact_events", return_value=([], clean)),
            patch("tools.timeline_materializer.library_artifact_events", return_value=([], clean)),
            patch("tools.timeline_materializer.machine_observation_events", return_value=([], clean)),
            patch(
                "tools.timeline_materializer.mcp_events",
                return_value=([], {"events": 0, "receipts_saturated": False, "errors": []}),
            ),
            patch("tools.timeline_materializer.mcp_replacement_events", return_value=([], clean)),
            patch("tools.timeline_materializer.runner_log_events", return_value=([], clean)),
            patch("tools.timeline_materializer.coordinator_events", return_value=([], clean)),
            patch("tools.timeline_materializer.build_overview", return_value=self._minimal_overview()),
        )

    def test_mixed_offset_work_graph_latest_at_is_ordered_by_instant(self):
        earlier_local = "2026-09-06T10:00:00+03:00"  # 07:00Z
        later_utc = "2026-09-06T08:30:00+00:00"      # 08:30Z
        events = [
            {
                "id": "commit:a",
                "source_type": "GIT_COMMIT",
                "project": "p3",
                "sha": "a" * 40,
                "patch_id": "same-patch",
                "event_at": earlier_local,
                "recorded_at": earlier_local,
                "title": "same chronology repair",
                "anchors": ["github:organicoverlords/regression-research#649"],
            },
            {
                "id": "commit:b",
                "source_type": "GIT_COMMIT",
                "project": "p3",
                "sha": "b" * 40,
                "patch_id": "same-patch",
                "event_at": later_utc,
                "recorded_at": later_utc,
                "title": "same chronology repair",
                "anchors": ["github:organicoverlords/regression-research#649"],
            },
        ]

        graph = build_work_graph(events)
        group = graph["commit_groups"][0]
        stream = graph["workstreams"][0]

        # Preserve the source timestamps, but choose the latest one by parsed instant.
        self.assertEqual([commit["at"] for commit in group["commits"]], [earlier_local, later_utc])
        self.assertEqual(group["latest_at"], later_utc)
        self.assertEqual(stream["latest_at"], later_utc)

    def test_mixed_offset_work_graph_rows_are_sorted_by_instant(self):
        earlier_local = "2026-09-06T10:00:00+03:00"  # 07:00Z
        later_utc = "2026-09-06T08:30:00+00:00"      # 08:30Z
        events = [
            {
                "id": "commit:earlier",
                "source_type": "GIT_COMMIT",
                "project": "p3",
                "sha": "c" * 40,
                "patch_id": "earlier-patch",
                "event_at": earlier_local,
                "recorded_at": earlier_local,
                "title": "earlier chronology repair",
                "anchors": ["github:organicoverlords/regression-research#649"],
            },
            {
                "id": "commit:later",
                "source_type": "GIT_COMMIT",
                "project": "p3",
                "sha": "d" * 40,
                "patch_id": "later-patch",
                "event_at": later_utc,
                "recorded_at": later_utc,
                "title": "later chronology repair",
                "anchors": ["github:organicoverlords/regression-research#650"],
            },
        ]

        graph = build_work_graph(events)

        self.assertEqual(graph["commit_groups"][0]["latest_at"], later_utc)
        self.assertEqual(graph["workstreams"][0]["latest_at"], later_utc)
        self.assertEqual(graph["workstreams"][0]["anchor"], "github:organicoverlords/regression-research#650")

    def test_disabled_github_does_not_advance_past_unread_history(self):
        prior = "2026-09-06T05:00:00+00:00"
        now = datetime(2026, 9, 6, 6, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self._write_previous_store(root, generated_at=prior)
            patches = self._empty_refresh_patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12]:
                result = materialize(root=root, include_github=False, now=now)

            payload = json.loads((state / "timeline-store.json").read_text(encoding="utf-8"))
            self.assertEqual(result["refresh_mode"], "INCREMENTAL")
            self.assertEqual(payload["source_watermarks"]["github"], prior)

    def test_old_but_live_refresh_lock_is_not_stolen_by_age(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "refresh.lock"
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
            try:
                lock_path.write_text(f"{child.pid}\n", encoding="ascii")
                stale = time.time() - (LOCK_STALE_MINUTES * 60 + 5)
                os.utime(lock_path, (stale, stale))

                acquired = _acquire_lock(lock_path)
                try:
                    self.assertIsNone(acquired)
                    self.assertEqual(lock_path.read_text(encoding="ascii").strip(), str(child.pid))
                finally:
                    if acquired is not None:
                        os.close(acquired)
            finally:
                child.terminate()
                child.wait(timeout=10)

    def test_fresh_lock_with_dead_owner_is_reclaimed_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "refresh.lock"
            lock_path.write_text("99999999\n", encoding="ascii")

            acquired = _acquire_lock(lock_path)
            self.assertIsNotNone(acquired)
            if acquired is not None:
                os.close(acquired)

    def test_unknown_lock_owner_is_not_reclaimed_even_when_old(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "refresh.lock"
            lock_path.write_text("12345\n", encoding="ascii")
            stale = time.time() - (LOCK_STALE_MINUTES * 60 + 5)
            os.utime(lock_path, (stale, stale))

            with patch("tools.timeline_materializer._lock_owner_liveness", return_value=None):
                acquired = _acquire_lock(lock_path)

            self.assertIsNone(acquired)
            self.assertEqual(lock_path.read_text(encoding="ascii").strip(), "12345")

    def test_malformed_lock_owner_is_unknown_and_not_reclaimed(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "refresh.lock"
            lock_path.write_text("not-a-pid\n", encoding="ascii")

            acquired = _acquire_lock(lock_path)

            self.assertIsNone(acquired)
            self.assertTrue(lock_path.exists())

    def test_interrupted_sidecar_write_keeps_canonical_evidence_readable_and_retryable(self):
        prior = "2026-09-06T05:00:00+00:00"
        event = {
            "id": "commit:preserved",
            "source_type": "GIT_COMMIT",
            "authority": "LOCAL_REPO_HISTORY",
            "project": "vault",
            "projects": ["vault"],
            "sha": "c" * 40,
            "event_at": "2026-09-06T04:50:00+00:00",
            "recorded_at": "2026-09-06T04:50:00+00:00",
            "title": "preserved recovery evidence",
            "summary": "preserved recovery evidence",
            "refs": [],
            "anchors": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = self._write_previous_store(root, generated_at=prior, events=[event])
            patches = self._empty_refresh_patches()
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12], patch(
                "tools.timeline_materializer._atomic_pickle", side_effect=OSError("simulated interrupted sidecar publication")
            ):
                with self.assertRaises(OSError):
                    materialize(root=root, include_github=False, now=datetime(2026, 9, 6, 6, 0, tzinfo=timezone.utc))

            self.assertTrue((state / "timeline-store.json").is_file())
            recovered_read = query_materialized(root=root, query="preserved recovery evidence", limit=4)
            self.assertEqual(recovered_read["matching_events"], 1)
            self.assertEqual(recovered_read["events"][0]["id"], event["id"])
            self.assertFalse((state / "refresh.lock").exists())

            retry_patches = self._empty_refresh_patches()
            with retry_patches[0], retry_patches[1], retry_patches[2], retry_patches[3], retry_patches[4], retry_patches[5], retry_patches[6], retry_patches[7], retry_patches[8], retry_patches[9], retry_patches[10], retry_patches[11], retry_patches[12]:
                retry = materialize(root=root, include_github=False, now=datetime(2026, 9, 6, 6, 5, tzinfo=timezone.utc))
            self.assertTrue(retry["ok"])
            self.assertEqual(retry["status"], "REFRESHED")


if __name__ == "__main__":
    unittest.main()
