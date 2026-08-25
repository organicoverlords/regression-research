import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class MemoryCliTests(unittest.TestCase):
    def test_append_and_history_cli(self):
        root=Path(__file__).resolve().parents[1]
        cli=root/"tools"/"memory_bank.py"
        with tempfile.TemporaryDirectory() as d:
            bank=Path(d)/"bank.jsonl"
            cmd=[sys.executable,str(cli),"--bank",str(bank),"append","--kind","lesson","--scope","mcp","--tag","routing","--text","Investigate first.","--state","PROVEN","--evidence","issue:7"]
            p=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            created=json.loads(p.stdout)
            self.assertEqual(created["scope"],"mcp")
            h=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"history","routing"],cwd=root,text=True,capture_output=True)
            self.assertEqual(h.returncode,0,h.stderr)
            self.assertEqual(json.loads(h.stdout)[0]["text"],"Investigate first.")

if __name__ == "__main__": unittest.main()
