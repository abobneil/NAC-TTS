from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlparse


@dataclass(frozen=True)
class VoiceOption:
    id: str
    label: str


def _csv_env(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _validate_origin(origin: str) -> str:
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"CORS origin '{origin}' must be an absolute http(s) origin.")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"CORS origin '{origin}' must not include a path, query string, or fragment.")
    return f"{parsed.scheme}://{parsed.netloc}"


def _validate_shared_secret(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} must not be empty.")
    if normalized in {
        "change-me-access-token",
        "change-me-session-secret",
        "replace-with-a-long-random-token",
        "replace-with-a-different-long-random-secret",
    }:
        raise ValueError(f"{name} must be replaced with a real random secret before starting the app.")
    return normalized


def _voice_label(voice_id: str) -> str:
    parts = voice_id.split("_", 1)
    if len(parts) == 2:
        prefix, name = parts
        return f"{prefix.upper()} {name.replace('_', ' ').title()}"
    return voice_id


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    storage_root: Path
    uploads_dir: Path
    audio_dir: Path
    tmp_dir: Path
    db_dir: Path
    model_id: str
    lang_code: str
    kokoro_device: str
    voices: list[VoiceOption]
    max_upload_mb: int
    max_pages: int
    max_chars: int
    max_active_jobs: int
    max_job_retries: int
    queue_name: str
    worker_heartbeat_ttl_seconds: int
    tmp_retention_hours: int
    audio_retention_days: int
    retention_sweep_interval_seconds: int
    cors_allow_origins: list[str]
    app_access_token: str
    auth_session_secret: str
    auth_cookie_secure: bool
    auth_session_ttl_seconds: int
    sample_rate: int = 24000
    silence_ms: int = 350


def get_settings() -> Settings:
    storage_root = Path(os.getenv("STORAGE_ROOT", "/data"))
    voice_ids = [
        voice.strip()
        for voice in os.getenv("KOKORO_VOICES", "af_heart,af_bella,am_adam,bf_emma,bm_george").split(",")
        if voice.strip()
    ]
    cors_allow_origins = [
        _validate_origin(origin)
        for origin in _csv_env(
            "CORS_ALLOW_ORIGINS",
            "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173",
        )
    ]
    app_access_token = _validate_shared_secret(
        "APP_ACCESS_TOKEN",
        os.getenv("APP_ACCESS_TOKEN", "change-me-access-token"),
    )
    auth_session_secret = _validate_shared_secret(
        "AUTH_SESSION_SECRET",
        os.getenv("AUTH_SESSION_SECRET", "change-me-session-secret"),
    )
    if app_access_token == auth_session_secret:
        raise ValueError("APP_ACCESS_TOKEN and AUTH_SESSION_SECRET must be different secrets.")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:////data/db/nac_tts.sqlite3"),
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        storage_root=storage_root,
        uploads_dir=storage_root / "uploads",
        audio_dir=storage_root / "audio",
        tmp_dir=storage_root / "tmp",
        db_dir=storage_root / "db",
        model_id=os.getenv("TTS_MODEL_ID", "hexgrad/Kokoro-82M"),
        lang_code=os.getenv("KOKORO_LANG_CODE", "a"),
        kokoro_device=os.getenv("KOKORO_DEVICE", "cuda"),
        voices=[VoiceOption(id=voice_id, label=_voice_label(voice_id)) for voice_id in voice_ids],
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "25")),
        max_pages=int(os.getenv("MAX_PAGES", "100")),
        max_chars=int(os.getenv("MAX_CHARS", "80000")),
        max_active_jobs=int(os.getenv("MAX_ACTIVE_JOBS", "2")),
        max_job_retries=int(os.getenv("MAX_JOB_RETRIES", "2")),
        queue_name=os.getenv("QUEUE_NAME", "tts:jobs"),
        worker_heartbeat_ttl_seconds=int(os.getenv("WORKER_HEARTBEAT_TTL_SECONDS", "30")),
        tmp_retention_hours=int(os.getenv("TMP_RETENTION_HOURS", "12")),
        audio_retention_days=int(os.getenv("AUDIO_RETENTION_DAYS", "30")),
        retention_sweep_interval_seconds=int(os.getenv("RETENTION_SWEEP_INTERVAL_SECONDS", "300")),
        cors_allow_origins=cors_allow_origins,
        app_access_token=app_access_token,
        auth_session_secret=auth_session_secret,
        auth_cookie_secure=_bool_env("AUTH_COOKIE_SECURE", False),
        auth_session_ttl_seconds=int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(12 * 60 * 60))),
    )
