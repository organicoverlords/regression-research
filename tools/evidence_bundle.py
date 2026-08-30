#!/usr/bin/env python3
"""Create and verify deterministic, content-bound regression evidence manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path, PurePosixPath

SCHEMA_VERSION = 1


def resolve_commit(root: Path, value: str = "HEAD") -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{value}^{{commit}}"],
            cwd=root,
            text=True,
            encoding="utf-8",
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"cannot resolve subject commit: {value}") from exc


def normalize_repo_path(value: str) -> str:
    raw = value.strip().replace("\\", "/")
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"artifact path must be a normalized repository-relative path: {value!r}")
    normalized = path.as_posix()
    if ":" in path.parts[0]:
        raise ValueError(f"artifact path must not contain a drive prefix: {value!r}")
    return normalized


def file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def repo_file(root: Path, normalized: str) -> Path:
    path = root / Path(*PurePosixPath(normalized).parts)
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"artifact resolves outside repository root: {normalized}") from exc
    if not resolved.is_file():
        raise ValueError(f"artifact is not a regular file: {normalized}")
    return resolved


def artifact_record(root: Path, value: str) -> dict[str, object]:
    normalized = normalize_repo_path(value)
    path = repo_file(root, normalized)
    digest, size = file_digest(path)
    return {"path": normalized, "sha256": digest, "size": size}


def ensure_output_does_not_alias_artifacts(root: Path, output: Path, manifest: dict[str, object]) -> None:
    output_path = output.resolve()
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return
    for record in artifacts:
        if not isinstance(record, dict):
            continue
        normalized = normalize_repo_path(str(record.get("path", "")))
        if output_path == repo_file(root, normalized).resolve():
            raise ValueError(f"output path must not overwrite a bound artifact: {normalized}")


def build_manifest(root: Path, paths: list[str], commit: str) -> dict[str, object]:
    if not commit.strip():
        raise ValueError("subject commit must not be empty")
    if not paths:
        raise ValueError("evidence manifest must bind at least one artifact")
    records = [artifact_record(root, value) for value in paths]
    records.sort(key=lambda record: str(record["path"]))
    normalized = [str(record["path"]) for record in records]
    folded = [value.casefold() for value in normalized]
    if len(folded) != len(set(folded)):
        raise ValueError("artifact paths contain duplicate or case-colliding entries")
    return {
        "schema": SCHEMA_VERSION,
        "subject": {"commit": commit.strip()},
        "artifacts": records,
    }



def git_blob_identity(root: Path, commit: str, normalized: str) -> tuple[str, str]:
    subject = subprocess.run(
        ["git", "rev-parse", f"{commit}:{normalized}"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if subject.returncode != 0:
        raise ValueError(f"artifact is not tracked by subject commit {commit}: {normalized}")
    path = repo_file(root, normalized)
    working = subprocess.run(
        ["git", "hash-object", "--path", normalized, str(path)],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if working.returncode != 0:
        raise ValueError(f"cannot hash working artifact through Git filters: {normalized}")
    return subject.stdout.strip(), working.stdout.strip()


def verify_subject_bindings(root: Path, manifest: dict[str, object], commit: str) -> list[str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    errors: list[str] = []
    for record in artifacts:
        if not isinstance(record, dict):
            continue
        try:
            normalized = normalize_repo_path(str(record.get("path", "")))
            subject_oid, working_oid = git_blob_identity(root, commit, normalized)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if subject_oid != working_oid:
            errors.append(f"artifact does not match subject commit {commit}: {normalized}")
    return errors


def canonical_json(manifest: dict[str, object]) -> str:
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.write_bytes(canonical_json(manifest).encode("utf-8"))


def load_manifest(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read evidence manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("evidence manifest must be a JSON object")
    return data


def verify_manifest(root: Path, manifest: dict[str, object], expected_commit: str) -> list[str]:
    errors: list[str] = []
    if manifest.get("schema") != SCHEMA_VERSION:
        errors.append(f"unsupported evidence schema: {manifest.get('schema')!r}")
    subject = manifest.get("subject")
    if not isinstance(subject, dict) or subject.get("commit") != expected_commit:
        actual = subject.get("commit") if isinstance(subject, dict) else None
        errors.append(f"subject commit mismatch: manifest={actual!r} expected={expected_commit!r}")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list")
        return errors
    if not artifacts:
        errors.append("evidence manifest must bind at least one artifact")
        return errors

    seen: set[str] = set()
    for index, record in enumerate(artifacts):
        if not isinstance(record, dict):
            errors.append(f"artifact[{index}] must be an object")
            continue
        try:
            normalized = normalize_repo_path(str(record.get("path", "")))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        folded = normalized.casefold()
        if folded in seen:
            errors.append(f"duplicate artifact path: {normalized}")
            continue
        seen.add(folded)
        try:
            path = repo_file(root, normalized)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        digest, size = file_digest(path)
        if record.get("sha256") != digest:
            errors.append(f"artifact digest mismatch: {normalized}")
        if record.get("size") != size:
            errors.append(f"artifact size mismatch: {normalized}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root (default: cwd)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="write a content-bound evidence manifest")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--commit", help="immutable subject commit (default: git HEAD)")
    create.add_argument("paths", nargs="+", help="repository-relative files to bind")

    verify = subparsers.add_parser("verify", help="verify an evidence manifest without mutating it")
    verify.add_argument("manifest", type=Path)
    verify.add_argument("--commit", help="expected subject commit (default: git HEAD)")

    args = parser.parse_args()
    root = args.root.resolve()
    try:
        commit = resolve_commit(root, args.commit or "HEAD")
        if args.command == "create":
            manifest = build_manifest(root, args.paths, commit)
            subject_errors = verify_subject_bindings(root, manifest, commit)
            if subject_errors:
                raise ValueError(subject_errors[0])
            ensure_output_does_not_alias_artifacts(root, args.output, manifest)
            write_manifest(args.output, manifest)
            print(f"EVIDENCE_BUNDLE_CREATED {args.output}")
            return 0
        manifest = load_manifest(args.manifest)
        errors = verify_manifest(root, manifest, commit)
        errors.extend(verify_subject_bindings(root, manifest, commit))
    except ValueError as exc:
        print(f"EVIDENCE_BUNDLE_FAIL: {exc}")
        return 1

    if errors:
        for error in errors:
            print(f"EVIDENCE_BUNDLE_FAIL: {error}")
        return 1
    print("EVIDENCE_BUNDLE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
