import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class MemoryMigrationCliTests(unittest.TestCase):
    def test_direct_script_execution_works(self):
        root=Path(__file__).resolve().parents[1]
        src=root/"tests"/"fixtures"/"memory-candidates.jsonl"
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/"bank.jsonl"
            proc=subprocess.run([sys.executable,str(root/"tools"/"migrate_memory_bank.py"),str(src),str(out)],cwd=root,text=True,capture_output=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertTrue(out.is_file())
            self.assertGreater(len(out.read_text(encoding="utf-8").splitlines()),0)

if __name__ == "__main__": unittest.main()
