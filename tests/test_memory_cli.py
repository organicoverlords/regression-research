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

    def test_correction_requires_supersedes_or_explicit_standalone(self):
        root=Path(__file__).resolve().parents[1]
        cli=root/"tools"/"memory_bank.py"
        with tempfile.TemporaryDirectory() as d:
            bank=Path(d)/"bank.jsonl"
            base=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"append","--kind","fact","--scope","mcp","--text","Old conclusion","--state","PROVEN"],cwd=root,text=True,capture_output=True,check=True)
            base_id=json.loads(base.stdout)["id"]

            rejected=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"append","--kind","correction","--scope","mcp","--text","Corrected conclusion","--state","PROVEN"],cwd=root,text=True,capture_output=True)
            self.assertEqual(rejected.returncode,2,rejected.stderr)
            self.assertIn("correction must name at least one --supersedes",rejected.stdout)

            missing=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"append","--kind","correction","--scope","mcp","--text","Corrected conclusion","--state","PROVEN","--supersedes","mem-does-not-exist"],cwd=root,text=True,capture_output=True)
            self.assertEqual(missing.returncode,2,missing.stderr)
            self.assertIn("supersedes target not found",missing.stdout)

            linked=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"append","--kind","correction","--scope","mcp","--text","Corrected conclusion","--state","PROVEN","--supersedes",base_id],cwd=root,text=True,capture_output=True,check=True)
            self.assertEqual(json.loads(linked.stdout)["supersedes"],[base_id])

            standalone=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"append","--kind","correction","--scope","mcp","--text","Standalone correction rule","--state","PROVISIONAL","--standalone-correction"],cwd=root,text=True,capture_output=True,check=True)
            self.assertEqual(json.loads(standalone.stdout)["supersedes"],[])

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
    def test_record_cli_preserves_verbatim_sources_and_interpretation(self):
        root=Path(__file__).resolve().parents[1]
        cli=root/"tools"/"memory_bank.py"
        with tempfile.TemporaryDirectory() as d:
            bank=Path(d)/"bank.jsonl"
            source1="like in this memory i would expect all the relevant messages to be added in the final memort after I add them one by one you know"
            source2="with spelling mistakes and all and your versoin can then explain why the memory exists and what you added etc"
            cmd=[
                sys.executable,str(cli),"--bank",str(bank),"record",
                "--kind","lesson","--scope","memory-governance",
                "--title","Verbatim recorder provenance",
                "--text","Assistant memories keep source transcript and interpretation separate.",
                "--source-message",source1,"--source-message",source2,
                "--turn-task","make it permanent that the original actual words are always included in every assistant recorder memory so there is no ambiguity afterwards",
                "--interpretation","The user wants accumulated verbatim provenance, not cleaned-up paraphrases.",
                "--confidence","99",
                "--confidence-reason","The requirement was stated explicitly and refined over consecutive messages.",
                "--state","PROVEN",
            ]
            p=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            created=json.loads(p.stdout)
            self.assertEqual(created["source_messages"],[source1,source2])
            self.assertEqual(created["turn_task"],"make it permanent that the original actual words are always included in every assistant recorder memory so there is no ambiguity afterwards")
            self.assertEqual(created["interpretation"],"The user wants accumulated verbatim provenance, not cleaned-up paraphrases.")
            self.assertEqual(created["confidence"],99)
            self.assertIn("assistant-recorded",created["tags"])
            self.assertIn("verbatim-source",created["tags"])
            found=subprocess.run([sys.executable,str(cli),"--bank",str(bank),"history","versoin"],cwd=root,text=True,capture_output=True,check=True)
            self.assertEqual(json.loads(found.stdout)[0]["id"],created["id"])


if __name__ == "__main__": unittest.main()
