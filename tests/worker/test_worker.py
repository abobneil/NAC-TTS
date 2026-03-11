from __future__ import annotations

from pathlib import Path
import importlib
import importlib.util
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "common"))


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.values: dict[str, str] = {}

    def lpush(self, name: str, value: str) -> None:
        self.lists.setdefault(name, []).insert(0, value)

    def lrem(self, name: str, count: int, value: str) -> int:
        items = self.lists.setdefault(name, [])
        removed = 0
        while value in items and (count == 0 or removed < count):
            items.remove(value)
            removed += 1
        return removed

    def brpoplpush(self, source: str, destination: str, timeout: int = 0) -> str | None:
        items = self.lists.setdefault(source, [])
        if not items:
            return None
        value = items.pop()
        self.lists.setdefault(destination, []).insert(0, value)
        return value

    def lrange(self, name: str, start: int, end: int) -> list[str]:
        items = self.lists.get(name, [])
        if end == -1:
            end = len(items) - 1
        return items[start : end + 1]

    def llen(self, name: str) -> int:
        return len(self.lists.get(name, []))

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def get(self, name: str) -> str | None:
        return self.values.get(name)


def configure_test_env(tmp_path: Path, monkeypatch, max_job_retries: int = 1) -> Path:
    storage_root = tmp_path / "storage"
    for name in ["uploads", "audio", "tmp", "db"]:
        (storage_root / name).mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(storage_root / 'db' / 'worker.sqlite3').as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/14")
    monkeypatch.setenv("MAX_JOB_RETRIES", str(max_job_retries))
    monkeypatch.setenv("KOKORO_VOICES", "af_heart")
    return storage_root


def load_queue_module(tmp_path: Path, monkeypatch):
    configure_test_env(tmp_path, monkeypatch)
    for module_name in list(sys.modules):
        if module_name.startswith("tts_shared"):
            sys.modules.pop(module_name)
    return importlib.import_module("tts_shared.queue")


def load_worker_module(tmp_path: Path, monkeypatch, max_job_retries: int = 1):
    configure_test_env(tmp_path, monkeypatch, max_job_retries=max_job_retries)
    for module_name in list(sys.modules):
        if module_name.startswith("tts_shared") or module_name == "worker_app_main":
            sys.modules.pop(module_name)

    module_path = ROOT / "services" / "worker" / "app" / "main.py"
    spec = importlib.util.spec_from_file_location("worker_app_main", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["worker_app_main"] = module
    spec.loader.exec_module(module)
    return module


def create_job(module, job_id: str, *, status: str = "queued", attempt_count: int = 0, text: str = "hello there"):
    text_path = module.settings.tmp_dir / f"{job_id}.txt"
    text_path.write_text(text, encoding="utf-8")

    with module.SessionLocal() as session:
        job = module.Job(
            id=job_id,
            title=job_id,
            source_type="text",
            source_filename=None,
            source_path=None,
            text_path=str(text_path),
            status=status,
            progress=0,
            progress_message="Queued",
            voice_id="af_heart",
            speaking_rate=1.0,
            char_count=len(text),
            attempt_count=attempt_count,
            page_count=None,
        )
        session.add(job)
        session.commit()


def test_queue_reservation_ack_and_requeue(tmp_path: Path, monkeypatch) -> None:
    queue_module = load_queue_module(tmp_path, monkeypatch)
    fake_redis = FakeRedis()
    monkeypatch.setattr(queue_module, "get_redis", lambda: fake_redis)

    queue_module.enqueue_job("job-1")
    assert queue_module.list_pending_jobs() == ["job-1"]
    assert queue_module.reserve_job(timeout_seconds=0) == "job-1"
    assert queue_module.list_processing_jobs() == ["job-1"]

    queue_module.requeue_job("job-1")
    assert queue_module.list_pending_jobs() == ["job-1"]
    assert queue_module.list_processing_jobs() == []

    assert queue_module.reserve_job(timeout_seconds=0) == "job-1"
    queue_module.ack_job("job-1")
    assert queue_module.list_pending_jobs() == []
    assert queue_module.list_processing_jobs() == []


def test_handle_reserved_job_requeues_retryable_failures(tmp_path: Path, monkeypatch) -> None:
    module = load_worker_module(tmp_path, monkeypatch, max_job_retries=1)
    module.init_db()
    create_job(module, "retry-job")

    events: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "requeue_job", lambda job_id: events.append(("requeue", job_id)))
    monkeypatch.setattr(module, "ack_job", lambda job_id: events.append(("ack", job_id)))

    class RetryEngine:
        def synthesize_chunks(self, *_args, **_kwargs):
            raise RuntimeError("temporary synthesis failure")

    module.handle_reserved_job(RetryEngine(), "retry-job")

    with module.SessionLocal() as session:
        job = session.get(module.Job, "retry-job")
        assert job
        assert job.status == "queued"
        assert job.attempt_count == 1
        assert "Retry queued after worker error" in (job.progress_message or "")

    assert events == [("requeue", "retry-job")]


def test_handle_reserved_job_marks_failure_after_retry_limit(tmp_path: Path, monkeypatch) -> None:
    module = load_worker_module(tmp_path, monkeypatch, max_job_retries=1)
    module.init_db()
    create_job(module, "failed-job", attempt_count=1)

    events: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "requeue_job", lambda job_id: events.append(("requeue", job_id)))
    monkeypatch.setattr(module, "ack_job", lambda job_id: events.append(("ack", job_id)))

    class FailingEngine:
        def synthesize_chunks(self, *_args, **_kwargs):
            raise RuntimeError("persistent synthesis failure")

    module.handle_reserved_job(FailingEngine(), "failed-job")

    with module.SessionLocal() as session:
        job = session.get(module.Job, "failed-job")
        assert job
        assert job.status == "failed"
        assert job.attempt_count == 2

    assert events == [("ack", "failed-job")]


def test_handle_reserved_job_marks_canceled_jobs_terminal(tmp_path: Path, monkeypatch) -> None:
    module = load_worker_module(tmp_path, monkeypatch, max_job_retries=1)
    module.init_db()
    create_job(module, "canceled-job")

    events: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "requeue_job", lambda job_id: events.append(("requeue", job_id)))
    monkeypatch.setattr(module, "ack_job", lambda job_id: events.append(("ack", job_id)))

    class CancelingEngine:
        def synthesize_chunks(self, *_args, **_kwargs):
            raise module.JobCanceledError("Job canceled.")

    module.handle_reserved_job(CancelingEngine(), "canceled-job")

    with module.SessionLocal() as session:
        job = session.get(module.Job, "canceled-job")
        assert job
        assert job.status == "canceled"

    assert events == [("ack", "canceled-job")]


def test_reconcile_jobs_requeues_processing_and_cleans_stale_entries(tmp_path: Path, monkeypatch) -> None:
    module = load_worker_module(tmp_path, monkeypatch, max_job_retries=1)
    module.init_db()
    create_job(module, "stuck-processing", status="processing", attempt_count=1)
    create_job(module, "queued-missing", status="queued")
    create_job(module, "exhausted-processing", status="processing", attempt_count=2)
    create_job(module, "canceled-job", status="canceled")
    create_job(module, "completed-job", status="completed")

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(module, "list_pending_jobs", lambda: [])
    monkeypatch.setattr(module, "list_processing_jobs", lambda: ["stuck-processing", "completed-job"])
    monkeypatch.setattr(module, "enqueue_job", lambda job_id: calls.append(("enqueue", job_id)))
    monkeypatch.setattr(module, "requeue_job", lambda job_id: calls.append(("requeue", job_id)))
    monkeypatch.setattr(module, "clear_job", lambda job_id: calls.append(("clear", job_id)))

    module.reconcile_jobs()

    with module.SessionLocal() as session:
        stuck = session.get(module.Job, "stuck-processing")
        queued = session.get(module.Job, "queued-missing")
        exhausted = session.get(module.Job, "exhausted-processing")
        canceled = session.get(module.Job, "canceled-job")
        assert stuck and stuck.status == "queued"
        assert queued and queued.status == "queued"
        assert exhausted and exhausted.status == "failed"
        assert canceled and canceled.status == "canceled"

    assert ("requeue", "stuck-processing") in calls
    assert ("enqueue", "queued-missing") in calls
    assert ("clear", "completed-job") in calls
    assert ("clear", "canceled-job") in calls
    assert ("clear", "exhausted-processing") in calls
