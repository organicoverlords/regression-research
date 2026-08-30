import json
import tempfile
import unittest
from pathlib import Path

from tools.memory_policy_changes import recent_memory_policy_changes


class MemoryPolicyChangesTests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> str:
        import subprocess
        return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8").strip()

    def test_recent_changes_reconstruct_memory_authority_and_policy_delta(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self._git(root, "init", "-b", "main")
            self._git(root, "config", "user.email", "changes@example.invalid")
            self._git(root, "config", "user.name", "changes-test")
            memory = root / "memory"
            contracts = root / "04 Operating Contracts"
            memory.mkdir()
            contracts.mkdir()
            bank = memory / "memory-bank.jsonl"
            registry = memory / "behavior-authority-registry.json"
            contract = contracts / "startup.json"
            bank.write_text(json.dumps({"id": "mem-a", "title": "base", "kind": "fact", "scope": "global", "state": "PROVEN", "supersedes": []}) + "\n", encoding="utf-8")
            registry.write_text(json.dumps({"user_explicit_ids": [], "canonical_policy_ids": []}), encoding="utf-8")
            contract.write_text("{}\n", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "base")

            entry = {"id": "mem-b", "title": "review first", "kind": "correction", "scope": "assistant", "state": "PROVEN", "supersedes": ["mem-a"]}
            with bank.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(entry) + "\n")
            registry.write_text(json.dumps({"user_explicit_ids": ["mem-b"], "canonical_policy_ids": []}), encoding="utf-8")
            contract.write_text('{"sequence":"changed"}\n', encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-m", "memory: authorize mem-b")

            change = recent_memory_policy_changes(root=root, limit=1)[0]
            self.assertEqual(change["subject"], "memory: authorize mem-b")
            self.assertEqual(change["memory"]["added"][0]["id"], "mem-b")
            self.assertEqual(change["memory"]["added"][0]["supersedes"], ["mem-a"])
            self.assertEqual(change["behavior_authority"]["user_explicit_added"], ["mem-b"])
            self.assertEqual(change["policy_files"], ["04 Operating Contracts/startup.json"])


if __name__ == "__main__":
    unittest.main()