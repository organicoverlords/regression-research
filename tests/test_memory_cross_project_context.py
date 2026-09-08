import unittest

from tools.memory_bank import search_context_memory


class CrossProjectMemoryContextTests(unittest.TestCase):
    @staticmethod
    def entry(ident, *, project, scope, tags, title, text):
        return {
            "id": ident,
            "timestamp": "2026-09-08T10:39:09+03:00",
            "kind": "lesson",
            "scope": scope,
            "tags": tags,
            "title": title,
            "text": text,
            "state": "PROVEN",
            "evidence": ["report:test"],
            "supersedes": [],
            "project": project,
        }

    def test_secondary_structured_project_is_retrievable_without_title_rescoping(self):
        cross = self.entry(
            "cross",
            project="p3",
            scope="p3-tiny3d-visual-camera-retakes",
            tags=["visual-proof", "tiny3d", "camera"],
            title="Saved camera proof settings",
            text="Camera proof can be reused for exact visual review.",
        )
        incidental = self.entry(
            "incidental",
            project="p3",
            scope="p3/build",
            tags=[],
            title="Tiny3D mentioned incidentally in a P3 build note",
            text="Camera proof words are present but this remains a P3-only record.",
        )

        hits = search_context_memory([incidental, cross], "tiny3d proof camera", limit=8)
        self.assertEqual([hit["id"] for hit in hits], ["cross"])


if __name__ == "__main__":
    unittest.main()
