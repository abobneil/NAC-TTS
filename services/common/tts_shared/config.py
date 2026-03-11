from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class VoiceOption:
    id: str
    label: str


def _csv_env(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


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
    queue_name: str
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
        queue_name=os.getenv("QUEUE_NAME", "tts:jobs"),
        cors_allow_origins=_csv_env(
            "CORS_ALLOW_ORIGINS",
            "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173",
        ),
        app_access_token=os.getenv("APP_ACCESS_TOKEN", "change-me-access-token"),
        auth_session_secret=os.getenv("AUTH_SESSION_SECRET", "change-me-session-secret"),
        auth_cookie_secure=_bool_env("AUTH_COOKIE_SECURE", False),
        auth_session_ttl_seconds=int(os.getenv("AUTH_SESSION_TTL_SECONDS", str(12 * 60 * 60))),
    )
