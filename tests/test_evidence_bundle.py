import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.evidence_bundle import (
    build_manifest,
    canonical_json,
    ensure_output_does_not_alias_artifacts,
    resolve_commit,
    verify_manifest,
    verify_subject_bindings,
    write_manifest,
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

    def test_write_manifest_uses_canonical_lf_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "bundle.json"
            manifest = {"schema": 1, "subject": {"commit": "abc123"}, "artifacts": [{"path": "proof.txt", "sha256": "00", "size": 0}]}
            write_manifest(output, manifest)
            self.assertEqual(output.read_bytes(), canonical_json(manifest).encode("utf-8"))
            self.assertNotIn(b"\r\n", output.read_bytes())

    def test_write_manifest_preserves_existing_output_when_publish_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "bundle.json"
            output.write_bytes(b"last-known-good\n")
            manifest = {"schema": 1, "subject": {"commit": "abc123"}, "artifacts": [{"path": "proof.txt", "sha256": "00", "size": 0}]}
            with mock.patch("tools.evidence_bundle.os.replace", side_effect=OSError("publish failed")):
                with self.assertRaisesRegex(OSError, "publish failed"):
                    write_manifest(output, manifest)
            self.assertEqual(output.read_bytes(), b"last-known-good\n")
            self.assertEqual(list(root.glob(f".{output.name}.*.tmp")), [])

    def test_verify_is_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "proof.txt"
            artifact.write_text("proof", encoding="utf-8")
            manifest = build_manifest(root, ["proof.txt"], "commit-a")
            before = artifact.read_bytes()
            self.assertEqual(verify_manifest(root, manifest, "commit-a"), [])
            self.assertEqual(artifact.read_bytes(), before)

    def test_create_rejects_output_that_aliases_bound_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "proof.txt"
            artifact.write_text("proof\n", encoding="utf-8")
            manifest = build_manifest(root, ["proof.txt"], "commit-a")
            before = artifact.read_bytes()
            with self.assertRaisesRegex(ValueError, "must not overwrite a bound artifact"):
                ensure_output_does_not_alias_artifacts(root, artifact, manifest)
            self.assertEqual(artifact.read_bytes(), before)

    def test_create_rejects_hardlink_output_alias(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            artifact = root / "proof.txt"
            output = root / "bundle.json"
            artifact.write_text("proof\n", encoding="utf-8")
            try:
                output.hardlink_to(artifact)
            except OSError as exc:
                self.skipTest(f"hard links unavailable: {exc}")
            manifest = build_manifest(root, ["proof.txt"], "commit-a")
            before = artifact.read_bytes()
            with self.assertRaisesRegex(ValueError, "must not overwrite a bound artifact"):
                ensure_output_does_not_alias_artifacts(root, output, manifest)
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
