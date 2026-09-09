import os
import subprocess
import unittest
from unittest.mock import patch

from tools import cleanup_converger, stack_atlas


@unittest.skipUnless(os.name == "nt", "Windows-only console-window regression")
class HiddenSubprocessWindowTests(unittest.TestCase):
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
