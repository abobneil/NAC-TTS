from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import logging
import shutil
import time
import traceback
from typing import Literal

from sqlalchemy import select

from tts_shared.audio_utils import combine_wavs, wav_to_mp3, write_silence
from tts_shared.config import get_settings
from tts_shared.database import SessionLocal, init_db
from tts_shared.logging_utils import configure_json_logging, log_event
from tts_shared.models import Job
from tts_shared.queue import (
    ack_job,
    clear_job,
    enqueue_job,
    list_pending_jobs,
    list_processing_jobs,
    publish_capabilities,
    queue_depth,
    record_worker_heartbeat,
    requeue_job,
    reserve_job,
)
from tts_shared.retention import sweep_retention
from tts_shared.text_utils import chunk_text


settings = get_settings()
logger = logging.getLogger("nac_tts.worker")


class JobCanceledError(RuntimeError):
    pass


class PermanentJobError(RuntimeError):
    pass


class KokoroEngine:
    def __init__(self) -> None:
        import torch
        from kokoro import KPipeline

        self._torch = torch
        requested = settings.kokoro_device
        if requested == "cuda" and not torch.cuda.is_available():
            self.device = "cpu"
        else:
            self.device = requested if requested in {"cpu", "cuda"} else "cpu"
        self.pipeline = KPipeline(
            repo_id=settings.model_id,
            lang_code=settings.lang_code,
            device=self.device,
        )

    def capabilities(self) -> dict:
        return {
            "device": self.device,
            "model_id": settings.model_id,
            "voices": [asdict(voice) for voice in settings.voices],
            "formats": ["mp3"],
            "limits": {
                "max_upload_mb": settings.max_upload_mb,
                "max_pages": settings.max_pages,
                "max_chars": settings.max_chars,
            },
            "sample_rate": settings.sample_rate,
        }

    def synthesize_chunks(self, text: str, voice_id: str, speaking_rate: float, job_dir: Path, job_id: str) -> tuple[Path, float]:
        import soundfile as sf

        chunks = chunk_text(text)
        silence_path = job_dir / "silence.wav"
        write_silence(silence_path, settings.sample_rate, settings.silence_ms)
        chunk_paths: list[Path] = []
        total_seconds = 0.0

        for index, chunk in enumerate(chunks, start=1):
            self._ensure_not_canceled(job_id)
            wav_path = job_dir / f"chunk-{index:04d}.wav"
            audio_segments = []
            for result in self.pipeline(chunk, voice=voice_id, speed=speaking_rate, split_pattern=None):
                if result.audio is None:
                    continue
                audio_segments.append(result.audio.detach().cpu().numpy())
            if not audio_segments:
                continue
            chunk_audio = self._torch.cat([self._torch.tensor(segment) for segment in audio_segments]).numpy()
            sf.write(wav_path, chunk_audio, settings.sample_rate)
            total_seconds += len(chunk_audio) / settings.sample_rate
            chunk_paths.append(wav_path)
            _update_job(
                job_id,
                progress=min(85, int((index / len(chunks)) * 80) + 5),
                progress_message=f"Synthesizing chunk {index}/{len(chunks)}",
            )

        if not chunk_paths:
            raise PermanentJobError("No audio was generated from the provided text.")

        combined_wav = job_dir / "combined.wav"
        combine_wavs(chunk_paths, silence_path, combined_wav)
        mp3_path = settings.audio_dir / f"{job_id}.mp3"
        wav_to_mp3(combined_wav, mp3_path, settings.sample_rate)
        total_seconds += max(0, len(chunk_paths) - 1) * (settings.silence_ms / 1000)
        return mp3_path, total_seconds

    @staticmethod
    def _ensure_not_canceled(job_id: str) -> None:
        with SessionLocal() as session:
            job = session.get(Job, job_id)
            if job and job.status == "canceled":
                raise JobCanceledError("Job canceled.")


def _update_job(job_id: str, **changes) -> None:
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            return
        for key, value in changes.items():
            setattr(job, key, value)
        session.commit()


def _load_job(job_id: str) -> Job | None:
    with SessionLocal() as session:
        return session.get(Job, job_id)


def _cleanup_job_artifacts(job_id: str, job_dir: Path | None = None) -> None:
    if job_dir is None:
        job_dir = settings.tmp_dir / job_id
    shutil.rmtree(job_dir, ignore_errors=True)
    (settings.audio_dir / f"{job_id}.mp3").unlink(missing_ok=True)


def _mark_job_retry(job_id: str, attempt_count: int, message: str) -> None:
    _update_job(
        job_id,
        status="queued",
        progress=0,
        progress_message=f"Retry queued after worker error ({attempt_count}/{settings.max_job_retries + 1} attempts used)",
        error_message=message,
        started_at=None,
        completed_at=None,
    )


def _mark_job_failed(job_id: str, message: str) -> None:
    _update_job(
        job_id,
        status="failed",
        progress_message="Failed",
        error_message=message,
        completed_at=datetime.now(timezone.utc),
    )


def _retryable_failure(message: str) -> bool:
    return "Job canceled." not in message and "No audio was generated" not in message


def process_job(engine: KokoroEngine, job_id: str) -> Literal["completed", "retry", "failed", "canceled", "discarded"]:
    job = _load_job(job_id)
    if job is None:
        return "discarded"
    if job.status == "canceled":
        _cleanup_job_artifacts(job_id)
        return "canceled"

    attempt_count = job.attempt_count + 1

    _update_job(
        job_id,
        status="processing",
        started_at=datetime.now(timezone.utc),
        progress=5,
        progress_message="Preparing text",
        attempt_count=attempt_count,
        completed_at=None,
        error_message=None,
    )

    job_dir = settings.tmp_dir / job_id
    _cleanup_job_artifacts(job_id, job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        text = Path(job.text_path).read_text(encoding="utf-8")
        mp3_path, duration_seconds = engine.synthesize_chunks(text, job.voice_id, job.speaking_rate, job_dir, job_id)
        _update_job(
            job_id,
            status="completed",
            progress=100,
            progress_message="Completed",
            duration_seconds=duration_seconds,
            audio_path=str(mp3_path),
            completed_at=datetime.now(timezone.utc),
            error_message=None,
        )
        return "completed"
    except JobCanceledError:
        _cleanup_job_artifacts(job_id, job_dir)
        _update_job(
            job_id,
            status="canceled",
            progress_message="Canceled",
            completed_at=datetime.now(timezone.utc),
            error_message=None,
        )
        return "canceled"
    except (FileNotFoundError, PermanentJobError) as exc:
        _cleanup_job_artifacts(job_id, job_dir)
        _mark_job_failed(job_id, str(exc))
        return "failed"
    except Exception as exc:
        _cleanup_job_artifacts(job_id, job_dir)
        message = f"{exc}\n{traceback.format_exc()}"
        if attempt_count <= settings.max_job_retries and _retryable_failure(message):
            _mark_job_retry(job_id, attempt_count, message)
            return "retry"
        _mark_job_failed(job_id, message)
        return "failed"
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def handle_reserved_job(engine: KokoroEngine, job_id: str) -> None:
    outcome = process_job(engine, job_id)
    log_event(logger, "job_processed", service="worker", job_id=job_id, outcome=outcome)
    if outcome == "retry":
        requeue_job(job_id)
        return
    if outcome in {"completed", "failed", "canceled", "discarded"}:
        ack_job(job_id)


def reconcile_jobs() -> None:
    pending_ids = set(list_pending_jobs())
    processing_ids = set(list_processing_jobs())
    queued_ids = pending_ids | processing_ids

    with SessionLocal() as session:
        jobs = {job.id: job for job in session.scalars(select(Job)).all()}

        for job_id in list(queued_ids):
            job = jobs.get(job_id)
            if job is None or job.status in {"completed", "failed", "canceled"}:
                clear_job(job_id)

        for job in jobs.values():
            if job.status == "canceled":
                clear_job(job.id)
                _cleanup_job_artifacts(job.id)
                continue

            if job.status == "queued":
                if job.id in processing_ids:
                    requeue_job(job.id)
                    job.progress = 0
                    job.progress_message = "Re-queued after worker restart"
                    job.started_at = None
                elif job.id not in pending_ids:
                    enqueue_job(job.id)
                continue

            if job.status != "processing":
                continue

            if job.attempt_count > settings.max_job_retries:
                clear_job(job.id)
                _cleanup_job_artifacts(job.id)
                job.status = "failed"
                job.progress_message = "Failed after worker restart"
                job.completed_at = datetime.now(timezone.utc)
                job.error_message = "Retry limit reached while recovering a reserved job."
                continue

            job.status = "queued"
            job.progress = 0
            job.progress_message = "Re-queued after worker restart"
            job.started_at = None
            job.completed_at = None
            if job.id in processing_ids:
                requeue_job(job.id)
            elif job.id not in pending_ids:
                enqueue_job(job.id)

        session.commit()


def main() -> None:
    configure_json_logging("worker")
    for directory in [settings.uploads_dir, settings.audio_dir, settings.tmp_dir, settings.db_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    init_db()
    retention_result = sweep_retention()
    log_event(logger, "retention_sweep", service="worker", **retention_result)
    reconcile_jobs()
    engine = KokoroEngine()
    publish_capabilities(engine.capabilities())
    last_retention_sweep = time.monotonic()
    while True:
        record_worker_heartbeat()
        job_id = reserve_job()
        if job_id:
            log_event(logger, "job_reserved", service="worker", job_id=job_id, **queue_depth())
            handle_reserved_job(engine, job_id)
        if time.monotonic() - last_retention_sweep >= settings.retention_sweep_interval_seconds:
            retention_result = sweep_retention()
            log_event(logger, "retention_sweep", service="worker", **retention_result)
            last_retention_sweep = time.monotonic()


if __name__ == "__main__":
    main()
