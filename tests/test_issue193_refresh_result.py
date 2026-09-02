import copy
import unittest

from tools.issue193_refresh_result import CANARY_DEFINITIONS, classify, validate_record


CANARIES = copy.deepcopy(CANARY_DEFINITIONS)


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
        "fresh_conversation": True,
        "ordinary_user_continuation_observed": kind == "control",
        "parallel_load_observed": False,
        "prohibited_mutations_observed": False,
        "prohibited_mutation_categories": [],
        "prohibited_methods_observed": False,
        "prohibited_method_categories": [],
        "stop_rule_violated": False,
        "recovery_limit_violated": False,
        "before": sample(before_value, False),
        "after": sample(after_value, refreshed),
    }
    if refreshed:
        value["stimulus"] = "refresh your memory"
    return value


def record(*pairs: dict) -> dict:
    return {"schema_version": 1, "issue": 193, "pairs": list(pairs)}


class Issue193RefreshResultTests(unittest.TestCase):
    def test_requires_exact_contamination_identity(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["prohibited_mutations_observed"] = True
        with self.assertRaisesRegex(ValueError, "must match prohibited_mutation_categories"):
            validate_record(data)

        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["prohibited_mutation_categories"] = ["Settings"]
        with self.assertRaisesRegex(ValueError, "must match prohibited_mutation_categories"):
            validate_record(data)

    def test_rejects_unknown_or_duplicate_contamination_categories(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["prohibited_mutations_observed"] = True
        data["pairs"][0]["prohibited_mutation_categories"] = ["not preregistered"]
        with self.assertRaisesRegex(ValueError, "unknown category"):
            validate_record(data)

        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["prohibited_methods_observed"] = True
        data["pairs"][0]["prohibited_method_categories"] = ["worker creation", "worker creation"]
        with self.assertRaisesRegex(ValueError, "must be unique"):
            validate_record(data)

    def test_named_contamination_remains_inconclusive(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False), pair("treatment", "t2", True, False))
        data["pairs"][1]["prohibited_methods_observed"] = True
        data["pairs"][1]["prohibited_method_categories"] = ["worker creation"]
        self.assertEqual(classify(data), "INCONCLUSIVE")

    def test_parallel_load_is_inconclusive(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False), pair("treatment", "t2", True, False))
        data["pairs"][1]["parallel_load_observed"] = True
        self.assertEqual(classify(data), "INCONCLUSIVE")

    def test_rejects_non_boolean_parallel_load_observed(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["parallel_load_observed"] = "false"
        with self.assertRaisesRegex(ValueError, "parallel_load_observed must be boolean"):
            validate_record(data)

    def test_non_fresh_conversation_is_inconclusive(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False), pair("treatment", "t2", True, False))
        data["pairs"][1]["fresh_conversation"] = False
        self.assertEqual(classify(data), "INCONCLUSIVE")

    def test_rejects_non_boolean_fresh_conversation(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["fresh_conversation"] = "true"
        with self.assertRaisesRegex(ValueError, "fresh_conversation must be boolean"):
            validate_record(data)

    def test_control_continuation_mismatch_is_inconclusive(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False), pair("treatment", "t2", True, False))
        data["pairs"][0]["ordinary_user_continuation_observed"] = False
        self.assertEqual(classify(data), "INCONCLUSIVE")

        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False), pair("treatment", "t2", True, False))
        data["pairs"][1]["ordinary_user_continuation_observed"] = True
        self.assertEqual(classify(data), "INCONCLUSIVE")

    def test_rejects_non_boolean_control_continuation_field(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["ordinary_user_continuation_observed"] = "true"
        with self.assertRaisesRegex(ValueError, "ordinary_user_continuation_observed must be boolean"):
            validate_record(data)

    def test_protocol_violation_is_inconclusive(self):
        data = record(
            pair("control", "c1", True, True),
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        data["pairs"][1]["prohibited_mutations_observed"] = True
        data["pairs"][1]["prohibited_mutation_categories"] = ["Settings"]
        self.assertEqual(classify(data), "INCONCLUSIVE")

    def test_stop_or_recovery_protocol_violation_is_inconclusive(self):
        for field in ("stop_rule_violated", "recovery_limit_violated"):
            with self.subTest(field=field):
                data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False), pair("treatment", "t2", True, False))
                data["pairs"][1][field] = True
                self.assertEqual(classify(data), "INCONCLUSIVE")

    def test_rejects_non_boolean_stop_or_recovery_fields(self):
        for field in ("stop_rule_violated", "recovery_limit_violated"):
            with self.subTest(field=field):
                data = record(pair("control", "c1", True, True))
                data["pairs"][0][field] = "false"
                with self.assertRaisesRegex(ValueError, f"{field} must be boolean"):
                    validate_record(data)

    def test_rejects_non_boolean_protocol_cleanliness_fields(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["prohibited_methods_observed"] = "false"
        with self.assertRaisesRegex(ValueError, "prohibited_methods_observed must be boolean"):
            validate_record(data)

    def test_rejects_boolean_or_float_schema_identity(self):
        for field, invalid_value, message in (
            ("schema_version", True, "schema_version must be integer 1"),
            ("schema_version", 1.0, "schema_version must be integer 1"),
            ("issue", 193.0, "issue must be integer 193"),
        ):
            with self.subTest(field=field, invalid_value=invalid_value):
                data = record(pair("control", "c1", True, True))
                data[field] = invalid_value
                with self.assertRaisesRegex(ValueError, message):
                    validate_record(data)


    def test_rejects_unexpected_structural_fields(self):
        data = record(pair("control", "c1", True, True))
        data["analysis_note"] = "post hoc"
        with self.assertRaisesRegex(ValueError, "unexpected record fields"):
            validate_record(data)

        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["retry_count"] = 1
        with self.assertRaisesRegex(ValueError, "unexpected pair fields"):
            validate_record(data)

        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["operator_note"] = "ignored"
        with self.assertRaisesRegex(ValueError, "after unexpected fields"):
            validate_record(data)

    def test_control_rejects_stimulus_field_even_when_empty(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["stimulus"] = None
        with self.assertRaisesRegex(ValueError, "unexpected pair fields"):
            validate_record(data)

    def test_rejects_non_object_record(self):
        with self.assertRaisesRegex(ValueError, "record must be an object"):
            validate_record([])

    def test_two_independent_treatment_changes_with_stable_control_support_h1(self):
        data = record(
            pair("control", "c1", True, True),
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        self.assertEqual(classify(data), "SUPPORT_H1")

    def test_treatment_schema_loss_is_not_h1_support(self):
        data = record(
            pair("control", "c1", True, True),
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        data["pairs"][2]["after"]["measurements"]["visible_or_discovered_schema"] = False
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

    def test_treatment_without_baseline_schema_is_not_h1_support(self):
        data = record(
            pair("control", "c1", True, True),
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        data["pairs"][2]["before"]["measurements"]["visible_or_discovered_schema"] = False
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

    def test_control_schema_loss_prevents_h1_support(self):
        data = record(
            pair("control", "c1", True, True),
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        data["pairs"][0]["after"]["measurements"]["visible_or_discovered_schema"] = False
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

    def test_unhealthy_control_sibling_route_prevents_h1_support(self):
        data = record(
            pair("control", "c1", True, True),
            pair("treatment", "t1", True, False),
            pair("treatment", "t2", True, False),
        )
        data["pairs"][0]["after"]["measurements"]["sibling_route_health"] = False
        self.assertEqual(classify(data), "REPRODUCTION_ONLY")

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

    def test_rejects_non_object_canary_definition(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["before"]["canaries"]["call_primary"] = "plugin2"
        with self.assertRaisesRegex(ValueError, "canary definitions must be objects"):
            validate_record(data)

    def test_rejects_canary_definition_that_differs_from_preregistration(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["before"]["canaries"]["call_primary"]["max_calls_per_phase"] = 2
        data["pairs"][0]["after"]["canaries"]["call_primary"]["max_calls_per_phase"] = 2
        with self.assertRaisesRegex(ValueError, "match preregistration exactly"):
            validate_record(data)

    def test_rejects_changed_canary_definition_within_pair(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["canaries"]["call_primary"] = {"route": "different"}
        with self.assertRaisesRegex(ValueError, "identical canary definitions"):
            validate_record(data)

    def test_rejects_changed_canary_definition_across_pairs(self):
        data = record(pair("control", "c1", True, True), pair("treatment", "t1", True, False))
        data["pairs"][1]["before"]["canaries"]["call_primary"] = {"route": "alternate"}
        data["pairs"][1]["after"]["canaries"]["call_primary"] = {"route": "alternate"}
        with self.assertRaisesRegex(ValueError, "all pairs must use identical canary definitions"):
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

    def test_rejects_unpreregistered_measurement(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["post_hoc_note"] = True
        with self.assertRaisesRegex(ValueError, "unexpected measurements"):
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

    def test_rejects_matching_local_arrival_without_caller_identity(self):
        data = record(pair("control", "c1", True, True))
        data["pairs"][0]["after"]["measurements"]["caller_id_or_process_id"] = None
        with self.assertRaisesRegex(ValueError, "caller_id_or_process_id is required when matching_local_request_start is true"):
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

    def test_rejects_control_pair_after_treatment_pair(self):
        data = record(pair("treatment", "t1", True, False), pair("control", "c1", True, True))
        with self.assertRaisesRegex(ValueError, "control pairs must precede treatment pairs"):
            validate_record(data)

    def test_control_only_record_is_inconclusive(self):
        data = record(pair("control", "c1", True, True))
        self.assertEqual(classify(data), "INCONCLUSIVE")

    def test_treatment_only_without_binding_change_is_inconclusive(self):
        data = record(pair("treatment", "t1", True, True))
        self.assertEqual(classify(data), "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
