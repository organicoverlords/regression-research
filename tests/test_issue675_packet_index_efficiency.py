import unittest
from unittest.mock import patch

import tools.timeline_materializer as tm


class Issue675PacketIndexEfficiencyTests(unittest.TestCase):
    @staticmethod
    def _seed(event_id: str, sha: str, body: str) -> dict:
        return {
            "id": event_id,
            "source_type": "GIT_COMMIT",
            "project": "lowvram",
            "title": "Hummingbird wing deformation investigation",
            "summary": "Hummingbird wing deformation investigation",
            "body": body,
            "event_at": "2026-09-06T10:00:00+00:00",
            "sha": sha,
            "anchors": [f"gitsha:{sha}"],
            "refs": [],
        }

    def test_generation_bound_postings_absence_does_not_rescan_full_corpus_per_seed_term(self):
        seeds = [
            self._seed(
                "git:seed:a",
                "1" * 40,
                "hummingbird wing deformation quaternionalignment manifoldrepair signedvolumecheck topologyislandguard",
            ),
            self._seed(
                "git:seed:b",
                "2" * 40,
                "hummingbird wing deformation quaternionalignment manifoldrepair signedvolumecheck topologyislandguard",
            ),
        ]
        candidates = [*seeds]
        for index in range(300):
            candidates.append({
                "id": f"git:noise:{index}",
                "source_type": "GIT_COMMIT",
                "project": "tiny3d",
                "title": f"Unrelated corrective history {index}",
                "summary": "unrelated rendering cache repair evidence",
                "body": "unrelated rendering cache repair evidence",
                "event_at": "2026-09-06T09:00:00+00:00",
                "sha": f"{index:040x}"[-40:],
                "anchors": [],
                "refs": [],
            })

        # This models the generation-matched sidecar contract: postings cover the
        # complete materialized query corpus. Therefore an absent token has df=0;
        # the packet builder must not re-tokenize every event to rediscover zero.
        query_index = {
            "schema": tm.QUERY_INDEX_SCHEMA,
            "generated_at": "fixture-generation",
            "ids": [event["id"] for event in candidates],
            "postings": {},
            "weight_codes": {},
            "anchors": [[] for _ in candidates],
        }

        original = tm._event_query_fields
        with patch.object(tm, "_event_query_fields", wraps=original) as fields:
            packet = tm._lesson_packet(
                "hummingbird wing deformation",
                selected=seeds,
                candidates=candidates,
                query_index=query_index,
                limit=8,
            )

        self.assertEqual(
            fields.call_count,
            0,
            "generation-bound postings absence is already df=0 and must not trigger per-token full-corpus rescans",
        )
        self.assertEqual(packet["status"], "NO_BRIDGE_TERMS")


if __name__ == "__main__":
    unittest.main()
