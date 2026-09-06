from __future__ import annotations

import unittest

from tools.timeline_materializer import _lesson_packet


class Issue675Slice1SeedScopeTests(unittest.TestCase):
    @staticmethod
    def commit(event_id: str, title: str, body: str, *, project: str = "lowvram") -> dict:
        return {
            "id": event_id,
            "source_type": "GIT_COMMIT",
            "authority": "REPO_HISTORY",
            "project": project,
            "projects": [project],
            "event_at": "2026-08-20T12:00:00+03:00",
            "title": title,
            "summary": title,
            "body": body,
            "sha": event_id.split(":")[-1].ljust(40, "a")[:40],
            "anchors": [],
            "refs": [],
        }

    def test_direct_commit_seeds_are_lessons_but_direct_worker_seed_is_not_self_echoed(self):
        query = "export skin replay deformation"
        export_seed = self.commit(
            "seed:export",
            "Rigged export loses skin during deformation export",
            "Export consumed the armature modifier so weighted skin vanished even though the command succeeded; verify exported deformation state explicitly.",
        )
        replay_seed = self.commit(
            "seed:replay",
            "Replay catches solved-pose deformation drift",
            "The solved pose looked correct but replayed keyframes inverted the limb; compare replay deformation against the solver target.",
        )
        task_worker = {
            "id": "worker:current-task",
            "source_type": "WORKER_REPORT",
            "authority": "DERIVED_WORKER_HISTORY",
            "project": "tiny3d",
            "projects": ["tiny3d"],
            "event_at": "2026-09-06T20:00:00+03:00",
            "title": "Current Hummingbird export skin replay deformation task",
            "summary": "Current task observation for Hummingbird deformation qualification.",
            "findings": (
                "Current Hummingbird work is checking exported skin, replay deformation, rig weights, and animation proof. "
                "This report describes the task being investigated and must seed retrieval without becoming its own historical lesson."
            ),
            "anchors": [],
            "refs": [],
        }
        bridge_export = self.commit(
            "bridge:export",
            "Verify exported armature skin",
            "Export verification checks actual weighted skin and deformation after serialization rather than trusting process success.",
            project="tiny3d",
        )
        bridge_replay = self.commit(
            "bridge:replay",
            "Verify replayed deformation keyframes",
            "Replay keyframes must reproduce measured deformation; replay drift exposes animation state that the solver never keyed.",
            project="tiny3d",
        )
        candidates = [export_seed, replay_seed, task_worker, bridge_export, bridge_replay]

        packet = _lesson_packet(
            query,
            selected=[export_seed, replay_seed, task_worker],
            candidates=candidates,
            query_index=None,
            limit=8,
        )

        ids = {item.get("source_event_id") for item in packet.get("items", [])}
        self.assertEqual(packet["authority"], "DERIVED_HISTORICAL_PRIORS_ONLY")
        self.assertEqual(packet["validation"], "SLICE1_RETRIEVAL_ONLY_NOT_VALIDATED")
        self.assertTrue(packet["live_truth_required"])
        self.assertTrue(packet["nonblocking"])
        self.assertIn(export_seed["id"], ids)
        self.assertIn(replay_seed["id"], ids)
        self.assertNotIn(task_worker["id"], ids)


if __name__ == "__main__":
    unittest.main()
