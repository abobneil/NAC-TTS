from __future__ import annotations

from pathlib import Path
import importlib
import sys

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "common"))
sys.path.insert(0, str(ROOT / "services" / "api"))


def load_app(tmp_path: Path, monkeypatch):
    storage_root = tmp_path / "storage"
    for name in ["uploads", "audio", "tmp", "db"]:
        (storage_root / name).mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(storage_root / 'db' / 'test.sqlite3').as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("MAX_CHARS", "50")
    monkeypatch.setenv("KOKORO_VOICES", "af_heart,af_bella")

    for module_name in list(sys.modules):
        if module_name.startswith("tts_shared") or module_name.startswith("app"):
            sys.modules.pop(module_name)

    module = importlib.import_module("app.main")
    monkeypatch.setattr(module, "enqueue_job", lambda job_id: None)
    monkeypatch.setattr(module, "read_capabilities", lambda: None)
    return module.app


def test_create_text_job(tmp_path: Path, monkeypatch) -> None:
    app = load_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            data={
                "title": "Drive copy",
                "source_type": "text",
                "text": "Short text for synthesis.",
                "voice_id": "af_heart",
                "speaking_rate": "1.0",
                "output_format": "mp3",
            },
        )

        assert response.status_code == 202
        payload = response.json()
        detail = client.get(f"/api/v1/jobs/{payload['job_id']}").json()
        assert detail["title"] == "Drive copy"
        assert detail["status"] == "queued"


def test_rejects_over_limit_text(tmp_path: Path, monkeypatch) -> None:
    app = load_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            data={
                "title": "Too long",
                "source_type": "text",
                "text": "x" * 100,
                "voice_id": "af_heart",
                "speaking_rate": "1.0",
                "output_format": "mp3",
            },
        )

        assert response.status_code == 422
        assert "50 characters" in response.json()["detail"]
