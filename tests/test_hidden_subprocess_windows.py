import ast
import os
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import bootstrap_read_loop, cleanup_converger, stack_atlas


@unittest.skipUnless(os.name == "nt", "Windows-only console-window regression")
class HiddenSubprocessWindowTests(unittest.TestCase):
    def test_bootstrap_read_loop_direct_runs_hide_console_children(self):
        source = Path(bootstrap_read_loop.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr == "run"
        ]
        self.assertGreater(len(calls), 0)
        for call in calls:
            keywords = {keyword.arg for keyword in call.keywords if keyword.arg is not None}
            self.assertIn("creationflags", keywords)

    def test_stack_atlas_shared_runner_hides_console_children(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.object(stack_atlas.subprocess, "run", return_value=completed) as run:
            stack_atlas._run_process(["git", "--version"], capture_output=True, text=True)
        kwargs = run.call_args.kwargs
        self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)
        self.assertTrue(kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(kwargs["startupinfo"].wShowWindow, subprocess.SW_HIDE)

    def test_stack_atlas_has_no_direct_subprocess_run_bypass(self):
        source = Path(stack_atlas.__file__).read_text(encoding="utf-8")
        self.assertEqual(source.count("subprocess.run("), 1)

    def test_stack_atlas_powershell_probe_is_hidden(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="[]\n", stderr="")
        with patch.object(stack_atlas.subprocess, "run", return_value=completed) as run:
            self.assertEqual(stack_atlas._powershell_json("Write-Output '[]'"), [])
        argv = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertIn("-WindowStyle", argv)
        self.assertEqual(argv[argv.index("-WindowStyle") + 1], "Hidden")
        self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)

    def test_cleanup_converger_children_use_no_window(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.object(cleanup_converger.subprocess, "run", return_value=completed) as run:
            cleanup_converger._run(["powershell.exe", "-NoProfile", "-Command", "exit 0"], check=False)
        self.assertTrue(run.call_args.kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)


if __name__ == "__main__":
    unittest.main()
