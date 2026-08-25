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

    def test_quick_note_cli_accepts_unicode_error(self):
        root=Path(__file__).resolve().parents[1]
        cli=root/"tools"/"memory_bank.py"
        with tempfile.TemporaryDirectory() as d:
            bank=Path(d)/"bank.jsonl"
            text="error: as?dasdnasdnda MCP retry failed"
            p=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"note",text,"--scope","mcp"],cwd=root,text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            created=json.loads(p.stdout)
            self.assertEqual(created["text"],text)
            self.assertEqual(created["scope"],"mcp")
            self.assertEqual(created["state"],"PROVISIONAL")
            self.assertIn("quick-note",created["tags"])
            self.assertIn("error",created["tags"])
            self.assertEqual(len(bank.read_text(encoding="utf-8").splitlines()),1)

    def test_recent_alias_matches_recent_titles(self):
        root=Path(__file__).resolve().parents[1]
        cli=root/"tools"/"memory_bank.py"
        with tempfile.TemporaryDirectory() as d:
            bank=Path(d)/"bank.jsonl"
            subprocess.run([sys.executable,str(cli),"--bank",str(bank),"append","--kind","lesson","--scope","memory","--text","Recent compatibility note","--state","PROVEN"],cwd=root,text=True,capture_output=True,check=True)
            canonical=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"recent-titles"],cwd=root,text=True,capture_output=True,check=True)
            alias=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"recent"],cwd=root,text=True,capture_output=True,check=True)
            self.assertEqual(alias.stdout,canonical.stdout)

if __name__ == "__main__": unittest.main()
