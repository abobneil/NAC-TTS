from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, UTC
from pathlib import Path
import json
import shutil
import sqlite3


def backup_sqlite_database(source_db: Path, destination_db: Path) -> None:
    destination_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source_db) as source, sqlite3.connect(destination_db) as destination:
        source.backup(destination)


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def clear_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def create_backup(storage_root: Path, output_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_root = output_root / f"backup-{timestamp}"
    backup_root.mkdir(parents=True, exist_ok=False)

    source_db = storage_root / "db" / "nac_tts.sqlite3"
    if not source_db.exists():
        raise FileNotFoundError(f"SQLite database not found: {source_db}")

    backup_sqlite_database(source_db, backup_root / "db" / "nac_tts.sqlite3")
    copy_tree(storage_root / "audio", backup_root / "audio")
    copy_tree(storage_root / "uploads", backup_root / "uploads")

    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "storage_root": str(storage_root.resolve()),
        "database": "db/nac_tts.sqlite3",
        "copied_directories": ["audio", "uploads"],
    }
    (backup_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return backup_root


def restore_backup(backup_root: Path, storage_root: Path) -> None:
    source_db = backup_root / "db" / "nac_tts.sqlite3"
    if not source_db.exists():
        raise FileNotFoundError(f"Backup database not found: {source_db}")

    destination_db_dir = storage_root / "db"
    destination_db_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_db, destination_db_dir / "nac_tts.sqlite3")

    for name in ["audio", "uploads"]:
        clear_directory(storage_root / name)
        copy_tree(backup_root / name, storage_root / name)


def main() -> None:
    parser = ArgumentParser(description="Create or restore NAC-TTS storage snapshots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument("--storage-root", type=Path, required=True)
    backup_parser.add_argument("--output-root", type=Path, required=True)

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--backup-root", type=Path, required=True)
    restore_parser.add_argument("--storage-root", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "backup":
        backup_root = create_backup(args.storage_root, args.output_root)
        print(backup_root)
        return

    restore_backup(args.backup_root, args.storage_root)
    print(args.storage_root)


if __name__ == "__main__":
    main()
