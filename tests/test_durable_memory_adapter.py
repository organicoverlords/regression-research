import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.durable_memory_adapter import adapt_export, adapt_record, load_export, MAX_DURABLE_CANDIDATES
from tools.memory_bank import validate_entry, search_entries, source_relevance

FIXTURE = Path("tests/fixtures/durable-memory-export.jsonl")


def _records(path: Path = FIXTURE):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class DurableMemoryAdapterTests(unittest.TestCase):
    def test_imports_bounded_fixture_preserves_provenance_and_skips_sensitive_unsupported(self):
        candidates = adapt_export(_records())
        ids = {c["id"] for c in candidates}
        # keeps stable non-sensitive
        texts = {c["text"] for c in candidates}
        self.assertIn("Prefers concise, direct responses with checkable proof.", texts)
        self.assertIn("User is executive; assistant owns planning and verification.", texts)
        # provenance preserved
        for c in candidates:
            self.assertEqual(c["source_class"], "DURABLE_MEMORY")
            self.assertTrue(c["source_id"])
            self.assertTrue(c["source_timestamp"])
            self.assertTrue(any(e.startswith("durable-memory:export:") for e in c["evidence"]))
            validate_entry({k: c[k] for k in ("id", "timestamp", "kind", "scope", "tags", "text", "state", "evidence", "supersedes")})
        # sensitive/unsupported skipped — must never leak into candidate bank
        leaked = " ".join(c["text"] for c in candidates)
        self.assertNotIn("123-45-6789", leaked)
        self.assertNotIn("joonas@example.com", leaked)
        self.assertNotIn("api_key", leaked.lower())
        self.assertNotIn("Transient debug token", leaked)
        self.assertEqual(len([c for c in candidates if c["text"] == "ok"]), 0)
        self.assertEqual(len(candidates), 4)  # 3 stable + 1 oversized truncated

    def test_oversized_signal_is_truncated_to_2000(self):
        candidates = adapt_export(_records())
        oversized = next(c for c in candidates if "Repeating to push" in c["text"])
        self.assertLessEqual(len(oversized["text"]), 2000)
        self.assertGreater(len(oversized["text"]), 400)

    def test_is_deterministic(self):
        a = adapt_export(_records())
        b = adapt_export(_records())
        self.assertEqual(a, b)
        # explicit id stability per text/kind/evidence
        r = {"id": "x", "kind": "preference", "text": "Prefers concise responses.", "timestamp": "2026-08-25T10:00:00+03:00"}
        first = adapt_record(r, source_id="chatgpt-personal-context", export_name="export", index=0)
        second = adapt_record(r, source_id="chatgpt-personal-context", export_name="export", index=0)
        self.assertEqual(first["id"], second["id"])

    def test_bounded_import_caps_at_fifty(self):
        many = [{"id": f"m{i}", "kind": "preference", "text": f"Stable preference number {i} with enough words to be durable."} for i in range(120)]
        out = adapt_export(many)
        self.assertEqual(len(out), MAX_DURABLE_CANDIDATES)
        self.assertEqual(len(out), 50)

    def test_optional_when_surface_unavailable(self):
        missing = Path(tempfile.gettempdir()) / "no-such-durable-export-xyz.jsonl"
        if missing.exists():
            missing.unlink()
        self.assertEqual(load_export(missing), [])
        # CLI also succeeds with missing input
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out.jsonl"
            proc = subprocess.run([sys.executable, "tools/durable_memory_adapter.py", str(missing), str(out)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "")
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["candidates"], 0)

    def test_cli_is_byte_deterministic_and_never_exposes_sensitive(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "a.jsonl", Path(td) / "b.jsonl"
            for output in (a, b):
                subprocess.run([sys.executable, "tools/durable_memory_adapter.py", str(FIXTURE), str(output)],
                               check=True, capture_output=True, text=True)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            records = [json.loads(line) for line in a.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(records), 4)
            leaked = " ".join(r["text"] for r in records)
            self.assertNotIn("example.com", leaked)
            self.assertNotIn("123-45-6789", leaked)

    def test_current_explicit_instruction_wins_over_durable_memory(self):
        durable = adapt_export([{"id": "d1", "kind": "preference", "text": "Prefers verbose responses.", "timestamp": "2026-08-25T10:00:00+03:00"}])
        self.assertEqual(durable[0]["source_class"], "DURABLE_MEMORY")
        current = {"id": "current-pref", "timestamp": "2026-08-25T11:00:00+03:00", "kind": "preference",
                   "scope": "global", "tags": ["tone"], "text": "Prefers verbose responses.",
                   "state": "PROVEN", "evidence": ["user-instruction:2026-08-25"], "supersedes": []}
        hits = search_entries(durable + [current], "Prefers verbose responses", limit=5)
        self.assertEqual(hits[0]["id"], "current-pref")
        self.assertGreater(source_relevance(current), source_relevance(durable[0]))

    def test_no_startup_dependency(self):
        # importing and searching the bank works without any durable export file
        from tools.memory_bank import load_bank, search_entries as s
        bank = load_bank(Path("memory/memory-bank.jsonl"))
        # should not raise, even if adapter never ran
        hits = s(bank, "MCP routing")
        self.assertIsInstance(hits, list)

    def test_supports_json_array_input(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "array.json"
            src.write_text(json.dumps([{"id": "a1", "kind": "fact", "text": "Stable fact for array input with enough words."}]),
                           encoding="utf-8")
            out = Path(td) / "out.jsonl"
            proc = subprocess.run([sys.executable, "tools/durable_memory_adapter.py", str(src), str(out)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            recs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["source_class"], "DURABLE_MEMORY")


if __name__ == "__main__":
    unittest.main()
