import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "issue193_refresh_result.py"

class Issue193RefreshResultCliTests(unittest.TestCase):
    def run_tool(self, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(TOOL), str(path)], cwd=ROOT, text=True, capture_output=True, check=False)

    def test_malformed_json_returns_structured_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not-json", encoding="utf-8")
            proc = self.run_tool(path)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["error"])

    def test_missing_record_returns_structured_error(self):
        path = ROOT / "tests" / "fixtures" / "does-not-exist-issue193.json"
        proc = self.run_tool(path)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stderr, "")
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["error"])

if __name__ == "__main__":
    unittest.main()
