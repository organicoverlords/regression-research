import copy
import unittest

from tools.issue174_sample_guard import PILOT, TRANCHE2, load_rows, summarize, validate_samples


class Issue174SampleGuardTests(unittest.TestCase):
    def setUp(self):
        self.pilot = load_rows(PILOT)
        self.tranche2 = load_rows(TRANCHE2)

    def test_committed_samples_validate_and_preserve_reported_denominators(self):
        validate_samples(self.pilot, self.tranche2)
        combined = summarize(self.pilot + self.tranche2)
        self.assertEqual(combined["ALL"], {"episodes": 48, "mistakes": 10, "controls": 10, "no_clear_mistake": 28})
        self.assertEqual((combined["GEN"]["episodes"], combined["GEN"]["mistakes"]), (24, 7))
        self.assertEqual((combined["UE"]["episodes"], combined["UE"]["mistakes"]), (24, 3))

    def test_duplicate_episode_across_tranches_is_rejected(self):
        tranche2 = copy.deepcopy(self.tranche2)
        tranche2[0]["conversation_id"] = self.pilot[0]["conversation_id"]
        tranche2[0]["user_index"] = self.pilot[0]["user_index"]
        with self.assertRaisesRegex(ValueError, "duplicate episode keys"):
            validate_samples(self.pilot, tranche2)

    def test_duplicate_pilot_sample_id_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        pilot[1]["sample_id"] = pilot[0]["sample_id"]
        with self.assertRaisesRegex(ValueError, "pilot sample_id values must be unique"):
            validate_samples(pilot, self.tranche2)

    def test_duplicate_tranche2_sample_id_is_rejected(self):
        tranche2 = copy.deepcopy(self.tranche2)
        tranche2[1]["sample2_id"] = tranche2[0]["sample2_id"]
        with self.assertRaisesRegex(ValueError, "tranche2 sample2_id values must be unique"):
            validate_samples(self.pilot, tranche2)

    def test_out_of_domain_sample_id_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        pilot[0]["sample_id"] = "25"
        with self.assertRaisesRegex(ValueError, "pilot sample_id values must remain frozen at 1..24"):
            validate_samples(pilot, self.tranche2)

    def test_missing_sample_id_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        pilot[0]["sample_id"] = ""
        with self.assertRaisesRegex(ValueError, "pilot sample_id is required"):
            validate_samples(pilot, self.tranche2)

    def test_missing_pilot_provenance_file_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        pilot[0]["source_snapshot_file"] = ""
        with self.assertRaisesRegex(ValueError, "pilot source_snapshot_file is required"):
            validate_samples(pilot, self.tranche2)

    def test_missing_tranche2_provenance_file_is_rejected(self):
        tranche2 = copy.deepcopy(self.tranche2)
        tranche2[0]["local_sample_file"] = ""
        with self.assertRaisesRegex(ValueError, "tranche2 local_sample_file is required"):
            validate_samples(self.pilot, tranche2)

    def test_missing_coded_column_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        pilot[0].pop("source_snapshot_file")
        with self.assertRaisesRegex(ValueError, "coded schema drift"):
            validate_samples(pilot, self.tranche2)

    def test_unexpected_coded_column_is_rejected(self):
        tranche2 = copy.deepcopy(self.tranche2)
        tranche2[0]["reviewer_note"] = "not part of the frozen coding schema"
        with self.assertRaisesRegex(ValueError, "coded schema drift"):
            validate_samples(self.pilot, tranche2)

    def test_mistake_requires_counterfactual(self):
        pilot = copy.deepcopy(self.pilot)
        row = next(row for row in pilot if row["coding_status"] == "MISTAKE")
        row["counterfactual"] = ""
        with self.assertRaisesRegex(ValueError, "require failure_class and counterfactual"):
            validate_samples(pilot, self.tranche2)

    def test_non_mistake_cannot_carry_failure_scoring(self):
        pilot = copy.deepcopy(self.pilot)
        row = next(row for row in pilot if row["coding_status"] == "NO_CLEAR_MISTAKE")
        row["severity_1_3"] = "2"
        with self.assertRaisesRegex(ValueError, "must leave severity_1_3 empty"):
            validate_samples(pilot, self.tranche2)

    def test_control_requires_explicit_control_rationale(self):
        pilot = copy.deepcopy(self.pilot)
        row = next(row for row in pilot if row["coding_status"] == "CONTROL")
        row["rationale"] = "route behaved correctly"
        with self.assertRaisesRegex(ValueError, "CONTROL rationale"):
            validate_samples(pilot, self.tranche2)

    def test_whitespace_only_sample_id_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        pilot[0]["sample_id"] = "   "
        with self.assertRaisesRegex(ValueError, "pilot sample_id is required"):
            validate_samples(pilot, self.tranche2)

    def test_whitespace_only_provenance_is_rejected(self):
        tranche2 = copy.deepcopy(self.tranche2)
        tranche2[0]["local_sample_file"] = " \t "
        with self.assertRaisesRegex(ValueError, "tranche2 local_sample_file is required"):
            validate_samples(self.pilot, tranche2)

    def test_whitespace_only_counterfactual_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        row = next(row for row in pilot if row["coding_status"] == "MISTAKE")
        row["counterfactual"] = "   "
        with self.assertRaisesRegex(ValueError, "require failure_class and counterfactual"):
            validate_samples(pilot, self.tranche2)

    def test_whitespace_only_rationale_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        pilot[0]["rationale"] = "   "
        with self.assertRaisesRegex(ValueError, "rationale is required"):
            validate_samples(pilot, self.tranche2)

    def test_zero_user_index_is_rejected(self):
        pilot = copy.deepcopy(self.pilot)
        pilot[0]["user_index"] = "0"
        with self.assertRaisesRegex(ValueError, "user_index must be between 1 and 1000000000"):
            validate_samples(pilot, self.tranche2)

    def test_tranche2_seed_is_frozen(self):
        tranche2 = copy.deepcopy(self.tranche2)
        tranche2[0]["seed"] = "1743"
        with self.assertRaisesRegex(ValueError, "seed must remain frozen"):
            validate_samples(self.pilot, tranche2)


if __name__ == "__main__":
    unittest.main()
