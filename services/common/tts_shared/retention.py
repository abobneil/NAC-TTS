from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from .config import get_settings
from .database import SessionLocal
from .models import Job


settings = get_settings()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _delete_old_tmp_files(cutoff: datetime) -> int:
    removed = 0
    for path in settings.tmp_dir.rglob("*"):
        if not path.exists():
            continue
        if path.is_dir():
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if modified_at < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def _delete_empty_tmp_dirs() -> None:
    for path in sorted(settings.tmp_dir.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def _expire_audio_files(cutoff: datetime) -> int:
    removed = 0
    with SessionLocal() as session:
        jobs = session.scalars(
            select(Job).where(
                Job.audio_path.is_not(None),
                Job.completed_at.is_not(None),
                Job.completed_at < cutoff,
            )
        ).all()

        for job in jobs:
            Path(job.audio_path).unlink(missing_ok=True)
            job.audio_path = None
            removed += 1

        session.commit()
    return removed


def sweep_retention() -> dict[str, int]:
    tmp_cutoff = _utcnow() - timedelta(hours=settings.tmp_retention_hours)
    audio_cutoff = _utcnow() - timedelta(days=settings.audio_retention_days)
    tmp_removed = _delete_old_tmp_files(tmp_cutoff)
    _delete_empty_tmp_dirs()
    audio_removed = _expire_audio_files(audio_cutoff)
    return {"tmp_removed": tmp_removed, "audio_removed": audio_removed}
