from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .memory_authority import AUTHORITY_REGISTRY
    from .memory_bank import DEFAULT_BANK, load_bank
    from .memory_timeline import build_behavior_bootstrap
except ImportError:
    from memory_authority import AUTHORITY_REGISTRY
    from memory_bank import DEFAULT_BANK, load_bank
    from memory_timeline import build_behavior_bootstrap

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
    payload = build_behavior_bootstrap(load_bank(DEFAULT_BANK))
    return {
        "artifact_schema_version": 1,
        "purpose": "verified distribution cache of the canonical Vault behavior bootstrap",
        "library_path": DEFAULT_LIBRARY_PATH,
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

    verify = sub.add_parser("verify", help="compare a Library/downloaded copy byte-for-byte")
    verify.add_argument("copy", type=Path)

    args = parser.parse_args()
    if args.command == "render":
        data = render_artifact_bytes()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(data)
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
