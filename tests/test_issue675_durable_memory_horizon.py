from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from tools.timeline_materializer import materialize, query_materialized


class Issue675DurableMemoryHorizonTests(unittest.TestCase):
    def test_promoted_durable_memory_is_not_aged_out_by_default_materialization(self):
        durable = {
            "id": "mem:durable-front-axis-correction",
            "timestamp": "2026-08-01T12:00:00+03:00",
            "kind": "correction",
            "scope": "lowvram/front-axis",
            "tags": ["front-axis", "correction", "camera", "chirality"],
            "title": "Retract the front-axis defect: the camera was never wrong",
            "text": (
                "Measured projector evidence showed the fitted camera was correct; the old objective compared "
                "handedness rather than facing. Preserve the retraction and verify current facing from physical evidence."
            ),
            "state": "PROVEN",
            "evidence": ["git:lowvram:51340308be7a0ec1fe6ad4df804988c1eb71cea5"],
            "supersedes": [],
            "project": "lowvram",
        }
        zero = {"events": 0, "saturated": False, "errors": []}
        minimal_overview = {
            "contract": "history only",
            "eligible_entries": 1,
            "incident_rollups": [],
            "recent": [],
            "projects": [],
            "recurring_tags": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "memory").mkdir(parents=True)
            with patch("tools.timeline_materializer.discover_repo_specs", return_value=[]), patch(
                "tools.timeline_materializer.load_bank", return_value=[durable]
            ), patch(
                "tools.timeline_materializer.collect_repo_history", return_value={"events": [], "coverage": {}}
            ), patch("tools.timeline_materializer.enrich_repo_events"), patch(
                "tools.timeline_materializer.worker_history_events", return_value=[]
            ), patch("tools.timeline_materializer.tracked_artifact_events", return_value=[]), patch(
                "tools.timeline_materializer.local_artifact_events",
                return_value=([], {"events": 0, "candidates": 0, "limit": 1000, "saturated": False}),
            ), patch("tools.timeline_materializer.library_artifact_events", return_value=([], zero)), patch(
                "tools.timeline_materializer.machine_observation_events", return_value=([], zero)
            ), patch(
                "tools.timeline_materializer.mcp_events",
                return_value=([], {"events": 0, "receipts_saturated": False, "errors": []}),
            ), patch("tools.timeline_materializer.mcp_replacement_events", return_value=([], zero)), patch(
                "tools.timeline_materializer.runner_log_events", return_value=([], zero)
            ), patch("tools.timeline_materializer.build_overview", return_value=minimal_overview):
                result = materialize(
                    root=root,
                    include_github=False,
                    now=datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc),
                )

            self.assertTrue(result["ok"])
            query = query_materialized(root=root, query="front axis camera wrong", limit=8)
            self.assertIsNotNone(query)
            event_ids = {row.get("id") for row in query.get("events", [])}
            self.assertIn(
                durable["id"],
                event_ids,
                "default materialization must not age out durable Memory corrections",
            )


if __name__ == "__main__":
    unittest.main()
