from __future__ import annotations

import unittest

from tools.timeline_materializer import _lesson_packet


class Issue675StaticAnimationProofTests(unittest.TestCase):
    def test_static_animation_task_surfaces_temporal_runtime_rejection_not_metadata_success(self):
        issue = {
            "id": "github-issue:p3#1657",
            "source_type": "GITHUB_ISSUE",
            "authority": "GITHUB_HISTORY_SNAPSHOT",
            "project": "p3",
            "event_at": "2026-09-05T22:41:13+00:00",
            "title": "Fail closed on static animation-backed visual proof videos",
            "summary": "12/12 animation-backed videos decoded 30 frames but showed effectively zero temporal motion.",
            "body": (
                "Twelve animation-backed videos decoded thirty frames but showed effectively zero temporal motion even though "
                "the source actions contained real transform keys. Historical visual evidence stays PENDING_REVIEW and runtime "
                "root cause is unproven; static frames, metadata, source keys, hashes, or RPC success cannot substitute for rendered motion."
            ),
            "anchors": ["github:organicoverlords/p3#1657"],
            "refs": ["#1657"],
        }
        pr = {
            "id": "github-pr:p3#1710",
            "source_type": "GITHUB_PR",
            "authority": "GITHUB_HISTORY_SNAPSHOT",
            "project": "p3",
            "event_at": "2026-09-05T22:41:14+00:00",
            "title": "Fail closed on static animation proof videos",
            "summary": "Reject animation-backed videos whose decoded frames do not demonstrate temporal motion.",
            "body": (
                "The temporal rendered-motion gate rejects static animation proof videos with "
                "VISUAL_PROOF_ANIMATION_TEMPORAL_GATE_FAILED. Historical frames with max_changed_samples=0 reject while a known-moving "
                "control passes; decoded frames and source animation metadata alone are insufficient runtime proof."
            ),
            "anchors": ["github:organicoverlords/p3#1710"],
            "refs": ["#1710"],
        }
        metadata_only = {
            "id": "git:p3:metadata-only",
            "source_type": "GIT_COMMIT",
            "authority": "REPO_HISTORY",
            "project": "p3",
            "event_at": "2026-09-05T20:00:00+00:00",
            "title": "Record animation metadata and source keys",
            "summary": "Animation metadata export completed successfully.",
            "body": (
                "Decoded frames, source transform keys, clip names, hashes, action metadata, and validation receipts were recorded. "
                "The metadata export succeeded and the animation file exists, but no rendered temporal motion was measured."
            ),
            "sha": "a" * 40,
            "anchors": ["gitsha:" + "a" * 40],
            "refs": [],
        }
        generic_runtime = {
            "id": "git:tiny3d:generic-runtime",
            "source_type": "GIT_COMMIT",
            "authority": "REPO_HISTORY",
            "project": "tiny3d",
            "event_at": "2026-09-05T19:00:00+00:00",
            "title": "Author runtime animation backend",
            "summary": "Runtime animation authoring writes frames and source keys.",
            "body": (
                "Runtime animation authoring emits decoded frames, source transform keys, clip metadata, hashes, and actions. "
                "This establishes authoring output but does not inspect whether a rendered proof video actually moves."
            ),
            "sha": "b" * 40,
            "anchors": ["gitsha:" + "b" * 40],
            "refs": [],
        }

        packet = _lesson_packet(
            "static animation proof temporal runtime evidence",
            selected=[issue, pr],
            candidates=[issue, pr, metadata_only, generic_runtime],
            query_index=None,
            limit=8,
        )

        ids = {row.get("source_event_id") for row in packet.get("items", [])}
        primary_ids = {issue["id"], pr["id"]}
        self.assertTrue(
            ids & primary_ids,
            "the packet must retain at least one exact primary static-video rejection instead of replacing both with bridge noise",
        )
        self.assertNotIn(
            metadata_only["id"],
            ids,
            "animation metadata/source-key success is explicitly insufficient temporal runtime proof",
        )
        self.assertTrue(packet["live_truth_required"])
        self.assertTrue(packet["nonblocking"])


if __name__ == "__main__":
    unittest.main()
