import ast
import json
import os
import struct
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import bootstrap_read_loop, cleanup_converger, stack_atlas

ROOT = Path(__file__).resolve().parents[1]


def _subprocess_run_owners(source: str) -> list[str | None]:
    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []
            self.owners: list[str | None] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
                and node.func.attr == "run"
            ):
                self.owners.append(self.stack[-1] if self.stack else None)
            self.generic_visit(node)

    visitor = Visitor()
    visitor.visit(ast.parse(source))
    return visitor.owners


def _pe_subsystem(path: Path) -> int:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise AssertionError(f"not a PE image: {path}")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise AssertionError(f"missing PE signature: {path}")
    optional_header = pe_offset + 24
    return struct.unpack_from("<H", data, optional_header + 68)[0]


class HiddenSubprocessContractTests(unittest.TestCase):
    def test_stack_atlas_direct_subprocess_runs_stay_inside_shared_runner(self):
        source = Path(stack_atlas.__file__).read_text(encoding="utf-8")
        owners = _subprocess_run_owners(source)
        self.assertGreaterEqual(len(owners), 1)
        self.assertEqual(set(owners), {"_run_process"})

    def test_stack_atlas_powershell_probe_routes_through_hidden_runner(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="[]\n", stderr="")
        with patch.object(stack_atlas, "_run_process", return_value=completed) as run:
            self.assertEqual(stack_atlas._powershell_json("Write-Output '[]'"), [])
        argv = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertIn("-WindowStyle", argv)
        self.assertEqual(argv[argv.index("-WindowStyle") + 1], "Hidden")
        self.assertTrue(kwargs["capture_output"])
        self.assertIsNotNone(kwargs["timeout"])
        if os.name == "nt":
            self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)

    def test_known_vault_background_owners_keep_headless_launch_contracts(self):
        required = {
            "tools/stack_atlas.py": ('getattr(subprocess, "CREATE_NO_WINDOW", 0)', "STARTF_USESHOWWINDOW", "SW_HIDE"),
            "tools/bootstrap_read_loop.py": ("def _creationflags()", "CREATE_NO_WINDOW"),
            "tools/timeline_materializer.py": ("def _run_process(", "CREATE_NO_WINDOW", "STARTF_USESHOWWINDOW", "SW_HIDE"),
            "tools/memory_git_sync.py": ("def _subprocess_window_kwargs()", "CREATE_NO_WINDOW", "STARTF_USESHOWWINDOW", "SW_HIDE"),
            "tools/repo_timeline.py": ("CREATE_NO_WINDOW",),
            "tools/cleanup_converger.py": ("CREATE_NO_WINDOW",),
            "tools/worktree_hygiene_guard.py": ("CREATE_NO_WINDOW",),
            "tools/runtime_dependency_graph.py": ("CREATE_NO_WINDOW",),
            "tools/worker_report_history.py": ("CREATE_NO_WINDOW",),
            "tools/Sync-VaultCheckout.ps1": ("-WindowStyle Hidden",),
            "tools/Install-TimelineMaterializerTask.ps1": ("pythonw.exe",),
            "tools/Install-VaultCheckoutSyncTask.ps1": ("pythonw.exe",),
            "tools/Install-WorktreeHygieneTask.ps1": ("pythonw.exe",),
            "tools/install_bootstrap_snapshot_task.ps1": ("pythonw.exe",),
        }
        for relative, tokens in required.items():
            with self.subTest(owner=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                for token in tokens:
                    self.assertIn(token, text, f"{relative} lost headless-launch contract token {token!r}")

    def test_bootstrap_direct_subprocess_runs_declare_creationflags(self):
        source = Path(bootstrap_read_loop.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
            and node.func.attr in {"run", "Popen"}
        ]
        self.assertGreater(len(calls), 0)
        for call in calls:
            keywords = {keyword.arg for keyword in call.keywords if keyword.arg is not None}
            self.assertIn("creationflags", keywords)


@unittest.skipUnless(os.name == "nt", "Windows-only console-window behavioral proof")
class HiddenSubprocessWindowsBehaviorTests(unittest.TestCase):
    def test_stack_atlas_shared_runner_hides_console_children(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.object(stack_atlas.subprocess, "run", return_value=completed) as run:
            stack_atlas._run_process(["git", "--version"], capture_output=True, text=True)
        kwargs = run.call_args.kwargs
        self.assertTrue(kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)
        self.assertTrue(kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(kwargs["startupinfo"].wShowWindow, subprocess.SW_HIDE)

    def test_cleanup_converger_children_use_no_window(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch.object(cleanup_converger.subprocess, "run", return_value=completed) as run:
            cleanup_converger._run(["powershell.exe", "-NoProfile", "-Command", "exit 0"], check=False)
        self.assertTrue(run.call_args.kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW)

    def test_actual_stack_atlas_child_console_is_not_visible(self):
        script = r'''
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class WindowProbe { [DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow(); [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd); }'
$hwnd = [WindowProbe]::GetConsoleWindow()
$visible = if ($hwnd -ne [IntPtr]::Zero) { [WindowProbe]::IsWindowVisible($hwnd) } else { $false }
[pscustomobject]@{ hwnd = $hwnd.ToInt64(); visible = $visible } | ConvertTo-Json -Compress
'''
        completed = stack_atlas._run_process(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        payload = json.loads(completed.stdout.strip())
        self.assertFalse(payload["visible"], payload)

    def test_pythonw_binary_is_gui_subsystem_when_available(self):
        executable = Path(sys.executable)
        candidate = executable if executable.name.casefold() == "pythonw.exe" else executable.with_name("pythonw.exe")
        if not candidate.is_file():
            self.skipTest(f"pythonw.exe not available beside {executable}")
        self.assertEqual(_pe_subsystem(candidate), 2, f"pythonw.exe is not IMAGE_SUBSYSTEM_WINDOWS_GUI: {candidate}")


if __name__ == "__main__":
    unittest.main()
