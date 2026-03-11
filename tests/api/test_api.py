from __future__ import annotations

from pathlib import Path
import importlib
import sys

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "common"))
sys.path.insert(0, str(ROOT / "services" / "api"))
AUTH_TOKEN = "test-access-token"


def load_app(tmp_path: Path, monkeypatch):
    storage_root = tmp_path / "storage"
    for name in ["uploads", "audio", "tmp", "db"]:
        (storage_root / name).mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(storage_root / 'db' / 'test.sqlite3').as_posix()}")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("MAX_CHARS", "50")
    monkeypatch.setenv("KOKORO_VOICES", "af_heart,af_bella")
    monkeypatch.setenv("APP_ACCESS_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("AUTH_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:8080,http://127.0.0.1:5173")

    for module_name in list(sys.modules):
        if module_name.startswith("tts_shared") or module_name.startswith("app"):
            sys.modules.pop(module_name)

    module = importlib.import_module("app.main")
    monkeypatch.setattr(module, "enqueue_job", lambda job_id: None)
    monkeypatch.setattr(module, "read_capabilities", lambda: None)
    return module.app


def login_client(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"access_token": AUTH_TOKEN})
    assert response.status_code == 204


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {AUTH_TOKEN}"}


def test_public_health_and_session_status(tmp_path: Path, monkeypatch) -> None:
    app = load_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/auth/session").json() == {"authenticated": False}


def test_rejects_unauthenticated_requests(tmp_path: Path, monkeypatch) -> None:
    app = load_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
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
        assert create_response.status_code == 401
        assert client.get("/api/v1/jobs").status_code == 401
        assert client.get("/api/v1/capabilities").status_code == 401


def test_create_text_job(tmp_path: Path, monkeypatch) -> None:
    app = load_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        login_client(client)
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
        login_client(client)
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


def test_bearer_token_auth_works_without_session(tmp_path: Path, monkeypatch) -> None:
    app = load_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/jobs",
            headers=auth_headers(),
            data={
                "title": "Bearer flow",
                "source_type": "text",
                "text": "Short text for synthesis.",
                "voice_id": "af_heart",
                "speaking_rate": "1.0",
                "output_format": "mp3",
            },
        )

        assert response.status_code == 202
        listing = client.get("/api/v1/jobs", headers=auth_headers())
        assert listing.status_code == 200
        assert listing.json()["total"] == 1


def test_invalid_login_is_rejected(tmp_path: Path, monkeypatch) -> None:
    app = load_app(tmp_path, monkeypatch)

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/login", json={"access_token": "wrong-token"})
        assert response.status_code == 401
        assert client.get("/api/v1/auth/session").json() == {"authenticated": False}


def test_cors_uses_allowlist(tmp_path: Path, monkeypatch) -> None:
    app = load_app(tmp_path, monkeypatch)

    with TestClient(app, base_url="http://localhost:8080") as client:
        allowed = client.options(
            "/api/v1/jobs",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:8080"

        blocked = client.options(
            "/api/v1/jobs",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert blocked.status_code == 400
