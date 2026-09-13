import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import memory_bank


def entry(ident: str, text: str) -> dict:
    return {
        "id": ident,
        "timestamp": "2026-09-12T04:00:00+03:00",
        "kind": "correction",
        "scope": "test",
        "tags": ["test"],
        "text": text,
        "state": "PROVEN",
        "evidence": ["test:evidence"],
        "supersedes": [],
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


class CanonicalOverlayTests(unittest.TestCase):
    def test_explicit_canonical_data_bank_merges_external_local_journal(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            code_bank = root / "code" / "memory" / "memory-bank.jsonl"
            data_root = root / "data" / "vault"
            data_bank = data_root / "memory" / "memory-bank.jsonl"
            local_bank = root / "local" / "memory-bank.local.jsonl"
            write_jsonl(code_bank, [entry("mem-code", "code seed")])
            write_jsonl(data_bank, [entry("mem-seed", "canonical seed")])
            write_jsonl(local_bank, [entry("mem-local", "local journal")])
            with (
                patch.object(memory_bank, "DEFAULT_BANK", code_bank),
                patch.object(memory_bank, "DEFAULT_LOCAL_BANK", local_bank),
                patch.dict(memory_bank.os.environ, {"VAULT_CANONICAL_ROOT": str(data_root)}, clear=False),
            ):
                loaded = memory_bank.load_bank(data_bank)
            self.assertEqual({row["id"] for row in loaded}, {"mem-seed", "mem-local"})

    def test_unrelated_bank_does_not_merge_external_local_journal(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            code_bank = root / "code" / "memory" / "memory-bank.jsonl"
            data_root = root / "data" / "vault"
            unrelated = root / "fixture" / "memory-bank.jsonl"
            local_bank = root / "local" / "memory-bank.local.jsonl"
            write_jsonl(code_bank, [entry("mem-code", "code seed")])
            write_jsonl(unrelated, [entry("mem-fixture", "fixture")])
            write_jsonl(local_bank, [entry("mem-local", "local journal")])
            with (
                patch.object(memory_bank, "DEFAULT_BANK", code_bank),
                patch.object(memory_bank, "DEFAULT_LOCAL_BANK", local_bank),
                patch.dict(memory_bank.os.environ, {"VAULT_CANONICAL_ROOT": str(data_root)}, clear=False),
            ):
                loaded = memory_bank.load_bank(unrelated)
            self.assertEqual([row["id"] for row in loaded], ["mem-fixture"])


if __name__ == "__main__":
    unittest.main()
