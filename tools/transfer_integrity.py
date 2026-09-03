from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "transfer-integrity.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_receipt(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"not a file: {path}")
    return {
        "schema": SCHEMA,
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def validate_receipt(receipt: object) -> dict[str, object]:
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise ValueError(f"receipt schema must be {SCHEMA}")
    size = receipt.get("bytes")
    digest = receipt.get("sha256")
    if not isinstance(size, int) or size < 0:
        raise ValueError("receipt bytes must be a non-negative integer")
    if not isinstance(digest, str) or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("receipt sha256 must be 64 lowercase hex characters")
    return receipt


def verify_file(path: Path, receipt: dict[str, object]) -> dict[str, object]:
    expected = validate_receipt(receipt)
    if not path.is_file():
        return {"status": "REJECTED", "reason": "destination_missing", "expected": expected, "actual": None}
    actual = build_receipt(path)
    size_match = actual["bytes"] == expected["bytes"]
    hash_match = actual["sha256"] == expected["sha256"]
    return {
        "status": "PROVEN" if size_match and hash_match else "REJECTED",
        "reason": "size_and_sha256_match" if size_match and hash_match else "integrity_mismatch",
        "size_match": size_match,
        "sha256_match": hash_match,
        "expected": expected,
        "actual": actual,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or verify transport-agnostic file transfer integrity receipts.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("file", type=Path)
    create.add_argument("--output", type=Path)
    verify = sub.add_parser("verify")
    verify.add_argument("file", type=Path)
    verify.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "create":
        payload = build_receipt(args.file)
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        print(text, end="")
        return 0

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    payload = verify_file(args.file, receipt)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
