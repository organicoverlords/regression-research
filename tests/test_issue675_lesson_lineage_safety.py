import unittest

from tools.timeline_materializer import _lesson_packet


class Issue675LessonLineageSafetyTests(unittest.TestCase):
    @staticmethod
    def _commit(event_id: str, sha: str, patch_id: str, title: str, body: str) -> dict:
        return {
            "id": event_id,
            "source_type": "GIT_COMMIT",
            "project": "tiny3d",
            "title": title,
            "summary": title,
            "body": body,
            "event_at": "2026-09-06T10:00:00+00:00",
            "sha": sha,
            "patch_id": patch_id,
            "anchors": [f"gitsha:{sha}"],
            "refs": [],
        }

    def test_equivalent_commit_lineage_cannot_count_as_independent_corroboration(self):
        seed_a = self._commit(
            "git:seed:a",
            "1" * 40,
            "seed-a",
            "Hummingbird wing deformation failure",
            "semantic wing deformation rigging replay proof geodesic weights collapse",
        )
        seed_b = self._commit(
            "git:seed:b",
            "2" * 40,
            "seed-b",
            "Repair hummingbird deformation",
            "semantic wing deformation rigging replay proof geodesic weights exclusion",
        )
        # Different SHAs/refs, but one implementation lineage: same patch-id and same
        # substantive change. Evidence form/count must not manufacture independence.
        copy_a = self._commit(
            "git:copy:a",
            "a" * 40,
            "equivalent-fix-patch",
            "Fix avian wing weighting",
            "surface geodesic wing weights avoid semantic cross-limb deformation",
        )
        copy_b = self._commit(
            "git:copy:b",
            "b" * 40,
            "equivalent-fix-patch",
            "Cherry-pick avian wing weighting fix",
            "surface geodesic wing weights avoid semantic cross-limb deformation",
        )
        memory = {
            "id": "mem:copied-lineage",
            "source_type": "VAULT_MEMORY",
            "project": "tiny3d",
            "title": "Independent corroboration of hummingbird wing repair",
            "summary": (
                "semantic wing deformation rigging replay proof geodesic weights "
                "collapse reproduced across two commit references"
            ),
            "event_at": "2026-09-06T12:00:00+00:00",
            "state": "PROVEN",
            "validation_method": "INDEPENDENT_CORROBORATION",
            "validation_result": "PASS",
            "validated_at": "2026-09-06T12:00:00+00:00",
            "validated_sources": [copy_a["id"], copy_b["id"]],
            "validation_evidence": [f"gitsha:{copy_a['sha']}", f"gitsha:{copy_b['sha']}"],
            "anchors": ["durable-memory:copied-lineage"],
        }

        packet = _lesson_packet(
            "hummingbird wing deformation",
            selected=[seed_a, seed_b],
            candidates=[seed_a, seed_b, copy_a, copy_b, memory],
            query_index=None,
            limit=8,
        )
        item = next(row for row in packet["items"] if row["source_event_id"] == memory["id"])
        self.assertNotEqual(
            item.get("historical_status"),
            "PROVEN",
            "two refs from one patch/evidence lineage are not independent corroboration",
        )
        self.assertTrue(packet["live_truth_required"])
        self.assertTrue(packet["nonblocking"])


if __name__ == "__main__":
    unittest.main()
