import tempfile
import unittest
from pathlib import Path

from tools.recurring_slot_registry import (
    RECURRING_WORKER_SLOTS,
    bind_slot,
    clear_slot,
    load_slot_snapshot,
)


class RecurringSlotRegistryTests(unittest.TestCase):
    def test_missing_registry_is_non_alert_unbound_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = load_slot_snapshot(Path(tmp))
        self.assertEqual(snapshot["status"], "MISSING")
        self.assertEqual(snapshot["bound_count"], 0)
        self.assertEqual(snapshot["slot_capacity_total"], 10)
        self.assertIn("not_worker_liveness_failure", snapshot["semantics"])

    def test_bind_replace_and_clear_preserve_slot_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_id = "1" * 32
            new_id = "2" * 32
            first = bind_slot("S1/1", old_id, label="Old name", root=root)
            self.assertTrue(first["ok"])
            occupied = bind_slot("S1/1", new_id, label="New name", root=root)
            self.assertFalse(occupied["ok"])
            self.assertEqual(occupied["status"], "SLOT_OCCUPIED")
            replaced = bind_slot("S1/1", new_id, label="New name", replace_current=True, root=root)
            self.assertTrue(replaced["ok"])
            snapshot = load_slot_snapshot(root)
            self.assertEqual(snapshot["bindings_by_slot"]["S1/1"]["automation_id"], new_id)
            self.assertEqual(snapshot["automation_to_slot"][new_id], "S1/1")
            self.assertNotIn(old_id, snapshot["automation_to_slot"])
            cleared = clear_slot("S1/1", expected_automation_id=new_id, root=root)
            self.assertTrue(cleared["ok"])
            self.assertIsNone(load_slot_snapshot(root)["bindings_by_slot"]["S1/1"])

    def test_same_automation_cannot_bind_two_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            automation_id = "a" * 32
            self.assertTrue(bind_slot("S2/1", automation_id, root=root)["ok"])
            duplicate = bind_slot("S2/2", automation_id, root=root)
            self.assertFalse(duplicate["ok"])
            self.assertEqual(duplicate["status"], "AUTOMATION_ALREADY_BOUND")

    def test_topology_has_exactly_five_stable_slots_per_partition(self):
        self.assertEqual(tuple(RECURRING_WORKER_SLOTS), ("S1", "S2"))
        self.assertEqual(RECURRING_WORKER_SLOTS["S1"], ("S1/1", "S1/2", "S1/3", "S1/4", "S1/5"))
        self.assertEqual(RECURRING_WORKER_SLOTS["S2"], ("S2/1", "S2/2", "S2/3", "S2/4", "S2/5"))


if __name__ == "__main__":
    unittest.main()
