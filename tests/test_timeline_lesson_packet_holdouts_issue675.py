from __future__ import annotations

import unittest

from tools.timeline_materializer import _lesson_packet


class TimelineLessonPacketHoldoutTests(unittest.TestCase):
    @staticmethod
    def commit(event_id: str, title: str, body: str, *, project: str = "lowvram") -> dict:
        return {
            "id": event_id,
            "source_type": "GIT_COMMIT",
            "project": project,
            "event_at": "2026-08-09T03:00:00+03:00",
            "title": title,
            "summary": title,
            "body": body,
            "sha": event_id.split(":")[-1].ljust(40, "a")[:40],
            "anchors": [],
            "refs": [],
        }

    def test_direct_primary_seeds_remain_eligible_for_bounded_packet(self):
        query = "export loses skin replay differs from solved pose"
        export_seed = self.commit(
            "seed:export",
            "Rigged exports lost their skin at the export call",
            "export apply consumed the armature modifier so joints and weights remained but the usable skin disappeared; "
            "the command exited successfully despite broken deformation and required an explicit armature export check",
        )
        replay_seed = self.commit(
            "seed:replay",
            "Gate the walk clip on replay, not just on the pose the solver saw",
            "the solver placed the ankle correctly but playback dropped an unkeyed handedness scale; replayed keyframes inverted the leg, "
            "so a replay drift measurement is required rather than trusting the solved in-memory pose",
        )
        generic_seed = {
            "id": "seed:generic",
            "source_type": "WORKER_REPORT",
            "project": "p3",
            "event_at": "2026-09-06T20:00:00+00:00",
            "title": "workflow validation report",
            "summary": "reviewed pipeline status and generated report metadata for the task",
            "findings": "workflow resolver report compiler validation issue branch commit test proof status",
            "validation": "tests passed and report published",
            "anchors": [],
            "refs": [],
        }
        weak_seed = {
            "id": "seed:weak",
            "source_type": "VAULT_MEMORY",
            "project": "vault",
            "event_at": "2026-09-06T19:00:00+00:00",
            "title": "generic process note",
            "summary": "generic process note about reports and checks",
            "text": "generic process note about reports and checks",
            "anchors": [],
            "refs": [],
        }
        bridge_export = self.commit(
            "bridge:export",
            "Verify exported armature deformation",
            "armature modifier export verification checks actual weighted deformation after serialization; broken weights or missing skin must fail closed",
            project="tiny3d",
        )
        bridge_replay = self.commit(
            "bridge:replay",
            "Verify animation playback keyframes",
            "playback keyframes and handedness must reproduce the measured solver target; replay drift catches animation state that was never keyed",
            project="tiny3d",
        )
        candidates = [export_seed, replay_seed, generic_seed, weak_seed, bridge_export, bridge_replay]

        packet = _lesson_packet(
            query,
            selected=[export_seed, replay_seed, generic_seed, weak_seed],
            candidates=candidates,
            query_index=None,
            limit=8,
        )

        packet_ids = {item.get("source_event_id") for item in packet.get("items", [])}
        self.assertEqual(packet["authority"], "DERIVED_HISTORICAL_PRIORS_ONLY")
        self.assertEqual(packet["validation"], "SLICE1_RETRIEVAL_ONLY_NOT_VALIDATED")
        self.assertTrue(packet["live_truth_required"])
        self.assertTrue(packet["nonblocking"])
        self.assertLessEqual(len(packet.get("items", [])), 8)
        self.assertIn(export_seed["id"], packet_ids)
        self.assertIn(replay_seed["id"], packet_ids)
        self.assertNotIn(generic_seed["id"], packet_ids)
        self.assertNotIn(weak_seed["id"], packet_ids)

    def test_packet_enforces_hard_8kib_utf8_budget_under_path_pressure(self):
        query = "hummingbird wing deformation"
        seeds = [
            self.commit(
                f"seed:{index}",
                f"Hummingbird wing deformation corrective seed {index}",
                "deformation armature surface weighting replay export correction measured wing geometry skin failure repair "
                "technical evidence establishes a bounded corrective bridge across the rigging task",
            )
            for index in range(4)
        ]
        long_component = "mesh_surface_deformation_evidence_" + ("segment_" * 28)
        bridges = []
        for index in range(10):
            event = self.commit(
                f"bridge:{index}",
                f"Avian deformation corrective evidence {index}",
                "deformation armature surface weighting replay export correction measured wing geometry skin failure repair "
                "technical evidence verifies the same rigging failure with substantive task-relevant measurements",
                project="tiny3d" if index % 2 else "lowvram",
            )
            event["changed_paths"] = [
                f"evidence/{index}/{part}/{long_component}.json" for part in range(6)
            ]
            bridges.append(event)

        packet = _lesson_packet(
            query,
            selected=seeds,
            candidates=[*seeds, *bridges],
            query_index=None,
            limit=8,
        )

        import json

        encoded = json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(encoded), 8192)
        self.assertLessEqual(len(packet.get("items", [])), 8)
        self.assertEqual(packet["authority"], "DERIVED_HISTORICAL_PRIORS_ONLY")
        self.assertTrue(packet["live_truth_required"])


if __name__ == "__main__":
    unittest.main()
