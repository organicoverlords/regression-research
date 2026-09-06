from __future__ import annotations

import unittest

from tools.timeline_materializer import _lesson_packet


class Issue675Slice1HummingbirdPacketTests(unittest.TestCase):
    @staticmethod
    def commit(event_id: str, title: str, body: str) -> dict:
        return {
            "id": event_id,
            "source_type": "GIT_COMMIT",
            "authority": "REPO_HISTORY",
            "project": "lowvram",
            "projects": ["lowvram"],
            "event_at": "2026-08-20T12:00:00+03:00",
            "title": title,
            "summary": title,
            "body": body,
            "sha": (event_id.split(":")[-1] + "a" * 40)[:40],
            "anchors": [],
            "refs": [],
        }

    def test_public_packet_matches_slice1_hummingbird_acceptance_contract(self):
        query = "hummingbird wing deformation"
        task_seed = {
            "id": "worker:hummingbird-current",
            "source_type": "WORKER_REPORT",
            "authority": "DERIVED_WORKER_HISTORY",
            "project": "tiny3d",
            "projects": ["tiny3d"],
            "event_at": "2026-09-06T20:00:00+03:00",
            "title": "Hummingbird wing deformation qualification",
            "summary": "Current Hummingbird wing deformation task",
            "findings": (
                "Inspect rig skin weights, surface geodesic topology, export replay, wrong-limb proof, "
                "semantic region cross-wing leakage, and animation deformation."
            ),
            "anchors": [],
            "refs": [],
        }
        semantic = self.commit(
            "git:lowvram:semantic",
            "Semantic region ownership blocks cross-wing leakage",
            "Semantic region segmentation excludes opposite wing and wrong-limb bones so cross-wing "
            "weight leakage and bleed cannot occur through spatial proximity.",
        )
        geodesic = self.commit(
            "git:lowvram:geodesic",
            "Use surface geodesic weighting over raw proximity",
            "Surface geodesic distance follows mesh connectivity instead of raw spatial proximity or distance "
            "thresholds. Weld UV seam topology first so traversal does not stop at duplicated seam vertices.",
        )
        export = self.commit(
            "git:lowvram:export",
            "Validate exported replayed animation",
            "Exported animation must be replayed from the actual action and frames; a solved pose or render can "
            "disagree with replayed deformation.",
        )
        wrong_limb = self.commit(
            "git:lowvram:wrong",
            "Wrong-limb visual proof can be a false pass",
            "A wrong limb or wing can make visual proof look plausible; later full deformation evidence rejected "
            "the false pass.",
        )
        packet = _lesson_packet(
            query,
            selected=[task_seed],
            candidates=[task_seed, semantic, geodesic, export, wrong_limb],
            query_index=None,
            limit=8,
        )

        self.assertIn("HISTORICAL", str(packet.get("authority", "")).upper())
        self.assertTrue(packet.get("bounded"))
        self.assertLessEqual(len(packet.get("items", [])), 8)
        live_truth = str(packet.get("live_truth") or "").casefold()
        self.assertIn("live", live_truth)
        self.assertTrue("verify" in live_truth or "continue" in live_truth)
        warnings = " ".join(str(value) for value in packet.get("warnings", []) or []).casefold()
        self.assertTrue("nonblock" in warnings or "non-block" in warnings or "continue" in live_truth)

        item_text = [
            " ".join(
                str(item.get(key) or "")
                for key in (
                    "conclusion",
                    "historical_prior",
                    "title",
                    "summary",
                    "rejected_or_disproven_approach",
                )
            ).casefold()
            for item in packet.get("items", [])
        ]
        self.assertTrue(any(("semantic" in text or "region" in text) and ("wing" in text or "limb" in text) for text in item_text))
        self.assertTrue(any(("surface" in text or "geodesic" in text) and ("proximity" in text or "distance" in text) for text in item_text))
        self.assertTrue(any(("weld" in text) and ("uv" in text or "seam" in text or "topology" in text) for text in item_text))
        self.assertTrue(any(("export" in text or "replay" in text) and ("animation" in text or "pose" in text or "action" in text) for text in item_text))
        self.assertTrue(any(("wrong" in text or "false" in text or "rejected" in text) and ("limb" in text or "wing" in text or "proof" in text) for text in item_text))
        self.assertNotIn(task_seed["id"], {item.get("source_event_id") for item in packet.get("items", [])})


if __name__ == "__main__":
    unittest.main()
