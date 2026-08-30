from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from .memory_authority import AUTHORITY_REGISTRY
    from .memory_bank import DEFAULT_BANK, build_startup_bootstrap, load_bank
except ImportError:
    from memory_authority import AUTHORITY_REGISTRY
    from memory_bank import DEFAULT_BANK, build_startup_bootstrap, load_bank

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY_PATH = "/Agent Bootstrap/chatgpt-bootstrap.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _source_descriptor(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": _repo_path(path),
        "bytes": len(data),
        "sha256": _sha256(data),
    }


def build_chatgpt_bootstrap_artifact() -> dict[str, Any]:
    """Build the generated ChatGPT distribution artifact from canonical Vault authority."""
    payload = build_startup_bootstrap(load_bank(DEFAULT_BANK))
    return {
        "artifact_schema_version": 2,
        "purpose": "primary fresh-chat behavior delivery generated from canonical Vault authority",
        "library_path": DEFAULT_LIBRARY_PATH,
        "delivery_contract": {
            "canonical_authority": "Vault",
            "fresh_chat_behavior_role": "primary",
            "behavior_requires_mcp": False,
            "vault_bootstrap_role": "fallback behavior delivery when Library is unavailable or incomplete",
            "embedded_recent_memory_glance_role": "bounded fallback orientation snapshot; refresh from Vault after behavior when available",
        },
        "source": {
            "behavior_bank": _source_descriptor(DEFAULT_BANK),
            "authority_registry": _source_descriptor(AUTHORITY_REGISTRY),
        },
        "payload": payload,
    }


def render_artifact_bytes() -> bytes:
    artifact = build_chatgpt_bootstrap_artifact()
    text = json.dumps(
        artifact,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (text + "\n").encode("utf-8")


def publication_plan() -> dict[str, Any]:
    data = render_artifact_bytes()
    artifact = build_chatgpt_bootstrap_artifact()
    return {
        "status": "EXPECTED_LIBRARY_ARTIFACT",
        "library_path": DEFAULT_LIBRARY_PATH,
        "bytes": len(data),
        "sha256": _sha256(data),
        "delivery_role": artifact["delivery_contract"]["fresh_chat_behavior_role"],
        "canonical_authority": artifact["delivery_contract"]["canonical_authority"],
        "source": artifact["source"],
        "acceptance": "retrieve the published Library copy and require byte-exact verify=PROVEN",
    }


def write_artifact_copy(path: Path, data: bytes) -> None:
    """Publish an artifact without exposing a partially written final path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def verify_artifact_copy(path: Path) -> dict[str, Any]:
    expected = render_artifact_bytes()
    actual = path.read_bytes()
    return {
        "status": "PROVEN" if actual == expected else "MISMATCH",
        "library_path": DEFAULT_LIBRARY_PATH,
        "expected_bytes": len(expected),
        "actual_bytes": len(actual),
        "expected_sha256": _sha256(expected),
        "actual_sha256": _sha256(actual),
    }


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render or verify the generated ChatGPT bootstrap distribution artifact."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="render the canonical generated artifact")
    render.add_argument("--output", type=Path)

    sub.add_parser("publication-plan", help="describe the exact Library artifact the publisher worker must expose")

    verify = sub.add_parser("verify", help="compare a Library/downloaded copy byte-for-byte")
    verify.add_argument("copy", type=Path)

    args = parser.parse_args()
    if args.command == "publication-plan":
        _print_json(publication_plan())
        return 0
    if args.command == "render":
        data = render_artifact_bytes()
        if args.output:
            write_artifact_copy(args.output, data)
            _print_json({
                "status": "RENDERED",
                "path": str(args.output),
                "bytes": len(data),
                "sha256": _sha256(data),
                "library_path": DEFAULT_LIBRARY_PATH,
            })
        else:
            stream = getattr(sys.stdout, "buffer", None)
            if stream is None:
                sys.stdout.write(data.decode("utf-8"))
            else:
                stream.write(data)
                stream.flush()
        return 0

    result = verify_artifact_copy(args.copy)
    _print_json(result)
    return 0 if result["status"] == "PROVEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
