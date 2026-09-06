from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TimelineCliIssue675Tests(unittest.TestCase):
    def test_timeline_help_documents_lesson_packet_contract(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "memory_bank.py"), "timeline", "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        help_text = proc.stdout.casefold()
        self.assertIn("lesson_packet", help_text)
        self.assertIn("historical", help_text)
        self.assertIn("bounded", help_text)
        self.assertIn("live", help_text)


if __name__ == "__main__":
    unittest.main()
