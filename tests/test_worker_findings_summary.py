from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from tools.worker_findings_summary import build_summary


class WorkerFindingsSummaryTests(unittest.TestCase):
    def _write_history(self, root: Path, population: str, name: str, *, tag_capable: bool = True, **overrides):
        history = root / ("history" if population == "timed" else "manual/history") / "_reports"
        history.mkdir(parents=True, exist_ok=True)
        now = datetime.now().astimezone()
        payload = {
            "schema": "worker-report-history.v6",
            "population": population,
            "report_sha256": name,
            "display_label": f"{population}-{name}",
            "archived_at": now.isoformat(),
            "finished_at": now.isoformat(),
            "duration_minutes": 10.0,
            "findings": None,
        }
        if tag_capable:
            payload["finding_tags"] = []
        payload.update(overrides)
        (history / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")

    def _write_current(self, root: Path, population: str, name: str, *, state="RUNNING", tags="none", findings="none", tag_capable=True):
        current = root / ("current" if population == "timed" else "manual/current")
        current.mkdir(parents=True, exist_ok=True)
        key = "automation_id" if population == "timed" else "run_id"
        now = datetime.now().astimezone().isoformat()
        tag_lines = f"finding_tags: {tags}\nfindings: {findings}\n" if tag_capable else ""
        (current / f"{name}.md").write_text(
            f"{key}: {name}\ndisplay_label: {population}-{name}\nstarted_at: {now}\nlast_activity_at: {now}\n"
            f"repo: p3\nscope: scope-{name}\nstate: {state}\noutcome: x\nmutation: x\nvalidation: PASS\n"
            f"remaining_gate: none\n{tag_lines}",
            encoding="utf-8",
        )

    def test_keeps_timed_and_manual_run_statistics_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_history(root, "timed", "t1", duration_minutes=20.0, target_utilization_pct=83.3, finding_tags=["build"])
            self._write_history(root, "manual", "m1", duration_minutes=5.0, finding_tags=["tooling"])
            summary = build_summary(root)
            self.assertEqual(summary["populations"]["timed"]["average_duration_minutes"], 20.0)
            self.assertEqual(summary["populations"]["timed"]["average_target_utilization_pct"], 83.3)
            self.assertEqual(summary["populations"]["manual"]["average_duration_minutes"], 5.0)
            self.assertNotIn("average_target_utilization_pct", summary["populations"]["manual"])
            self.assertEqual(summary["findings"]["tag_counts"], {"build": 1, "tooling": 1})

    def test_reports_tag_coverage_for_archived_and_active_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_history(root, "timed", "tagged", finding_tags=["bug"])
            self._write_history(root, "timed", "legacy", tag_capable=False)
            self._write_current(root, "timed", "active-tagged", tags="resource, build", findings="paging pressure")
            self._write_current(root, "timed", "active-none")
            self._write_current(root, "timed", "active-legacy", tag_capable=False)
            summary = build_summary(root)
            timed = summary["populations"]["timed"]
            self.assertEqual(timed["archived_tag_eligible_runs"], 1)
            self.assertEqual(timed["archived_tagged_pct"], 100.0)
            self.assertEqual(timed["active_tag_eligible_runs"], 2)
            self.assertEqual(timed["active_tagged_pct"], 50.0)
            self.assertEqual(summary["findings"]["tag_counts"], {"build": 1, "bug": 1, "resource": 1})

    def test_normalizes_quoted_whole_field_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_current(root, "timed", "quoted", tags='"resource,improvement,proof"', findings="quoted producer")
            summary = build_summary(root)
            self.assertEqual(
                summary["findings"]["tag_counts"],
                {"improvement": 1, "proof": 1, "resource": 1},
            )
            recent = summary["findings"]["recent"][0]
            self.assertEqual(recent["finding_tags"], ["improvement", "proof", "resource"])

    def test_ignores_finalized_current_reports_to_avoid_double_counting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_history(root, "manual", "m1", finding_tags=["improvement"])
            self._write_current(root, "manual", "m1", state="RUN_FINISHED", tags="improvement", findings="already archived")
            summary = build_summary(root)
            self.assertEqual(summary["populations"]["manual"]["archived_runs"], 1)
            self.assertEqual(summary["populations"]["manual"]["active_runs"], 0)
            self.assertEqual(summary["findings"]["tag_counts"], {"improvement": 1})

    def test_excludes_abandoned_history_snapshots_from_findings_and_run_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_history(
                root,
                "manual",
                "abandoned",
                lifecycle_status="ABANDONED_OPEN",
                included_in_metrics=False,
                finding_tags=["improvement"],
                findings="self report only",
            )
            summary = build_summary(root)
            self.assertEqual(summary["populations"]["manual"]["archived_runs"], 0)
            self.assertEqual(summary["findings"]["tag_counts"], {})
            self.assertEqual(summary["findings"]["recent"], [])

    def test_delegates_history_window_to_canonical_metadata_loader(self):
        now = datetime.now().astimezone()
        recent = {
            "schema": "worker-report-history.v6",
            "population": "timed",
            "report_sha256": "recent",
            "display_label": "timed-recent",
            "archived_at": now.isoformat(),
            "finished_at": now.isoformat(),
            "duration_minutes": 20.0,
            "target_utilization_pct": 83.3,
            "finding_tags": ["performance"],
        }
        with tempfile.TemporaryDirectory() as tmp, patch(
            "tools.worker_findings_summary.load_history_metadata", side_effect=[[recent], []]
        ) as loader:
            summary = build_summary(Path(tmp), hours=24)
        self.assertEqual(loader.call_count, 2)
        for call in loader.call_args_list:
            self.assertIn("since", call.kwargs)
            self.assertLess(abs((call.kwargs["since"] - (now - timedelta(hours=24))).total_seconds()), 5)
        self.assertEqual(summary["populations"]["timed"]["archived_runs"], 1)
        self.assertEqual(summary["findings"]["tag_counts"], {"performance": 1})

    def test_ignores_old_history_outside_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = (datetime.now().astimezone() - timedelta(days=2)).isoformat()
            self._write_history(root, "timed", "old", archived_at=old, finished_at=old, finding_tags=["error"])
            summary = build_summary(root, hours=24)
            self.assertEqual(summary["populations"]["timed"]["archived_runs"], 0)
            self.assertEqual(summary["findings"]["tag_counts"], {})


if __name__ == "__main__":
    unittest.main()
