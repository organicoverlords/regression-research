import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class StandaloneRepoSmoke(unittest.TestCase):
    def test_bank_works_from_repo_files_only(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            dst=Path(d)/"repo"; dst.mkdir()
            shutil.copytree(root/"memory",dst/"memory")
            shutil.copytree(root/"tools",dst/"tools")
            p=subprocess.run([sys.executable,str(dst/"tools"/"memory_bank.py"),"search","Chain Lightning","--scope","p3"],cwd=dst,text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            hits=json.loads(p.stdout)
            self.assertTrue(hits)
            self.assertIn("Chain Lightning",hits[0]["text"])

if __name__ == "__main__": unittest.main()
