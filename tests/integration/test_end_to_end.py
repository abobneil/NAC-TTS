from __future__ import annotations

from pathlib import Path
import importlib
import importlib.util
import sys

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "common"))
sys.path.insert(0, str(ROOT / "services" / "api"))

AUTH_TOKEN = "test-access-token"


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


def configure_env(tmp_path: Path, monkeypatch) -> None:
    storage_root = tmp_path / "storage"
    for name in ["uploads", "audio", "tmp", "db"]:
        (storage_root / name).mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(storage_root / 'db' / 'integration.sqlite3').as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/12")
    monkeypatch.setenv("KOKORO_VOICES", "af_heart")
    monkeypatch.setenv("APP_ACCESS_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("AUTH_SESSION_SECRET", "integration-session-secret")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:8080")


def load_modules(tmp_path: Path, monkeypatch):
    configure_env(tmp_path, monkeypatch)
    for module_name in list(sys.modules):
        if module_name.startswith("tts_shared") or module_name.startswith("app") or module_name == "worker_app_main":
            sys.modules.pop(module_name)

    api_module = importlib.import_module("app.main")
    worker_spec = importlib.util.spec_from_file_location("worker_app_main", ROOT / "services" / "worker" / "app" / "main.py")
    assert worker_spec and worker_spec.loader
    worker_module = importlib.util.module_from_spec(worker_spec)
    sys.modules["worker_app_main"] = worker_module
    worker_spec.loader.exec_module(worker_module)

    queue_module = importlib.import_module("tts_shared.queue")
    fake_redis = FakeRedis()
    monkeypatch.setattr(queue_module, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(api_module, "read_capabilities", lambda: None)
    return api_module, worker_module, queue_module


def login_client(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"access_token": AUTH_TOKEN})
    assert response.status_code == 204


def test_create_process_download_and_delete_job(tmp_path: Path, monkeypatch) -> None:
    api_module, worker_module, queue_module = load_modules(tmp_path, monkeypatch)

    class FakeEngine:
        def synthesize_chunks(self, _text: str, _voice_id: str, _speaking_rate: float, _job_dir: Path, job_id: str):
            output_path = worker_module.settings.audio_dir / f"{job_id}.mp3"
            output_path.write_bytes(b"fake-mp3")
            return output_path, 1.25

    with TestClient(api_module.app) as client:
        login_client(client)
        create_response = client.post(
            "/api/v1/jobs",
            data={
                "title": "Integration Job",
                "source_type": "text",
                "text": "Hello integration coverage.",
                "voice_id": "af_heart",
                "speaking_rate": "1.0",
                "output_format": "mp3",
            },
        )
        assert create_response.status_code == 202
        job_id = create_response.json()["job_id"]

        reserved = queue_module.reserve_job(timeout_seconds=0)
        assert reserved == job_id
        worker_module.handle_reserved_job(FakeEngine(), job_id)

        detail = client.get(f"/api/v1/jobs/{job_id}")
        assert detail.status_code == 200
        assert detail.json()["status"] == "completed"
        assert detail.json()["audio_url"] == f"/api/v1/jobs/{job_id}/file"

        listing = client.get("/api/v1/jobs")
        assert listing.status_code == 200
        assert listing.json()["items"][0]["id"] == job_id

        download = client.get(f"/api/v1/jobs/{job_id}/file")
        assert download.status_code == 200
        assert download.content == b"fake-mp3"

        delete_response = client.delete(f"/api/v1/jobs/{job_id}")
        assert delete_response.status_code == 204
