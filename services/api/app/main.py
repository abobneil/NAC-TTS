from __future__ import annotations

from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
import logging
import secrets
from threading import Lock
import time
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import func, select
from starlette.middleware.sessions import SessionMiddleware

from .auth import is_authenticated, require_auth
from tts_shared.config import get_settings
from tts_shared.database import SessionLocal, init_db
from tts_shared.logging_utils import configure_json_logging, log_event
from tts_shared.models import Job
from tts_shared.pdf_utils import PdfValidationError, extract_text_from_pdf
from tts_shared.queue import clear_job, enqueue_job, queue_depth, read_capabilities, read_worker_heartbeat, remove_pending_job
from tts_shared.retention import sweep_retention
from tts_shared.schemas import (
    AuthLoginSchema,
    AuthSessionSchema,
    CapabilitiesSchema,
    JobCreatedSchema,
    JobListSchema,
    JobSchema,
    LimitsSchema,
    VoiceSchema,
)
from tts_shared.text_utils import normalize_text


settings = get_settings()
logger = logging.getLogger("nac_tts.api")
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_BLOCK_SECONDS = 15 * 60
_LOGIN_ATTEMPTS: dict[str, deque[float]] = {}
_LOGIN_BLOCKED_UNTIL: dict[str, float] = {}
_LOGIN_LOCK = Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_json_logging("api")
    for directory in [settings.uploads_dir, settings.audio_dir, settings.tmp_dir, settings.db_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    init_db()
    retention_result = sweep_retention()
    log_event(logger, "retention_sweep", service="api", **retention_result)
    yield


app = FastAPI(title="NAC-TTS API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.auth_session_secret,
    same_site="lax",
    https_only=settings.auth_cookie_secure,
    max_age=settings.auth_session_ttl_seconds,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def set_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    log_event(
        logger,
        "http_request",
        service="api",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


def to_job_schema(job: Job) -> JobSchema:
    audio_url = None
    if job.audio_path and job.status == "completed":
        audio_url = f"/api/v1/jobs/{job.id}/file"
    return JobSchema.model_validate(job, from_attributes=True).model_copy(update={"audio_url": audio_url})


def _client_address(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _prune_login_attempts(client_address: str, now: float) -> deque[float]:
    attempts = _LOGIN_ATTEMPTS.setdefault(client_address, deque())
    cutoff = now - LOGIN_WINDOW_SECONDS
    while attempts and attempts[0] <= cutoff:
        attempts.popleft()
    if not attempts:
        _LOGIN_ATTEMPTS.pop(client_address, None)
        return deque()
    return attempts


def _enforce_login_rate_limit(request: Request) -> None:
    client_address = _client_address(request)
    now = time.time()
    with _LOGIN_LOCK:
        blocked_until = _LOGIN_BLOCKED_UNTIL.get(client_address)
        if blocked_until is not None:
            if now < blocked_until:
                raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
            _LOGIN_BLOCKED_UNTIL.pop(client_address, None)
        attempts = _prune_login_attempts(client_address, now)
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            _LOGIN_BLOCKED_UNTIL[client_address] = now + LOGIN_BLOCK_SECONDS
            _LOGIN_ATTEMPTS.pop(client_address, None)
            raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")


def _record_failed_login(request: Request) -> None:
    client_address = _client_address(request)
    now = time.time()
    with _LOGIN_LOCK:
        attempts = _prune_login_attempts(client_address, now)
        if not attempts:
            attempts = _LOGIN_ATTEMPTS.setdefault(client_address, deque())
        attempts.append(now)
        if len(attempts) >= LOGIN_MAX_ATTEMPTS:
            _LOGIN_BLOCKED_UNTIL[client_address] = now + LOGIN_BLOCK_SECONDS
            _LOGIN_ATTEMPTS.pop(client_address, None)


def _clear_failed_logins(request: Request) -> None:
    client_address = _client_address(request)
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.pop(client_address, None)
        _LOGIN_BLOCKED_UNTIL.pop(client_address, None)


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/ready")
def readiness() -> JSONResponse:
    try:
        with SessionLocal() as session:
            session.execute(select(1))
        depths = queue_depth()
        heartbeat = read_worker_heartbeat()
    except Exception as exc:
        log_event(logger, "readiness_failed", service="api", error=str(exc))
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "api": "ok", "redis": "down", "worker": "unknown"},
        )

    now = time.time()
    worker_ok = heartbeat is not None and (now - heartbeat) <= settings.worker_heartbeat_ttl_seconds
    status_code = 200 if worker_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if worker_ok else "degraded",
            "api": "ok",
            "redis": "ok",
            "worker": {
                "status": "ok" if worker_ok else "stale",
                "last_heartbeat": heartbeat,
            },
            "queue": depths,
        },
    )


@app.post("/api/v1/auth/login", status_code=204, response_class=Response)
def login(payload: AuthLoginSchema, request: Request) -> Response:
    _enforce_login_rate_limit(request)
    if not secrets.compare_digest(payload.access_token, settings.app_access_token):
        _record_failed_login(request)
        raise HTTPException(
            status_code=401,
            detail="Invalid access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    request.session.clear()
    request.session["authenticated"] = True
    _clear_failed_logins(request)
    log_event(logger, "login_succeeded", service="api")
    return Response(status_code=204)


@app.post("/api/v1/auth/logout", status_code=204, response_class=Response)
def logout(request: Request) -> Response:
    request.session.clear()
    log_event(logger, "logout_succeeded", service="api")
    return Response(status_code=204)


@app.get("/api/v1/auth/session", response_model=AuthSessionSchema)
def auth_session(request: Request) -> AuthSessionSchema:
    return AuthSessionSchema(authenticated=is_authenticated(request))


@app.get("/api/v1/capabilities", response_model=CapabilitiesSchema, dependencies=[Depends(require_auth)])
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
    value = "".join(char for char in title.strip() if char.isprintable()).replace("/", "-").replace("\\", "-")
    if value:
        return value[:255]
    safe_fallback = "".join(char for char in fallback.strip() if char.isprintable()).replace("/", "-").replace("\\", "-")
    return safe_fallback[:255] or "Untitled"


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


@app.post("/api/v1/jobs", response_model=JobCreatedSchema, status_code=202, dependencies=[Depends(require_auth)])
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
            attempt_count=0,
            page_count=page_count,
        )
        session.add(job)
        session.commit()

    enqueue_job(job_id)
    return JobCreatedSchema(job_id=job_id, status="queued")


@app.get("/api/v1/jobs", response_model=JobListSchema, dependencies=[Depends(require_auth)])
def list_jobs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)) -> JobListSchema:
    with SessionLocal() as session:
        items = session.scalars(select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset)).all()
        total = int(session.scalar(select(func.count()).select_from(Job)) or 0)
    return JobListSchema(items=[to_job_schema(item) for item in items], total=total)


@app.get("/api/v1/jobs/{job_id}", response_model=JobSchema, dependencies=[Depends(require_auth)])
def get_job(job_id: str) -> JobSchema:
    with SessionLocal() as session:
        job = _get_job_or_404(session, job_id)
        return to_job_schema(job)


@app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobSchema, dependencies=[Depends(require_auth)])
def cancel_job(job_id: str) -> JobSchema:
    with SessionLocal() as session:
        job = _get_job_or_404(session, job_id)
        if job.status in {"completed", "failed"}:
            raise HTTPException(status_code=409, detail="Completed or failed jobs cannot be canceled.")
        if job.status == "queued":
            remove_pending_job(job.id)
        job.status = "canceled"
        job.progress_message = "Canceled"
        session.commit()
        session.refresh(job)
        return to_job_schema(job)


@app.get("/api/v1/jobs/{job_id}/file", dependencies=[Depends(require_auth)])
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


@app.delete("/api/v1/jobs/{job_id}", status_code=204, response_class=Response, dependencies=[Depends(require_auth)])
def delete_job(job_id: str) -> Response:
    with SessionLocal() as session:
        job = _get_job_or_404(session, job_id)
        if job.status in {"queued", "processing"}:
            raise HTTPException(status_code=409, detail="Cancel active jobs before deleting them.")
        clear_job(job.id)
        if job.audio_path:
            Path(job.audio_path).unlink(missing_ok=True)
        if job.source_path:
            Path(job.source_path).unlink(missing_ok=True)
        Path(job.text_path).unlink(missing_ok=True)
        session.delete(job)
        session.commit()
    return Response(status_code=204)
