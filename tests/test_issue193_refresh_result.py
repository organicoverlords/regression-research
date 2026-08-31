import copy
import unittest

from tools.issue193_refresh_result import classify, validate_record


CANARIES = {
    "discover_primary": {},
    "call_primary": {},
    "discover_alternate": {},
    "call_alternate": {},
    "local_arrival": {},
}


def sample(callable_value: bool, refreshed: bool) -> dict:
    return {
        "canaries": copy.deepcopy(CANARIES),
        "measurements": {
            "visible_or_discovered_schema": True,
            "direct_recipient_callable": callable_value,
            "exact_client_error_class": None if callable_value else "RESOURCE_NOT_FOUND",
            "caller_id_or_process_id": "caller_test",
            "matching_local_request_start": callable_value,
            "sibling_route_health": True,
            "refresh_or_reload_between_samples": refreshed,
        },
    }
def pair(kind: str, conversation_id: str, before_value: bool, after_value: bool) -> dict:
    refreshed = kind == "treatment"
    value = {
        "kind": kind,
        "conversation_id": conversation_id,
        "model": "gpt-5.6",
        "configuration": "thinking",
        "before": sample(before_value, False),
        "after": sample(after_value, refreshed),
    }
    if refreshed:
        value["stimulus"] = "refresh your memory"
    return value


def record(*pairs: dict) -> dict:
    return {"schema_version": 1, "issue": 193, "pairs": list(pairs)}


class Issue193RefreshResultTests(unittest.TestCase):
    def test_two_independent_treatment_changes_with_stable_control_support_h1(self):
        data = record(
            pair("control", "c1", True, True),
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        self.assertEqual(classify(data), "SUPPORT_H1")

    def test_failed_control_does_not_count_as_stable_supporting_control(self):
        data = record(
            pair("control", "c1", False, False),
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

    def test_two_treatment_changes_without_control_are_reproduction_only(self):
        data = record(
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

    def test_single_treatment_change_is_reproduction_only(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False))
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

    def test_treatment_recovery_does_not_support_binding_loss_hypothesis(self):
        data = record(
            pair("control", "c1", True, True),
            pair("treatment", "t1", False, True),
            pair("treatment", "t2", False, True),
        )
        self.assertEqual(classify(data), "WEAKEN_H1")
    def test_rejects_non_object_pair(self):
        data = record([])
        with self.assertRaisesRegex(ValueError, "each pair must be an object"):
            validate_record(data)

    def test_rejects_non_object_canaries(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["before"]["canaries"] = list(CANARIES)
        with self.assertRaisesRegex(ValueError, "before.canaries must be an object"):
            validate_record(data)

    def test_rejects_wrong_stimulus(self):
        data = record(pair("treatment", "t1", True, False))
        data["pairs"][0]["stimulus"] = "refresh memory"
        with self.assertRaisesRegex(ValueError, "stimulus"):
            validate_record(data)

    def test_rejects_duplicate_conversation_ids(self):
        data = record(pair("control", "same", True, True), pair("treatment", "same", True, False))
        with self.assertRaisesRegex(ValueError, "independent"):
            validate_record(data)

    def test_rejects_mixed_models_across_pairs(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False))
        data["pairs"][1]["model"] = "gpt-5.5"
        with self.assertRaisesRegex(ValueError, "same model"):
            validate_record(data)

    def test_accepts_whitespace_variants_of_same_model_and_configuration(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False))
        data["pairs"][1]["model"] = " gpt-5.6 "
        data["pairs"][1]["configuration"] = " thinking "
        self.assertTrue(validate_record(data)["ok"])

    def test_rejects_mixed_configurations_across_pairs(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False))
        data["pairs"][1]["configuration"] = "instant"
        with self.assertRaisesRegex(ValueError, "same configuration"):
            validate_record(data)

    def test_rejects_missing_preregistered_canary(self):
        data = record(pair("control", "c1", True, True))
        del data["pairs"][0]["after"]["canaries"]["local_arrival"]
        with self.assertRaisesRegex(ValueError, "exact preregistered canaries"):
            validate_record(data)

    def test_rejects_non_boolean_measurement(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["direct_recipient_callable"] = "false"
        with self.assertRaisesRegex(ValueError, "direct_recipient_callable must be boolean"):
            validate_record(data)

    def test_rejects_invalid_error_class_type(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["exact_client_error_class"] = []
        with self.assertRaisesRegex(ValueError, "exact_client_error_class"):
            validate_record(data)

    def test_rejects_error_class_when_recipient_is_callable(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["exact_client_error_class"] = "RESOURCE_NOT_FOUND"
        with self.assertRaisesRegex(ValueError, "must be null when direct_recipient_callable is true"):
            validate_record(data)

    def test_rejects_missing_error_class_when_recipient_is_not_callable(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["direct_recipient_callable"] = False
        with self.assertRaisesRegex(ValueError, "must be a non-empty string when direct_recipient_callable is false"):
            validate_record(data)

    def test_rejects_refresh_before_pair_baseline(self):
        data = record(pair("treatment", "t1", True, False))
        data["pairs"][0]["before"]["measurements"]["refresh_or_reload_between_samples"] = True
        with self.assertRaisesRegex(ValueError, "before sample must precede refresh/reload"):
            validate_record(data)

    def test_rejects_missing_caller_identity_measurement(self):
        data = record(pair("control", "c1", True, True))
        del data["pairs"][0]["after"]["measurements"]["caller_id_or_process_id"]
        with self.assertRaisesRegex(ValueError, "missing measurements"):
            validate_record(data)

    def test_rejects_invalid_caller_identity_type(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["caller_id_or_process_id"] = []
        with self.assertRaisesRegex(ValueError, "caller_id_or_process_id"):
            validate_record(data)


    def test_treatment_change_with_unhealthy_sibling_route_is_not_h1_support(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False), pair("treatment", "t2", True, False))
        data["pairs"][2]["after"]["measurements"]["sibling_route_health"] = False
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

    def test_treatment_change_with_matching_local_arrival_is_not_h1_support(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False), pair("treatment", "t2", True, False))
        data["pairs"][2]["after"]["measurements"]["matching_local_request_start"] = True
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

    def test_rejects_whitespace_only_required_metadata(self):
        for field in ("conversation_id", "model", "configuration"):
            with self.subTest(field=field):
                data = record(pair("control", "c1", True, True))
                data["pairs"][0][field] = "   "
                with self.assertRaises(ValueError):
                    validate_record(data)

    def test_rejects_whitespace_variant_duplicate_conversation_ids(self):
        data = record(pair("control", "same", True, True), pair("treatment", " same ", True, False))
        with self.assertRaisesRegex(ValueError, "independent"):
            validate_record(data)

    def test_rejects_whitespace_only_optional_string_measurements_when_present(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["caller_id_or_process_id"] = "   "
        with self.assertRaisesRegex(ValueError, "caller_id_or_process_id"):
            validate_record(data)

        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["direct_recipient_callable"] = False
        data["pairs"][0]["after"]["measurements"]["exact_client_error_class"] = "   "
        with self.assertRaisesRegex(ValueError, "exact_client_error_class"):
            validate_record(data)


if __name__ == "__main__":
    unittest.main()
