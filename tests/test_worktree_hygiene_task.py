import unittest
from unittest.mock import patch

from tools.worktree_hygiene_task import MAX_AUXILIARY, MAX_DIRTY, classify_health


class WorktreeHygieneTaskTests(unittest.TestCase):
    def test_health_is_healthy_at_bounds(self):
        snapshot = {"auxiliary_count": MAX_AUXILIARY, "dirty_count": MAX_DIRTY}
        self.assertEqual(classify_health(snapshot), "healthy")

    def test_health_degrades_before_large_tail(self):
        self.assertEqual(
            classify_health({"auxiliary_count": MAX_AUXILIARY + 1, "dirty_count": 0}),
            "degraded",
        )
        self.assertEqual(
            classify_health({"auxiliary_count": 0, "dirty_count": MAX_DIRTY + 1}),
            "degraded",
        )


if __name__ == "__main__":
    unittest.main()
