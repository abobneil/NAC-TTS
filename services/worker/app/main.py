from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import shutil
import traceback

import soundfile as sf
import torch
from kokoro import KPipeline

from tts_shared.audio_utils import combine_wavs, wav_to_mp3, write_silence
from tts_shared.config import get_settings
from tts_shared.database import SessionLocal, init_db
from tts_shared.models import Job
from tts_shared.queue import pop_job, publish_capabilities
from tts_shared.text_utils import chunk_text


settings = get_settings()


class KokoroEngine:
    def __init__(self) -> None:
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
            chunk_audio = torch.cat([torch.tensor(segment) for segment in audio_segments]).numpy()
            sf.write(wav_path, chunk_audio, settings.sample_rate)
            total_seconds += len(chunk_audio) / settings.sample_rate
            chunk_paths.append(wav_path)
            _update_job(
                job_id,
                progress=min(85, int((index / len(chunks)) * 80) + 5),
                progress_message=f"Synthesizing chunk {index}/{len(chunks)}",
            )

        if not chunk_paths:
            raise RuntimeError("No audio was generated from the provided text.")

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
                raise RuntimeError("Job canceled.")


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


def process_job(engine: KokoroEngine, job_id: str) -> None:
    job = _load_job(job_id)
    if job is None or job.status == "canceled":
        return

    _update_job(
        job_id,
        status="processing",
        started_at=datetime.now(timezone.utc),
        progress=5,
        progress_message="Preparing text",
    )

    text = Path(job.text_path).read_text(encoding="utf-8")
    job_dir = settings.tmp_dir / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
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
    except RuntimeError as exc:
        if str(exc) == "Job canceled.":
            _update_job(job_id, progress_message="Canceled")
        else:
            _update_job(
                job_id,
                status="failed",
                progress_message="Failed",
                error_message=str(exc),
                completed_at=datetime.now(timezone.utc),
            )
    except Exception as exc:  # pragma: no cover
        _update_job(
            job_id,
            status="failed",
            progress_message="Failed",
            error_message=f"{exc}\n{traceback.format_exc()}",
            completed_at=datetime.now(timezone.utc),
        )
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def main() -> None:
    for directory in [settings.uploads_dir, settings.audio_dir, settings.tmp_dir, settings.db_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    init_db()
    engine = KokoroEngine()
    publish_capabilities(engine.capabilities())
    while True:
        job_id = pop_job()
        if job_id:
            process_job(engine, job_id)


if __name__ == "__main__":
    main()
