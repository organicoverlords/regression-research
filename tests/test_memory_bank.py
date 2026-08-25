import json
import tempfile
import unittest
from pathlib import Path

from tools.memory_bank import BankError, load_bank, validate_entry


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


if __name__ == "__main__": unittest.main()
