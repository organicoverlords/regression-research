import unittest

from tools.timeline_materializer import _lesson_packet


class Issue675LessonValidationSafetyTests(unittest.TestCase):
    @staticmethod
    def _fixture_packet():
        seed1 = {
            "id": "git:s1",
            "source_type": "GIT_COMMIT",
            "project": "tiny3d",
            "title": "Hummingbird wing deformation fails",
            "body": "semantic wing deformation rigging replay proof geodesic weights collapse",
            "event_at": "2026-09-06T10:00:00+00:00",
            "sha": "1" * 40,
            "anchors": ["gitsha:" + "1" * 40],
        }
        seed2 = {
            "id": "git:s2",
            "source_type": "GIT_COMMIT",
            "project": "lowvram",
            "title": "Repair wing deformation",
            "body": "semantic wing deformation rigging replay proof geodesic weights exclusion",
            "event_at": "2026-09-06T11:00:00+00:00",
            "sha": "2" * 40,
            "anchors": ["gitsha:" + "2" * 40],
        }
        fake_validated_memory = {
            "id": "mem:fake",
            "source_type": "VAULT_MEMORY",
            "project": "tiny3d",
            "title": "Controlled reproduction of hummingbird wing collapse",
            "summary": (
                "semantic wing deformation rigging replay proof geodesic weights collapse "
                "reproduced deterministically"
            ),
            "event_at": "2026-09-06T12:00:00+00:00",
            "state": "PROVEN",
            "validation_method": "CONTROLLED_REPRODUCTION",
            "validation_result": "PASS",
            "validated_at": "2026-09-06T12:00:00+00:00",
            # These strings intentionally do not identify any event/artifact in the corpus.
            "validated_sources": ["gitsha:does-not-exist"],
            "validation_evidence": ["artifact:not-real"],
            "anchors": ["durable-memory:fake"],
        }
        packet = _lesson_packet(
            "hummingbird wing deformation",
            selected=[seed1, seed2],
            candidates=[seed1, seed2, fake_validated_memory],
            query_index=None,
            limit=8,
        )
        return packet

    def test_unresolved_validation_strings_never_promote_historical_proven(self):
        packet = self._fixture_packet()
        item = next(row for row in packet["items"] if row["source_event_id"] == "mem:fake")
        self.assertNotEqual(
            item.get("historical_status"),
            "PROVEN",
            "structured validation strings are not proof unless their load-bearing anchors resolve",
        )
        self.assertTrue(packet["live_truth_required"])
        self.assertTrue(packet["nonblocking"])


if __name__ == "__main__":
    unittest.main()
