from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import importlib
import importlib.util
import os
import sqlite3
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "common"))


def configure_env(tmp_path: Path, monkeypatch, *, database_path: Path | None = None) -> tuple[Path, Path]:
    storage_root = tmp_path / "storage"
    for name in ["uploads", "audio", "tmp", "db"]:
        (storage_root / name).mkdir(parents=True, exist_ok=True)

    db_path = database_path or (storage_root / "db" / "nac_tts.sqlite3")
    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/13")
    return storage_root, db_path


def load_database_module(tmp_path: Path, monkeypatch, *, database_path: Path | None = None):
    configure_env(tmp_path, monkeypatch, database_path=database_path)
    for module_name in list(sys.modules):
        if module_name.startswith("tts_shared"):
            sys.modules.pop(module_name)
    return importlib.import_module("tts_shared.database")


def load_snapshot_module():
    module_path = ROOT / "ops" / "scripts" / "storage_snapshot.py"
    spec = importlib.util.spec_from_file_location("storage_snapshot", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["storage_snapshot"] = module
    spec.loader.exec_module(module)
    return module


def test_init_db_runs_alembic_migrations(tmp_path: Path, monkeypatch) -> None:
    db_module = load_database_module(tmp_path, monkeypatch)
    _, db_path = configure_env(tmp_path, monkeypatch)

    db_module.init_db()

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert "jobs" in tables
    assert revision == ("20260311_0001",)


def test_validate_storage_settings_rejects_sqlite_db_outside_storage_root(tmp_path: Path, monkeypatch) -> None:
    outside_db = tmp_path / "outside.sqlite3"
    db_module = load_database_module(tmp_path, monkeypatch, database_path=outside_db)

    with pytest.raises(RuntimeError, match="STORAGE_ROOT/db"):
        db_module.validate_storage_settings()


def test_storage_snapshot_backup_and_restore_round_trip(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    backup_root = tmp_path / "backups"
    for name in ["audio", "uploads", "db"]:
        (storage_root / name).mkdir(parents=True, exist_ok=True)

    source_db = storage_root / "db" / "nac_tts.sqlite3"
    with sqlite3.connect(source_db) as connection:
        connection.execute("CREATE TABLE example (value TEXT)")
        connection.execute("INSERT INTO example (value) VALUES ('original')")
        connection.commit()

    (storage_root / "audio" / "sample.mp3").write_bytes(b"mp3")
    (storage_root / "uploads" / "sample.pdf").write_bytes(b"%PDF")

    snapshot_module = load_snapshot_module()
    created_backup = snapshot_module.create_backup(storage_root, backup_root)

    (storage_root / "audio" / "sample.mp3").write_bytes(b"changed")
    clear_target = storage_root / "uploads" / "sample.pdf"
    clear_target.unlink()
    with sqlite3.connect(source_db) as connection:
        connection.execute("DELETE FROM example")
        connection.commit()

    snapshot_module.restore_backup(created_backup, storage_root)

    with sqlite3.connect(source_db) as connection:
        rows = connection.execute("SELECT value FROM example").fetchall()

    assert rows == [("original",)]
    assert (storage_root / "audio" / "sample.mp3").read_bytes() == b"mp3"
    assert (storage_root / "uploads" / "sample.pdf").read_bytes() == b"%PDF"
    assert (created_backup / "manifest.json").exists()


def test_retention_sweep_expires_old_tmp_and_audio_files(tmp_path: Path, monkeypatch) -> None:
    db_module = load_database_module(tmp_path, monkeypatch)
    db_module.init_db()
    retention_module = importlib.import_module("tts_shared.retention")
    models_module = importlib.import_module("tts_shared.models")

    old_tmp = retention_module.settings.tmp_dir / "stale.txt"
    old_tmp.write_text("old", encoding="utf-8")
    old_time = (datetime.now(timezone.utc) - timedelta(hours=retention_module.settings.tmp_retention_hours + 2)).timestamp()
    os.utime(old_tmp, (old_time, old_time))

    audio_path = retention_module.settings.audio_dir / "stale.mp3"
    audio_path.write_bytes(b"old-audio")
    text_path = retention_module.settings.tmp_dir / "job.txt"
    text_path.write_text("job", encoding="utf-8")

    with db_module.SessionLocal() as session:
        session.add(
            models_module.Job(
                id="retained-job",
                title="Retained Job",
                source_type="text",
                source_filename=None,
                source_path=None,
                text_path=str(text_path),
                status="completed",
                progress=100,
                progress_message="Completed",
                voice_id="af_heart",
                speaking_rate=1.0,
                char_count=3,
                attempt_count=1,
                page_count=None,
                audio_path=str(audio_path),
                completed_at=datetime.now(timezone.utc) - timedelta(days=retention_module.settings.audio_retention_days + 1),
            )
        )
        session.commit()

    result = retention_module.sweep_retention()

    with db_module.SessionLocal() as session:
        job = session.get(models_module.Job, "retained-job")
        assert job is not None
        assert job.audio_path is None

    assert result == {"tmp_removed": 1, "audio_removed": 1}
    assert not old_tmp.exists()
    assert not audio_path.exists()
