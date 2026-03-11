from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VoiceSchema(BaseModel):
    id: str
    label: str


class LimitsSchema(BaseModel):
    max_upload_mb: int
    max_pages: int
    max_chars: int


class CapabilitiesSchema(BaseModel):
    device: str
    model_id: str
    voices: list[VoiceSchema]
    formats: list[str]
    limits: LimitsSchema
    sample_rate: int


class AuthLoginSchema(BaseModel):
    access_token: str


class AuthSessionSchema(BaseModel):
    authenticated: bool


class JobSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    source_type: str
    source_filename: str | None
    status: str
    progress: int
    progress_message: str | None
    voice_id: str
    speaking_rate: float
    char_count: int
    page_count: int | None
    duration_seconds: float | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    audio_url: str | None = None


class JobListSchema(BaseModel):
    items: list[JobSchema]
    total: int


class JobCreatedSchema(BaseModel):
    job_id: str
    status: str
