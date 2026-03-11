# NAC-TTS

Self-hosted local GPU text-to-speech with a mobile-friendly web frontend.

Production deployment and go-live steps live in [`docs/runbook.md`](docs/runbook.md).

## Stack

- FastAPI API with SQLite metadata
- Redis-backed worker
- Kokoro TTS on NVIDIA GPU
- React + Vite frontend
- Caddy for static hosting and API reverse proxy
- Cloudflare Tunnel for remote access

## Repo Layout

- `apps/web`: React/Vite frontend
- `services/api`: FastAPI app
- `services/worker`: Redis worker and Kokoro pipeline
- `services/common`: shared backend modules
- `ops/docker`: Compose and edge config

## Quick Start

1. Copy `.env.example` to `.env` and set values.
2. Set `APP_ACCESS_TOKEN` and `AUTH_SESSION_SECRET` to real random secrets before exposing the app beyond your machine.
3. Create Cloudflare Tunnel credentials if you want remote access.
4. Build and start:

```powershell
docker compose -f ops/docker/docker-compose.yml up --build
```

5. Open `http://localhost:8080` and sign in with `APP_ACCESS_TOKEN`.

## Notes

- The worker image installs `espeak-ng` and `ffmpeg`.
- GPU acceleration requires Docker Desktop GPU support and a working NVIDIA driver.
- Scanned PDFs are rejected in v1 because OCR is out of scope.
- The full production deployment and go-live procedure is documented in [`docs/runbook.md`](docs/runbook.md).
- Remote-access setup and auth details are documented in [`docs/authentication.md`](docs/authentication.md).
- Migration and backup/restore guidance is documented in [`docs/persistence.md`](docs/persistence.md).
- Health, logging, and retention guidance is documented in [`docs/operations.md`](docs/operations.md).
