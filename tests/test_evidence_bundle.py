import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.evidence_bundle import (
    build_manifest,
    canonical_json,
    resolve_commit,
    verify_manifest,
    verify_subject_bindings,
)


class EvidenceBundleTests(unittest.TestCase):
    def test_manifest_is_deterministic_and_content_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "b.txt").write_text("beta\n", encoding="utf-8")
            (root / "a.txt").write_text("alpha\n", encoding="utf-8")
            first = build_manifest(root, ["b.txt", "a.txt"], "abc123")
            second = build_manifest(root, ["a.txt", "b.txt"], "abc123")
            self.assertEqual(canonical_json(first), canonical_json(second))
            self.assertEqual([item["path"] for item in first["artifacts"]], ["a.txt", "b.txt"])
            self.assertEqual(verify_manifest(root, first, "abc123"), [])

    def test_verify_rejects_stale_subject_and_tampered_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "result.json"
            artifact.write_text(json.dumps({"ok": True}), encoding="utf-8")
            manifest = build_manifest(root, ["result.json"], "commit-a")
            artifact.write_text(json.dumps({"ok": False}), encoding="utf-8")
            errors = verify_manifest(root, manifest, "commit-b")
            self.assertTrue(any("subject commit mismatch" in error for error in errors))
            self.assertTrue(any("artifact digest mismatch" in error for error in errors))

    def test_subject_binding_rejects_uncommitted_artifact_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            artifact = root / "proof.txt"
            artifact.write_text("committed\n", encoding="utf-8")
            subprocess.run(["git", "add", "proof.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            self.assertEqual(resolve_commit(root, "HEAD"), commit)
            committed_manifest = build_manifest(root, ["proof.txt"], commit)
            self.assertEqual(verify_subject_bindings(root, committed_manifest, commit), [])
            artifact.write_text("uncommitted\n", encoding="utf-8")
            dirty_manifest = build_manifest(root, ["proof.txt"], commit)
            self.assertEqual(
                verify_subject_bindings(root, dirty_manifest, commit),
                [f"artifact does not match subject commit {commit}: proof.txt"],
            )

    def test_verify_is_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "proof.txt"
            artifact.write_text("proof", encoding="utf-8")
            manifest = build_manifest(root, ["proof.txt"], "commit-a")
            before = artifact.read_bytes()
            self.assertEqual(verify_manifest(root, manifest, "commit-a"), [])
            self.assertEqual(artifact.read_bytes(), before)

    def test_rejects_empty_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(ValueError, "at least one artifact"):
                build_manifest(root, [], "commit-a")
            self.assertEqual(
                verify_manifest(
                    root,
                    {"schema": 1, "subject": {"commit": "commit-a"}, "artifacts": []},
                    "commit-a",
                ),
                ["evidence manifest must bind at least one artifact"],
            )

    def test_rejects_traversal_and_case_collisions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Evidence.txt").write_text("one", encoding="utf-8")
            (root / "evidence.txt").write_text("two", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repository-relative"):
                build_manifest(root, ["../escape.txt"], "commit-a")
            with self.assertRaisesRegex(ValueError, "case-colliding"):
                build_manifest(root, ["Evidence.txt", "evidence.txt"], "commit-a")


if __name__ == "__main__":
    unittest.main()
