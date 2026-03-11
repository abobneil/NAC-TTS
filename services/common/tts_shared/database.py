from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _sqlite_database_path() -> Path | None:
    if not settings.database_url.startswith("sqlite:///"):
        return None
    return Path(settings.database_url.removeprefix("sqlite:///"))


def validate_storage_settings() -> None:
    if not settings.storage_root.is_absolute():
        raise RuntimeError("STORAGE_ROOT must be an absolute path.")

    directories = [settings.uploads_dir, settings.audio_dir, settings.tmp_dir, settings.db_dir]
    if len({directory.resolve() for directory in directories}) != len(directories):
        raise RuntimeError("Storage directories must resolve to distinct paths.")

    database_path = _sqlite_database_path()
    if database_path is not None and settings.db_dir.resolve() not in database_path.resolve().parents:
        raise RuntimeError("SQLite DATABASE_URL must point inside STORAGE_ROOT/db.")


def init_db() -> None:
    from .db_migrations import run_migrations

    validate_storage_settings()
    settings.db_dir.mkdir(parents=True, exist_ok=True)
    run_migrations()

    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON;")


@contextmanager
def session_scope() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
