from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select

from tts_shared.config import get_settings
from tts_shared.database import SessionLocal, init_db
from tts_shared.models import Job
from tts_shared.pdf_utils import PdfValidationError, extract_text_from_pdf
from tts_shared.queue import enqueue_job, read_capabilities
from tts_shared.schemas import CapabilitiesSchema, JobCreatedSchema, JobListSchema, JobSchema, LimitsSchema, VoiceSchema
from tts_shared.text_utils import normalize_text


settings = get_settings()
app = FastAPI(title="NAC-TTS API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def to_job_schema(job: Job) -> JobSchema:
    audio_url = None
    if job.audio_path and job.status == "completed":
        audio_url = f"/api/v1/jobs/{job.id}/file"
    return JobSchema.model_validate(job, from_attributes=True).model_copy(update={"audio_url": audio_url})


@app.on_event("startup")
def startup() -> None:
    for directory in [settings.uploads_dir, settings.audio_dir, settings.tmp_dir, settings.db_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/capabilities", response_model=CapabilitiesSchema)
def capabilities() -> CapabilitiesSchema:
    payload = read_capabilities()
    if payload:
        return CapabilitiesSchema.model_validate(payload)
    return CapabilitiesSchema(
        device=settings.kokoro_device,
        model_id=settings.model_id,
        voices=[VoiceSchema(id=voice.id, label=voice.label) for voice in settings.voices],
        formats=["mp3"],
        limits=LimitsSchema(
            max_upload_mb=settings.max_upload_mb,
            max_pages=settings.max_pages,
            max_chars=settings.max_chars,
        ),
        sample_rate=settings.sample_rate,
    )


def _ensure_voice(voice_id: str) -> None:
    allowed = {voice.id for voice in settings.voices}
    if voice_id not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported voice selection.")


def _sanitize_title(title: str, fallback: str) -> str:
    value = title.strip()
    if value:
        return value[:255]
    return fallback[:255] or "Untitled"


def _persist_text(job_id: str, text: str) -> Path:
    path = settings.tmp_dir / f"{job_id}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _active_job_count(session) -> int:
    stmt = select(func.count()).select_from(Job).where(Job.status.in_(["queued", "processing"]))
    return int(session.scalar(stmt) or 0)


def _get_job_or_404(session, job_id: str) -> Job:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.post("/api/v1/jobs", response_model=JobCreatedSchema, status_code=202)
async def create_job(
    title: str = Form(""),
    source_type: str = Form(...),
    text: str = Form(""),
    voice_id: str = Form(...),
    speaking_rate: float = Form(1.0),
    output_format: str = Form(...),
    file: UploadFile | None = File(None),
) -> JobCreatedSchema:
    if output_format != "mp3":
        raise HTTPException(status_code=422, detail="Only MP3 output is supported.")
    if source_type not in {"text", "pdf"}:
        raise HTTPException(status_code=422, detail="source_type must be text or pdf.")
    if not 0.7 <= speaking_rate <= 1.4:
        raise HTTPException(status_code=422, detail="speaking_rate must be between 0.7 and 1.4.")

    _ensure_voice(voice_id)
    job_id = str(uuid4())
    source_filename: str | None = None
    source_path: Path | None = None
    page_count: int | None = None

    if source_type == "text":
        normalized_text = normalize_text(text)
        if not normalized_text:
            raise HTTPException(status_code=422, detail="Text input is required.")
        fallback_title = normalized_text[:80]
    else:
        if file is None or not file.filename:
            raise HTTPException(status_code=422, detail="A PDF file is required.")
        if file.content_type not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=422, detail="Uploaded file must be a PDF.")
        raw = await file.read()
        if len(raw) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.max_upload_mb} MB.")
        if not raw.startswith(b"%PDF"):
            raise HTTPException(status_code=422, detail="Uploaded file is not a valid PDF.")
        source_filename = Path(file.filename).name
        source_path = settings.uploads_dir / f"{job_id}.pdf"
        source_path.write_bytes(raw)
        try:
            normalized_text, page_count = extract_text_from_pdf(source_path, settings.max_pages)
        except PdfValidationError as exc:
            source_path.unlink(missing_ok=True)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        fallback_title = source_filename.rsplit(".", 1)[0]

    if len(normalized_text) > settings.max_chars:
        if source_path:
            source_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Text exceeds {settings.max_chars} characters.")

    text_path = _persist_text(job_id, normalized_text)
    with SessionLocal() as session:
        if _active_job_count(session) >= settings.max_active_jobs:
            raise HTTPException(status_code=429, detail="Too many active jobs. Wait for one to finish.")
        job = Job(
            id=job_id,
            title=_sanitize_title(title, fallback_title),
            source_type=source_type,
            source_filename=source_filename,
            source_path=str(source_path) if source_path else None,
            text_path=str(text_path),
            status="queued",
            progress=0,
            progress_message="Queued",
            voice_id=voice_id,
            speaking_rate=speaking_rate,
            char_count=len(normalized_text),
            page_count=page_count,
        )
        session.add(job)
        session.commit()

    enqueue_job(job_id)
    return JobCreatedSchema(job_id=job_id, status="queued")


@app.get("/api/v1/jobs", response_model=JobListSchema)
def list_jobs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> JobListSchema:
    with SessionLocal() as session:
        items = session.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset)).all()
        total = int(session.scalar(select(func.count()).select_from(Job)) or 0)
    return JobListSchema(items=[to_job_schema(item) for item in items], total=total)


@app.get("/api/v1/jobs/{job_id}", response_model=JobSchema)
def get_job(job_id: str) -> JobSchema:
    with SessionLocal() as session:
        job = _get_job_or_404(session, job_id)
        return to_job_schema(job)


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobSchema)
def cancel_job(job_id: str) -> JobSchema:
    with SessionLocal() as session:
        job = _get_job_or_404(session, job_id)
        if job.status in {"completed", "failed"}:
            raise HTTPException(status_code=409, detail="Completed or failed jobs cannot be canceled.")
        job.status = "canceled"
        job.progress_message = "Canceled"
        session.commit()
        session.refresh(job)
        return to_job_schema(job)


@app.get("/api/v1/jobs/{job_id}/file")
def get_audio_file(job_id: str) -> FileResponse:
    with SessionLocal() as session:
        job = _get_job_or_404(session, job_id)
        if job.status != "completed" or not job.audio_path:
            raise HTTPException(status_code=404, detail="Audio file not available.")
        path = Path(job.audio_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio file missing.")
        filename = f"{job.title}.mp3".replace("/", "-")
        return FileResponse(path=path, media_type="audio/mpeg", filename=filename)


@app.delete("/api/v1/jobs/{job_id}", status_code=204, response_class=Response)
def delete_job(job_id: str) -> Response:
    with SessionLocal() as session:
        job = _get_job_or_404(session, job_id)
        if job.audio_path:
            Path(job.audio_path).unlink(missing_ok=True)
        if job.source_path:
            Path(job.source_path).unlink(missing_ok=True)
        Path(job.text_path).unlink(missing_ok=True)
        session.delete(job)
        session.commit()
    return Response(status_code=204)
