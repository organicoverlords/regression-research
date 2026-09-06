import unittest

from tools.timeline_materializer import _lesson_packet


class Issue675StaticProofSafetyTests(unittest.TestCase):
    @staticmethod
    def _commit(event_id: str, sha: str, title: str) -> dict:
        return {
            "id": event_id,
            "source_type": "GIT_COMMIT",
            "project": "p3",
            "title": title,
            "summary": title,
            "body": (
                "p3 animation temporal runtime proof playback keyframes motion static frame "
                "rendered evidence verifier acceptance"
            ),
            "event_at": "2026-09-06T10:00:00+00:00",
            "sha": sha,
            "anchors": [f"gitsha:{sha}"],
            "refs": [],
        }

    def test_static_artifact_cannot_validate_temporal_runtime_animation_claim(self):
        seed_a = self._commit("git:p3:seed-a", "1" * 40, "Reject static animation proof")
        seed_b = self._commit("git:p3:seed-b", "2" * 40, "Require temporal runtime playback evidence")
        static_frame = {
            "id": "artifact:p3:static-frame",
            "source_type": "TRACKED_ARTIFACT",
            "project": "p3",
            "title": "Animation acceptance screenshot",
            "summary": "single static rendered frame with animation metadata",
            "event_at": "2026-09-06T11:00:00+00:00",
            "artifact_type": "screenshot",
            "evidence_type": "STATIC_IMAGE",
            "path": "02 Evidence/p3/static-animation-proof.png",
            "anchors": ["artifact:02 Evidence/p3/static-animation-proof.png"],
            "refs": [],
        }
        claimed_runtime_success = {
            "id": "mem:p3:static-proves-runtime",
            "source_type": "VAULT_MEMORY",
            "project": "p3",
            "title": "P3 animation runtime playback is proven",
            "summary": (
                "p3 animation temporal runtime proof playback keyframes motion rendered evidence "
                "accepted from one static frame"
            ),
            "event_at": "2026-09-06T12:00:00+00:00",
            "state": "PROVEN",
            "validation_method": "CONTROLLED_REPRODUCTION",
            "validation_result": "PASS",
            "validated_at": "2026-09-06T12:00:00+00:00",
            "validated_sources": [static_frame["id"]],
            "validation_evidence": [static_frame["anchors"][0]],
            "validation_note": "A single screenshot exists after a successful animation-related build.",
            "anchors": ["durable-memory:p3-static-runtime"],
        }

        packet = _lesson_packet(
            "P3 static animation proof temporal runtime evidence",
            selected=[seed_a, seed_b],
            candidates=[seed_a, seed_b, static_frame, claimed_runtime_success],
            query_index=None,
            limit=8,
        )
        item = next(
            row for row in packet["items"]
            if row.get("source_event_id") == claimed_runtime_success["id"]
        )
        self.assertNotEqual(
            item.get("historical_status"),
            "PROVEN",
            "a static image/build-adjacent artifact cannot validate a temporal runtime animation conclusion",
        )
        self.assertTrue(packet["live_truth_required"])
        self.assertTrue(packet["nonblocking"])


if __name__ == "__main__":
    unittest.main()
