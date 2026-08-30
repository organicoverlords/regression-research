from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = Path(r"C:\Users\Lauri\Desktop\vault") if os.name == "nt" else REPO
DEFAULT_ROOT = Path(os.environ.get("MEMORY_VAULT_ROOT", str(DEFAULT_VAULT))) / "memory" / "conversations"
DEFAULT_BACKUP_DIR = Path(r"G:\Oma Drive\Memory Corpus Backups")
CHUNK = 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _iter_files(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__"}]
        base = Path(current)
        for name in sorted(files):
            path = base / name
            if not path.is_symlink():
                yield path


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": "vault.memory-conversations.v2", "imports": [], "files": []}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise ValueError(f"invalid conversation corpus manifest: {path}")
    value.setdefault("imports", [])
    value.setdefault("recoveries", [])
    return value


def _write_manifest(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="manifest-", suffix=".json", dir=path.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _storage(row: dict[str, Any]) -> str:
    return str(row.get("storage_path") or (Path("raw") / str(row["label"]) / Path(str(row["relative_path"]))).as_posix())


def _copy_verified(src: Path, dst: Path) -> tuple[int, str, bool]:
    size = src.stat().st_size
    digest = _sha256(src)
    if dst.exists():
        if not dst.is_file() or dst.stat().st_size != size or _sha256(dst) != digest:
            raise RuntimeError(f"canonical target differs; refusing overwrite: {dst}")
        return size, digest, False
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.with_name(dst.name + f".copy-{os.getpid()}.tmp")
    shutil.copy2(src, temp)
    if temp.stat().st_size != size or _sha256(temp) != digest:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f"copy verification failed: {src}")
    os.replace(temp, dst)
    return size, digest, True


def _revision_storage(label: str, rel: Path, digest: str) -> str:
    return (Path("revisions") / label / digest[:16] / rel).as_posix()


def sync_source(
    source: Path,
    label: str,
    root: Path = DEFAULT_ROOT,
    *,
    min_age_seconds: float = 0.0,
) -> dict[str, Any]:
    """Incrementally preserve a moving export source without rewriting history.

    New paths become immutable baseline copies under ``raw/<label>``. If a source
    path later changes bytes, the original canonical copy remains untouched and the
    new bytes are stored under a content-addressed ``revisions/<label>`` path.
    Files younger than ``min_age_seconds`` are deferred so active writers are not
    snapshotted mid-write. Missing source files never delete canonical history.
    """
    source = source.resolve(strict=True)
    if not label or Path(label).name != label or label in {".", ".."}:
        raise ValueError("label must be one safe directory name")
    if min_age_seconds < 0:
        raise ValueError("min_age_seconds must be non-negative")

    manifest = _load_manifest(root / "manifest.json")
    rows = {_storage(row): row for row in manifest["files"]}
    copied = reused = fast_reused = revisions_copied = revisions_reused = total = 0
    deferred_unstable = 0
    seen_baselines: set[str] = set()
    candidates = list(_iter_files(source)) if source.is_dir() else [source]
    now_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)

    for src in candidates:
        rel = src.relative_to(source) if source.is_dir() else Path(src.name)
        storage = (Path("raw") / label / rel).as_posix()
        src_stat = src.stat()
        age_seconds = max(0.0, (now_ns - src_stat.st_mtime_ns) / 1_000_000_000)
        if age_seconds < min_age_seconds:
            deferred_unstable += 1
            continue
        seen_baselines.add(storage)
        total += src_stat.st_size
        dst = root / storage
        existing = rows.get(storage)

        if existing is None:
            size, digest, created = _copy_verified(src, dst)
            copied += int(created)
            reused += int(not created)
            rows[storage] = {
                "storage_path": storage,
                "label": label,
                "relative_path": rel.as_posix(),
                "bytes": size,
                "sha256": digest,
                "kind": "source-copy",
                "source_mtime_ns": src_stat.st_mtime_ns,
            }
            continue

        if not dst.is_file():
            raise RuntimeError(f"canonical target missing for manifest row: {dst}")
        expected_size = int(existing.get("bytes", -1))
        expected_digest = str(existing.get("sha256") or "")
        dst_stat = dst.stat()
        if (
            expected_size == src_stat.st_size == dst_stat.st_size
            and dst_stat.st_mtime_ns == src_stat.st_mtime_ns
        ):
            fast_reused += 1
            reused += 1
            continue

        # Metadata changed. Verify the immutable baseline before deciding whether
        # the source is merely touched or is a genuinely new revision.
        if dst_stat.st_size != expected_size or _sha256(dst) != expected_digest:
            raise RuntimeError(f"canonical target differs from manifest; refusing refresh: {dst}")
        source_digest = _sha256(src)
        if src_stat.st_size == expected_size and source_digest == expected_digest:
            reused += 1
            continue

        revision_storage = _revision_storage(label, rel, source_digest)
        revision_dst = root / revision_storage
        size, digest, created = _copy_verified(src, revision_dst)
        revisions_copied += int(created)
        revisions_reused += int(not created)
        reused += int(not created)
        rows[revision_storage] = {
            "storage_path": revision_storage,
            "label": label,
            "relative_path": rel.as_posix(),
            "bytes": size,
            "sha256": digest,
            "kind": "source-revision",
            "revision_of": storage,
            "source_mtime_ns": src_stat.st_mtime_ns,
        }

    baseline_rows = {
        storage for storage, row in rows.items()
        if row.get("label") == label and row.get("kind") == "source-copy"
    }
    imports = [entry for entry in manifest.get("imports", []) if entry.get("label") != label]
    imports.append({
        "label": label,
        "original_source": str(source),
        "imported_at": _now(),
        "files": len(candidates),
        "bytes": total,
        "mode": "revision-preserving-sync",
        "deferred_unstable": deferred_unstable,
    })
    manifest.update({
        "schema": "vault.memory-conversations.v2",
        "updated_at": _now(),
        "imports": sorted(imports, key=lambda x: x["label"]),
        "files": sorted(rows.values(), key=_storage),
    })
    _write_manifest(root / "manifest.json", manifest)
    return {
        "status": "PROVEN",
        "label": label,
        "source": str(source),
        "canonical": str(root / "raw" / label),
        "files_seen": len(candidates),
        "stable_files_seen": len(seen_baselines),
        "bytes": total,
        "copied": copied,
        "reused": reused,
        "fast_reused": fast_reused,
        "revisions_copied": revisions_copied,
        "revisions_reused": revisions_reused,
        "deferred_unstable": deferred_unstable,
        "preserved_missing_source_files": len(baseline_rows - seen_baselines),
    }


def import_source(source: Path, label: str, root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    source = source.resolve(strict=True)
    if not label or Path(label).name != label or label in {".", ".."}:
        raise ValueError("label must be one safe directory name")
    manifest = _load_manifest(root / "manifest.json")
    rows = {_storage(row): row for row in manifest["files"]}
    copied = reused = total = 0
    touched = []
    candidates = list(_iter_files(source)) if source.is_dir() else [source]
    for src in candidates:
        rel = src.relative_to(source) if source.is_dir() else Path(src.name)
        storage = (Path("raw") / label / rel).as_posix()
        size, digest, created = _copy_verified(src, root / storage)
        copied += int(created); reused += int(not created); total += size
        row = {"storage_path": storage, "label": label, "relative_path": rel.as_posix(), "bytes": size, "sha256": digest, "kind": "source-copy"}
        rows[storage] = row; touched.append(row)
    imports = [entry for entry in manifest.get("imports", []) if entry.get("label") != label]
    imports.append({"label": label, "original_source": str(source), "imported_at": _now(), "files": len(touched), "bytes": total})
    manifest.update({"schema": "vault.memory-conversations.v2", "updated_at": _now(), "imports": sorted(imports, key=lambda x: x["label"]), "files": sorted(rows.values(), key=_storage)})
    _write_manifest(root / "manifest.json", manifest)
    return {"status": "PROVEN", "label": label, "source": str(source), "canonical": str(root / "raw" / label), "files": len(touched), "bytes": total, "copied": copied, "reused": reused}


def export_legacy_sqlite(source_db: Path, root: Path = DEFAULT_ROOT, label: str = "legacy-regression-sqlite") -> dict[str, Any]:
    import sqlite3
    source_db = source_db.resolve(strict=True)
    source_hash = _sha256(source_db)
    conn = sqlite3.connect(source_db); conn.row_factory = sqlite3.Row
    manifest = _load_manifest(root / "manifest.json")
    rows = {_storage(row): row for row in manifest["files"]}
    written = reused = messages_total = 0
    try:
        conversations = conn.execute("SELECT * FROM conversations ORDER BY id").fetchall()
        for conv in conversations:
            cid = str(conv["id"]); messages = []
            for msg in conn.execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY seq", (cid,)):
                messages.append({"id": str(msg["message_id"] or f"{cid}:{msg['seq']}"), "role": str(msg["role"] or "unknown"), "create_time": msg["create_time"], "content": {"content_type": "text", "parts": [str(msg["text"] or "")]}})
            obj = {"id": cid, "conversation_id": cid, "title": conv["title"], "create_time": conv["create_time"], "update_time": conv["update_time"], "messages": messages, "_vault_recovery": {"source": str(source_db), "source_sha256": source_hash, "source_kind": conv["source_kind"], "source_path": conv["source_path"]}}
            data = (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
            storage = (Path("recovered") / label / "conversations" / f"{cid}.json").as_posix(); dst = root / storage
            digest = hashlib.sha256(data).hexdigest()
            if dst.exists():
                if dst.read_bytes() != data: raise RuntimeError(f"recovered conversation differs; refusing overwrite: {dst}")
                reused += 1
            else:
                dst.parent.mkdir(parents=True, exist_ok=True); temp = dst.with_name(dst.name + f".write-{os.getpid()}.tmp"); temp.write_bytes(data); os.replace(temp, dst); written += 1
            messages_total += len(messages)
            rows[storage] = {"storage_path": storage, "label": label, "relative_path": f"conversations/{cid}.json", "bytes": len(data), "sha256": digest, "kind": "recovered-conversation", "source_sha256": source_hash}
    finally:
        conn.close()
    recoveries = [entry for entry in manifest.get("recoveries", []) if entry.get("label") != label]
    recoveries.append({"label": label, "source_db": str(source_db), "source_sha256": source_hash, "recovered_at": _now(), "conversations": written + reused, "messages": messages_total})
    manifest.update({"schema": "vault.memory-conversations.v2", "updated_at": _now(), "recoveries": sorted(recoveries, key=lambda x: x["label"]), "files": sorted(rows.values(), key=_storage)})
    _write_manifest(root / "manifest.json", manifest)
    return {"status": "PROVEN", "source": str(source_db), "source_sha256": source_hash, "conversations": written + reused, "messages": messages_total, "written": written, "reused": reused, "canonical": str(root / "recovered" / label)}

def verify(root: Path = DEFAULT_ROOT, hashes: bool = True) -> dict[str, Any]:
    manifest = _load_manifest(root / "manifest.json")
    missing, mismatched = [], []
    total = 0
    for row in manifest["files"]:
        path = root / _storage(row)
        if not path.is_file():
            missing.append(str(path))
            continue
        size = path.stat().st_size
        total += size
        if size != int(row["bytes"]):
            mismatched.append(str(path) + ":SIZE")
        elif hashes and _sha256(path) != row["sha256"]:
            mismatched.append(str(path) + ":SHA256")
    return {"status": "PROVEN" if not missing and not mismatched else "REJECTED", "root": str(root), "files": len(manifest["files"]), "bytes": total, "imports": manifest.get("imports", []), "recoveries": manifest.get("recoveries", []), "hashes_verified": hashes, "missing": missing[:20], "mismatched": mismatched[:20]}


def backup(root: Path = DEFAULT_ROOT, backup_dir: Path = DEFAULT_BACKUP_DIR) -> dict[str, Any]:
    proof = verify(root, hashes=True)
    if proof["status"] != "PROVEN":
        return {"status": "REJECTED", "error": "canonical corpus failed verification", "verification": proof}
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = backup_dir / f"memory-conversations-{stamp}.zip"
    partial = final.with_suffix(".zip.part")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
        for path in _iter_files(root):
            zf.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(partial) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"backup CRC verification failed: {bad}")
    digest = _sha256(partial)
    os.replace(partial, final)
    checksum = final.with_suffix(final.suffix + ".sha256")
    checksum.write_text(f"{digest}  {final.name}\n", encoding="ascii")
    return {"status": "PROVEN", "archive": str(final), "sha256": digest, "bytes": final.stat().st_size, "checksum": str(checksum), "files": proof["files"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Preserve full downloaded ChatGPT conversations inside the canonical Vault memory corpus.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import"); imp.add_argument("--source", type=Path, required=True); imp.add_argument("--label", required=True)
    sync = sub.add_parser("sync"); sync.add_argument("--source", type=Path, required=True); sync.add_argument("--label", required=True); sync.add_argument("--min-age-seconds", type=float, default=0.0)
    recover = sub.add_parser("recover-legacy-sqlite"); recover.add_argument("--source-db", type=Path, required=True); recover.add_argument("--label", default="legacy-regression-sqlite")
    check = sub.add_parser("verify"); check.add_argument("--no-hash", action="store_true")
    save = sub.add_parser("backup"); save.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()
    try:
        if args.command == "import": result = import_source(args.source, args.label, args.root)
        elif args.command == "sync": result = sync_source(args.source, args.label, args.root, min_age_seconds=args.min_age_seconds)
        elif args.command == "recover-legacy-sqlite": result = export_legacy_sqlite(args.source_db, args.root, args.label)
        elif args.command == "verify": result = verify(args.root, hashes=not args.no_hash)
        else: result = backup(args.root, args.backup_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") == "PROVEN" else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
