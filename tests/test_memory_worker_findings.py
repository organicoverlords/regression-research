import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tools.memory_bank import build_overview, worker_findings_overview
from tools.stack_atlas import _compact_worker_findings


class MemoryWorkerFindingsOverviewTests(unittest.TestCase):
    def write_metrics(self, path: Path, *, population: str, generated_at: str, window_hours=24.0, reports=2, counts=None, latest=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": "worker-report-metrics.v1",
            "population": population,
            "generated_at": generated_at,
            "window_hours": window_hours,
            "reports": reports,
            "finding_tag_counts": counts or {},
            "latest_reports": latest or [],
        }), encoding="utf-8")

    def test_combines_timed_and_manual_metrics_without_liveness_claims(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            timed = root / "timed.json"
            manual = root / "manual.json"
            long_finding = "x" * 500
            self.write_metrics(
                timed,
                population="timed",
                generated_at="2026-09-05T23:30:00+03:00",
                counts={"proof": 4, "bug": 2},
                latest=[{"display_label": "Pine", "archived_at": "2026-09-05T23:30:00+03:00", "repo": "p3", "finding_tags": ["proof"], "findings": long_finding}],
            )
            self.write_metrics(
                manual,
                population="manual",
                generated_at="2026-09-05T23:40:00+03:00",
                counts={"proof": 3, "improvement": 5},
                latest=[{"display_label": "Audit", "archived_at": "2026-09-05T23:40:00+03:00", "repo": "vault", "finding_tags": ["improvement"], "findings": "aggregation improved"}],
            )
            result = worker_findings_overview(
                timed_metrics=timed,
                manual_metrics=manual,
                limit=3,
                now=datetime.fromisoformat("2026-09-06T00:00:00+03:00"),
            )
        self.assertIn("never current liveness", result["contract"])
        self.assertEqual(result["top_tags"][0], {"name": "proof", "count": 7})
        self.assertEqual(result["top_tags"][1], {"name": "improvement", "count": 5})
        self.assertEqual([item["population"] for item in result["populations"]], ["timed", "manual"])
        self.assertTrue(all(item["status"] == "AVAILABLE" for item in result["populations"]))
        self.assertLessEqual(len(result["populations"][0]["recent_findings"][0]["finding"]), 320)
        self.assertTrue(result["populations"][0]["recent_findings"][0]["finding"].endswith("..."))

    def test_marks_projection_stale_relative_to_its_own_window_and_missing_source(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            timed = root / "timed.json"
            manual = root / "missing.json"
            self.write_metrics(timed, population="timed", generated_at="2026-09-04T00:00:00+03:00", window_hours=24.0)
            result = worker_findings_overview(
                timed_metrics=timed,
                manual_metrics=manual,
                now=datetime.fromisoformat("2026-09-06T00:00:00+03:00"),
            )
        self.assertEqual(result["populations"][0]["status"], "STALE_PROJECTION")
        self.assertEqual(result["populations"][0]["source_age_hours"], 48.0)
        self.assertEqual(result["populations"][1]["status"], "MISSING")

    def test_build_overview_attaches_worker_findings_and_bootstrap_compaction_drops_long_text(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            timed = root / "timed.json"
            manual = root / "manual.json"
            self.write_metrics(timed, population="timed", generated_at="2026-09-06T00:00:00+03:00", counts={"proof": 2}, latest=[{"findings": "very long proof detail", "finding_tags": ["proof"]}])
            self.write_metrics(manual, population="manual", generated_at="2026-09-06T00:00:00+03:00", counts={"improvement": 1})
            overview = build_overview([], timed_metrics=timed, manual_metrics=manual, limit=3, now=datetime.fromisoformat("2026-09-06T00:00:00+03:00"))
        self.assertIn("worker_findings", overview)
        compact = _compact_worker_findings(overview, 3)
        self.assertEqual(compact["top_tags"][0], {"name": "proof", "count": 2})
        self.assertNotIn("recent_findings", compact["populations"][0])
        self.assertEqual(compact["populations"][0]["reports"], 2)


if __name__ == "__main__":
    unittest.main()
