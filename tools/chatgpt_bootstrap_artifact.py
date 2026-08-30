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
    from .stack_atlas import atlas_publication_plan
except ImportError:
    from memory_authority import AUTHORITY_REGISTRY
    from memory_bank import DEFAULT_BANK, build_startup_bootstrap, load_bank
    from stack_atlas import atlas_publication_plan

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIBRARY_PATH = "/Agent Bootstrap/chatgpt-bootstrap.json"
MAX_ARTIFACT_BYTES = 15_000
EMBEDDED_RECENT_LIMIT = 1
STACK_ATLAS_SOURCE = ROOT / "tools" / "stack_atlas.py"
CAPABILITY_POLICY_SOURCE = ROOT / "tests" / "fixtures" / "capability-routing-policy.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _repo_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _source_digest(path: Path) -> str:
    return _sha256(path.read_bytes())


def _source_digests() -> dict[str, str]:
    return {
        "behavior_bank": _source_digest(DEFAULT_BANK),
        "authority_registry": _source_digest(AUTHORITY_REGISTRY),
        "stack_atlas": _source_digest(STACK_ATLAS_SOURCE),
        "capability_policy": _source_digest(CAPABILITY_POLICY_SOURCE),
    }


def _compact_payload() -> dict[str, Any]:
    return {
        "status": "RETIRED",
        "continuity": "current conversation + ChatGPT Memory",
        "vault": "optional history/notebook/evidence only",
        "atlas": "publish/use Stack Atlas independently for stack/infra work",
    }


def build_chatgpt_bootstrap_artifact() -> dict[str, Any]:
    """Legacy tombstone: behavior bootstrap distribution is retired."""
    return {
        "artifact_schema_version": 4,
        "purpose": "retired ChatGPT behavior bootstrap",
        "library_path": DEFAULT_LIBRARY_PATH,
        "authority": "NONE",
        "retired": True,
        "payload": _compact_payload(),
    }


def render_artifact_bytes() -> bytes:
    artifact = build_chatgpt_bootstrap_artifact()
    text = json.dumps(
        artifact,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    data = (text + "\n").encode("utf-8")
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"generated ChatGPT bootstrap is {len(data)} bytes; cap is {MAX_ARTIFACT_BYTES}")
    return data


def publication_plan() -> dict[str, Any]:
    return {
        "status": "RETIRED_NO_LIBRARY_ARTIFACT",
        "library_path": DEFAULT_LIBRARY_PATH,
        "publish": False,
        "stack_atlas": atlas_publication_plan(),
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
        description="Legacy retired ChatGPT bootstrap artifact utility; Stack Atlas publishes separately."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    render = sub.add_parser("render", help="render the canonical generated artifact")
    render.add_argument("--output", type=Path)

    sub.add_parser("publication-plan", help="report that bootstrap publication is retired; includes independent Atlas plan")

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
