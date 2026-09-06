from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.timeline_materializer import SCHEMA, build_work_graph, query_materialized


class TimelineLessonPacketPublicTests(unittest.TestCase):
    @staticmethod
    def commit(sha: str, title: str, body: str) -> dict:
        return {
            "id": f"git:lowvram:{sha}",
            "source_type": "GIT_COMMIT",
            "authority": "REPO_HISTORY",
            "event_at": "2026-08-09T03:00:00+03:00",
            "project": "lowvram",
            "projects": ["lowvram"],
            "title": title,
            "summary": title,
            "body": body,
            "sha": sha,
            "short_sha": sha[:10],
            "anchors": [],
            "refs": [],
        }

    def test_attached_worker_findings_remain_context_without_replacing_commit_lesson(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            stamp = "2026-09-06T20:00:00+03:00"
            geodesic_sha = "97ff891a4ca48faf77c334f80678133ea263c16f"
            export_sha = "8ad2a7ba8d3bbc92bca3bd09af798e17e7db99a4"
            replay_sha = "9a44ad7326bf77a385c2bfe22b547ef9c80a2c43"
            wrong_limb_sha = "0e7bef0fa56bea230d1830ec2757dcf7c1413496"

            seed = {
                "id": "worker:hummingbird-public-seed",
                "source_type": "WORKER_REPORT",
                "authority": "DERIVED_WORKER_HISTORY",
                "event_at": stamp,
                "project": "tiny3d",
                "projects": ["tiny3d"],
                "title": "Hummingbird wing deformation qualification",
                "summary": "Hummingbird wing deformation still needs measured rigging evidence.",
                "findings": (
                    "Inspect wing skin weights, welded regions, surface connectivity, export replay, and exact posed limbs; "
                    "historical findings are priors only and current evidence must decide."
                ),
                "refs": [],
                "anchors": [],
            }
            geodesic = self.commit(
                geodesic_sha,
                "Bone placement from the mesh, and weights over the surface",
                "Euclidean proximity reaches across gaps and claims opposite-side vertices. "
                "Geodesic distance follows the mesh surface over adjacency built from welded vertex positions; "
                "GLB UV seams duplicate render vertices and must not break topology traversal.",
            )
            export = self.commit(
                export_sha,
                "Rigged exports lost their skin at the export call",
                "Export consumed the armature modifier while weights and animation remained, so a successful-looking file could not deform. "
                "Validate the exported rig and replayed animation rather than trusting exit status.",
            )
            replay = self.commit(
                replay_sha,
                "Gate the walk clip on replay, not just on the pose the solver saw",
                "The solved pose was correct but replay dropped an unkeyed handedness scale and rotated the limb 180 degrees. "
                "Measure replay drift on the actual animation frames.",
            )
            wrong_limb = self.commit(
                wrong_limb_sha,
                "The five-pose verifier posed the wrong limb and called it a pass",
                "Opposite-side aliases selected a real but wrong limb, so the visual proof falsely passed. "
                "Require direct same-side vertex and deformation evidence.",
            )
            attached_note = {
                "id": "worker:slice1-ranking-note",
                "source_type": "WORKER_REPORT",
                "authority": "DERIVED_WORKER_HISTORY",
                "event_at": "2026-09-07T00:22:21+03:00",
                "project": "lowvram",
                "projects": ["lowvram"],
                "title": "Slice 1 ranking proof note",
                "summary": "Ranking acceptance note attached to the historical geodesic commit.",
                "findings": (
                    "The residual false positive had query_hits=0, direct_lesson_hits=0, and lesson concepts only proof. "
                    "Filtering that proof-only bridge class preserves technical transfer while reviewing Hummingbird wing deformation."
                ),
                "refs": [geodesic_sha],
                "anchors": [],
            }
            events = [seed, geodesic, export, replay, wrong_limb, attached_note]
            payload = {
                "schema": SCHEMA,
                "generated_at": stamp,
                "horizon_days": 30,
                "ingestion": {},
                "timeline": {
                    "schema_version": "1",
                    "authority": "HISTORICAL_EVIDENCE_ONLY",
                    "contract": "history only",
                    "events": events,
                    "historical_evidence_events": [],
                    "work_graph": build_work_graph(events),
                    "continuity_graph": {"cases": [], "summary": {}},
                    "materialized": {},
                },
            }
            (state / "timeline-store.json").write_text(json.dumps(payload), encoding="utf-8")
            result = query_materialized(root=root, query="hummingbird wing deformation", limit=20)

        self.assertIsNotNone(result)
        groups = result["work_graph"]["commit_groups"]
        geodesic_group = next(
            group for group in groups
            if group.get("title") == "Bone placement from the mesh, and weights over the surface"
        )
        worker_text = " ".join(
            str(worker.get("findings") or "") for worker in geodesic_group.get("workers", [])
        ).casefold()
        self.assertIn("residual false positive", worker_text)

        packet = result["lesson_packet"]
        geodesic_item = next(
            item for item in packet.get("items", [])
            if f"gitsha:{geodesic_sha}" in (item.get("evidence_anchors") or [])
            or str(item.get("source_event_id") or "").endswith(geodesic_sha)
        )
        lesson_text = str(
            geodesic_item.get("conclusion")
            or geodesic_item.get("historical_prior")
            or geodesic_item.get("historical_lesson")
            or geodesic_item.get("summary")
            or ""
        ).casefold()
        self.assertIn("geodesic", lesson_text)
        self.assertIn("welded", lesson_text)
        self.assertNotIn("residual false positive", lesson_text)


if __name__ == "__main__":
    unittest.main()
