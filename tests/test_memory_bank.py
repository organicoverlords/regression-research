import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from tools.memory_bank import BankError, append_entry, load_bank, validate_entry


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

    def test_canonical_append_still_syncs_before_and_after_write(self):
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


if __name__ == "__main__": unittest.main()
