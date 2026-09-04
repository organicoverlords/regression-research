import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class StandaloneRepoSmoke(unittest.TestCase):
    def test_bank_works_from_repo_files_only(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d) / "repo"
            dst.mkdir()
            shutil.copytree(root / "memory", dst / "memory")
            shutil.copytree(root / "tools", dst / "tools")

            env = os.environ.copy()
            env["MEMORY_VAULT_ROOT"] = str(dst)
            ordinary = subprocess.run(
                [sys.executable, str(dst / "tools" / "memory_bank.py"), "search", "Chain Lightning", "--scope", "p3"],
                cwd=dst, text=True, encoding="utf-8", capture_output=True, env=env,
            )
            self.assertEqual(ordinary.returncode, 0, ordinary.stderr)
            ordinary_hits = json.loads(ordinary.stdout)
            self.assertFalse(any(hit["id"] == "mem-20260825-chain-lightning" for hit in ordinary_hits))

            history = subprocess.run(
                [sys.executable, str(dst / "tools" / "memory_bank.py"), "search", "Chain Lightning", "--scope", "p3", "--history"],
                cwd=dst, text=True, encoding="utf-8", capture_output=True, env=env,
            )
            self.assertEqual(history.returncode, 0, history.stderr)
            history_hits = json.loads(history.stdout)
            self.assertTrue(any(hit["id"] == "mem-20260825-chain-lightning" for hit in history_hits))


if __name__ == "__main__":
    unittest.main()
