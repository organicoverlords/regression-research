import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from tools.memory_bank import BankError, append_entry, attach_materialized_orientation, load_bank, validate_entry


class MemoryBankValidationTests(unittest.TestCase):
    def valid(self):
        return {
            "id": "mem-20260825-abc123",
            "timestamp": "2026-08-25T11:30:00+03:00",
            "kind": "lesson",
            "scope": "mcp",
            "tags": ["routing", "turvallisuus"],
            "text": "Server non-arrival is distinct from local transport failure.",
            "state": "PROVEN",
            "evidence": ["github:chatgpt-mcp-clean#7"],
            "supersedes": [],
        }

    def test_sensitive_value_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as raw:
            bank = Path(raw) / "bank.jsonl"
            entry = self.valid()
            entry["text"] = "my password is CorrectHorseBatteryStaple123!"
            with self.assertRaisesRegex(BankError, "sensitive memory content rejected before write"):
                append_entry(bank, entry)
            self.assertFalse(bank.exists())

    def test_sensitive_verbatim_source_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as raw:
            bank = Path(raw) / "bank.jsonl"
            entry = self.valid()
            entry.update({
                "tags": ["assistant-recorded", "verbatim-source"],
                "source_messages": ["Bearer abcdefghijklmnopqrstuvwxyz0123456789"],
                "interpretation": "safe summary",
                "confidence": 100,
                "confidence_reason": "test",
            })
            with self.assertRaisesRegex(BankError, "sensitive memory content rejected before write"):
                append_entry(bank, entry)
            self.assertFalse(bank.exists())

    def test_valid_entry_and_utf8(self):
        validate_entry(self.valid())

    def test_missing_required_field_rejected(self):
        e = self.valid(); del e["text"]
        with self.assertRaises(BankError): validate_entry(e)

    def test_invalid_enum_rejected(self):
        e = self.valid(); e["state"] = "MAYBE"
        with self.assertRaises(BankError): validate_entry(e)

    def test_arrays_must_be_string_arrays(self):
        for field in ("tags", "evidence", "supersedes"):
            e = self.valid(); e[field] = [123]
            with self.subTest(field=field), self.assertRaises(BankError): validate_entry(e)

    def test_append_infers_single_project_from_scope(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bank.jsonl"
            created = append_entry(path, {
                "kind": "lesson", "scope": "p3/build", "tags": [],
                "text": "Build rule", "state": "PROVEN", "evidence": [], "supersedes": [],
            })
            self.assertEqual(created["project"], "p3")
            self.assertEqual(load_bank(path)[0]["project"], "p3")

    def test_append_does_not_infer_project_from_body_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bank.jsonl"
            created = append_entry(path, {
                "kind": "lesson", "scope": "global", "tags": [],
                "text": "P3 appears only in this body example", "state": "PROVEN", "evidence": [], "supersedes": [],
            })
            self.assertNotIn("project", created)

    def test_project_and_expiry_validate(self):
        e = self.valid()
        e["project"] = "p3"
        e["expires_at"] = "2099-08-21T10:00:00+03:00"
        validate_entry(e)
        bad = self.valid(); bad["expires_at"] = "2099-08-21T10:00:00"
        with self.assertRaises(BankError): validate_entry(bad)
        bad = self.valid(); bad["project"] = ""
        with self.assertRaises(BankError): validate_entry(bad)

    def test_behavior_rule_is_typed_forensic_metadata_only(self):
        e = self.valid()
        e["kind"] = "fact"
        e["behavior_rule"] = True
        validate_entry(e)
        bad = self.valid()
        bad["behavior_rule"] = "true"
        with self.assertRaises(BankError):
            validate_entry(bad)

    def test_thread_validates_nonempty(self):
        e = self.valid()
        e["thread"] = "incident-family-42"
        validate_entry(e)
        bad = self.valid()
        bad["thread"] = ""
        with self.assertRaises(BankError):
            validate_entry(bad)

    def test_event_at_validates_timezone(self):
        e = self.valid()
        e["event_at"] = "2026-08-28T20:00:00+03:00"
        validate_entry(e)
        bad = self.valid()
        bad["event_at"] = "2026-08-28T20:00:00"
        with self.assertRaises(BankError):
            validate_entry(bad)


    def test_malformed_jsonl_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"; p.write_text('{"id":"x"}\nnot-json\n', encoding="utf-8")
            with self.assertRaises(BankError): load_bank(p)

    def test_duplicate_ids_rejected(self):
        e = self.valid()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text(json.dumps(e)+"\n"+json.dumps(e)+"\n", encoding="utf-8")
            with self.assertRaises(BankError): load_bank(p)

    def test_canonical_load_is_read_only(self):
        e = self.valid()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text(json.dumps(e)+"\n", encoding="utf-8")
            with patch("tools.memory_bank._is_canonical_bank", return_value=True), patch("tools.memory_bank.sync_bank") as sync:
                self.assertEqual(load_bank(p), [e])
            sync.assert_not_called()

    def test_canonical_append_is_local_only_by_default(self):
        values = self.valid()
        values.pop("id")
        values.pop("timestamp")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text("", encoding="utf-8")
            with patch("tools.memory_bank._is_canonical_bank", return_value=True), patch(
                "tools.memory_bank.sync_lock", side_effect=lambda path: nullcontext()
            ), patch("tools.memory_bank._sync_canonical_locked") as sync:
                saved = append_entry(p, values)
            self.assertEqual(saved["text"], values["text"])
            sync.assert_not_called()

    def test_canonical_append_publish_syncs_before_and_after_write(self):
        values = self.valid()
        values.pop("id")
        values.pop("timestamp")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bank.jsonl"
            p.write_text("", encoding="utf-8")
            with patch("tools.memory_bank._is_canonical_bank", return_value=True), patch(
                "tools.memory_bank.sync_lock", side_effect=lambda path: nullcontext()
            ), patch("tools.memory_bank._sync_canonical_locked") as sync:
                saved = append_entry(p, values, publish=True)
            self.assertEqual(saved["text"], values["text"])
            self.assertEqual(sync.call_count, 2)
            self.assertFalse(sync.call_args_list[0].kwargs["strict"])
            self.assertTrue(sync.call_args_list[1].kwargs["strict"])

    def test_assistant_recorded_requires_verbatim_provenance(self):
        e = self.valid()
        e["tags"] = ["assistant-recorded"]
        with self.assertRaises(BankError):
            validate_entry(e)

    def test_assistant_recorded_structured_fields_validate(self):
        e = self.valid()
        e.update({
            "tags": ["assistant-recorded", "verbatim-source"],
            "source_messages": ["and hwat you think it means with like confidence score etc? dunno"],
            "turn_task": "make it permanent that the original actual words are always included in every assistant recorder memory so there is no ambiguity afterwards",
            "interpretation": "Preserve source wording separately from assistant interpretation.",
            "confidence": 98,
            "confidence_reason": "The user stated the desired recorder behavior explicitly across several consecutive turns.",
        })
        validate_entry(e)
        self.assertEqual(e["source_messages"][0], "and hwat you think it means with like confidence score etc? dunno")

    def test_structured_fields_rejected_without_assistant_recorded_tag(self):
        e = self.valid()
        e["source_messages"] = ["exact source"]
        with self.assertRaises(BankError):
            validate_entry(e)



class MemoryBankMaterializedOverviewTests(unittest.TestCase):
    def test_overview_orientation_uses_same_materialized_freshness_and_coverage_contract(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            state = root / ".state" / "timeline"
            state.mkdir(parents=True)
            projection = {
                "schema": "vault.timeline.bootstrap.v1",
                "generated_at": "2026-09-06T05:58:00+00:00",
                "overview": {
                    "timeline_snapshots": {"authority": "DERIVED_HISTORY_ONLY", "windows": [{"window": "24h", "events": 3}]},
                    "timeline_materialized": {
                        "refresh_minutes": 5,
                        "horizon_days": 30,
                        "backfill_incomplete_sources": ["github"],
                    },
                },
            }
            (state / "bootstrap-memory-overview.json").write_text(json.dumps(projection), encoding="utf-8")
            report = {"schema": "memory-bank.overview.v1", "contract": "history only"}
            attach_materialized_orientation(
                report, vault_root=root, now=__import__("datetime").datetime(2026, 9, 6, 6, 0, tzinfo=__import__("datetime").timezone.utc)
            )
        self.assertEqual(report["timeline_materialized"]["status"], "FRESH")
        self.assertEqual(report["timeline_materialized"]["coverage_status"], "HISTORICAL_INCOMPLETE")
        self.assertEqual(report["timeline_materialized"]["absence_semantics"], "NO_MATCH_IS_NOT_PROOF_OF_ABSENCE")
        self.assertEqual(report["timeline_snapshots"]["windows"][0]["window"], "24h")
        self.assertEqual(report["debugging_boundary"]["current_diagnosis"], "VERIFY_THE_OWNING_LIVE_REPO_RUNTIME_SCHEDULER_OR_COORDINATOR")

    def test_missing_materialization_never_becomes_evidence_of_absence(self):
        with tempfile.TemporaryDirectory() as d:
            report = {}
            attach_materialized_orientation(report, vault_root=Path(d))
        self.assertEqual(report["timeline_materialized"]["status"], "MISSING")
        self.assertIn("DO_NOT_INFER_ABSENCE", report["timeline_materialized"]["absence_semantics"])
        self.assertTrue(report["timeline_materialized"]["live_truth_required"])

if __name__ == "__main__": unittest.main()
