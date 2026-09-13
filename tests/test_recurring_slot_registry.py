import tempfile
import unittest
from pathlib import Path

from tools.recurring_slot_registry import (
    RECURRING_WORKER_SLOTS,
    bind_slot,
    clear_slot,
    load_slot_snapshot,
    reconcile_partition,
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

    def test_reconcile_partition_atomically_replaces_all_slots_and_preserves_other_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(1, 6):
                self.assertTrue(bind_slot(f"S1/{index}", str(index) * 32, label=f"Old S1 {index}", root=root)["ok"])
                self.assertTrue(bind_slot(f"S2/{index}", chr(96 + index) * 32, label=f"S2 {index}", root=root)["ok"])
            before = load_slot_snapshot(root)
            s2_before = {
                slot_id: before["bindings_by_slot"][slot_id]
                for slot_id in RECURRING_WORKER_SLOTS["S2"]
            }
            replacement_ids = ("6", "7", "8", "9", "f")
            desired = {
                f"S1/{index}": {
                    "automation_id": replacement_ids[index - 1] * 32,
                    "label": f"New S1 {index}",
                }
                for index in range(1, 6)
            }
            result = reconcile_partition(
                "S1",
                desired,
                expected_updated_at=before["updated_at"],
                root=root,
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "PARTITION_RECONCILED")
            after = load_slot_snapshot(root)
            self.assertEqual(after["partitions"]["S1"]["bound_count"], 5)
            self.assertEqual(after["bound_count"], 10)
            self.assertEqual(
                {slot_id: after["bindings_by_slot"][slot_id] for slot_id in RECURRING_WORKER_SLOTS["S2"]},
                s2_before,
            )
            for slot_id, expected in desired.items():
                self.assertEqual(after["bindings_by_slot"][slot_id]["automation_id"], expected["automation_id"])
                self.assertEqual(after["bindings_by_slot"][slot_id]["label"], expected["label"])

    def test_reconcile_partition_rejects_partial_snapshot_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(bind_slot("S1/1", "1" * 32, root=root)["ok"])
            before = load_slot_snapshot(root)
            result = reconcile_partition(
                "S1",
                {"S1/1": {"automation_id": "2" * 32}},
                expected_updated_at=before["updated_at"],
                root=root,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "PARTITION_BINDINGS_INCOMPLETE")
            self.assertEqual(load_slot_snapshot(root)["updated_at"], before["updated_at"])
            self.assertEqual(load_slot_snapshot(root)["bindings_by_slot"]["S1/1"]["automation_id"], "1" * 32)

    def test_reconcile_partition_requires_compare_and_swap_for_existing_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(bind_slot("S1/1", "1" * 32, root=root)["ok"])
            desired = {
                f"S1/{index}": {"automation_id": str(index) * 32}
                for index in range(1, 6)
            }
            result = reconcile_partition("S1", desired, root=root)
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "EXPECTED_UPDATED_AT_REQUIRED")

    def test_reconcile_partition_rejects_stale_compare_and_swap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(bind_slot("S1/1", "1" * 32, root=root)["ok"])
            stale_updated_at = load_slot_snapshot(root)["updated_at"]
            self.assertTrue(bind_slot("S2/1", "a" * 32, root=root)["ok"])
            desired = {
                f"S1/{index}": {"automation_id": str(index) * 32}
                for index in range(1, 6)
            }
            result = reconcile_partition(
                "S1",
                desired,
                expected_updated_at=stale_updated_at,
                root=root,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "REGISTRY_CHANGED_BEFORE_RECONCILE")

    def test_reconcile_partition_rejects_cross_partition_automation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shared_id = "a" * 32
            self.assertTrue(bind_slot("S2/1", shared_id, root=root)["ok"])
            before = load_slot_snapshot(root)
            desired = {
                f"S1/{index}": {"automation_id": (shared_id if index == 1 else str(index) * 32)}
                for index in range(1, 6)
            }
            result = reconcile_partition(
                "S1",
                desired,
                expected_updated_at=before["updated_at"],
                root=root,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status"], "AUTOMATION_BOUND_CROSS_PARTITION")

    def test_topology_has_exactly_five_stable_slots_per_partition(self):
        self.assertEqual(tuple(RECURRING_WORKER_SLOTS), ("S1", "S2"))
        self.assertEqual(RECURRING_WORKER_SLOTS["S1"], ("S1/1", "S1/2", "S1/3", "S1/4", "S1/5"))
        self.assertEqual(RECURRING_WORKER_SLOTS["S2"], ("S2/1", "S2/2", "S2/3", "S2/4", "S2/5"))


if __name__ == "__main__":
    unittest.main()
