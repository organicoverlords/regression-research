import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "Sync-VaultCheckout.ps1"


def run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return proc.stdout.strip()


@unittest.skipUnless(os.name == "nt", "Vault checkout sync is Windows-specific")
class VaultCheckoutSyncTests(unittest.TestCase):
    def test_repair_preserves_dirty_wrong_branch_before_converging_main(self):
        with tempfile.TemporaryDirectory(prefix="vault-sync-test-") as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "-C", str(repo), "init", "-b", "main"], check=True, capture_output=True)
            run_git(repo, "config", "user.email", "test@example.com")
            run_git(repo, "config", "user.name", "test")
            (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
            run_git(repo, "add", ".")
            run_git(repo, "commit", "-m", "base")
            main_head = run_git(repo, "rev-parse", "HEAD")
            run_git(repo, "update-ref", "refs/remotes/origin/main", main_head)

            run_git(repo, "switch", "-c", "feature")
            feature_head = run_git(repo, "rev-parse", "HEAD")
            (repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")
            (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
            run_git(repo, "add", "staged.txt")
            (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPT),
                    "-RepoRoot",
                    str(repo),
                    "-SkipFetch",
                    "-Repair",
                ],
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "REPAIRED")
            self.assertEqual(result["action"], "preserve-wrong-branch-dirty-then-switch-reset-to-remote")
            self.assertEqual(result["wrong_branch_before"], "feature")
            self.assertEqual(result["wrong_branch_head_before"], feature_head)

            self.assertEqual(run_git(repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")
            self.assertEqual(run_git(repo, "rev-parse", "HEAD"), main_head)
            self.assertEqual(run_git(repo, "status", "--porcelain=v1", "--untracked-files=normal"), "")
            self.assertEqual(run_git(repo, "rev-parse", "refs/heads/feature"), feature_head)

            preserve = result["preservation_branch"]
            self.assertEqual(run_git(repo, "show", f"{preserve}:tracked.txt"), "dirty")
            self.assertEqual(run_git(repo, "show", f"{preserve}:staged.txt"), "staged")
            self.assertEqual(run_git(repo, "show", f"{preserve}:untracked.txt"), "untracked")


if __name__ == "__main__":
    unittest.main()
