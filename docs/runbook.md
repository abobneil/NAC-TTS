# Production Deployment and Go-Live Runbook

## Supported topology

- `caddy` serves the web app and reverse-proxies `/api/*` to the FastAPI service.
- `api` owns the authenticated HTTP surface, runs migrations on startup, and exposes health endpoints.
- `worker` consumes Redis queue work, publishes heartbeats, and performs retention sweeps.
- `redis` backs queue state and operational heartbeat data.
- `cloudflared` is optional and should only expose `caddy`.

This runbook assumes a single-host deployment using `ops/docker/docker-compose.yml`.

## Required environment variables

Set these in `.env` before opening access:

- `APP_ACCESS_TOKEN`: Shared app/API access token. Use a long random value.
- `AUTH_SESSION_SECRET`: Separate random secret for signed browser sessions.
- `AUTH_COOKIE_SECURE=true` when the public hostname uses HTTPS.
- `CORS_ALLOW_ORIGINS`: Exact browser origin list, for example `https://tts.example.com`.
- `DATABASE_URL`: Leave pointed at `sqlite:////data/db/nac_tts.sqlite3` for the supported topology unless you are deliberately migrating the storage layout.
- `REDIS_URL`: Leave pointed at the internal Redis service unless you are using an external Redis instance.
- `KOKORO_DEVICE`: `cuda` for the intended launch topology.
- `CF_TUNNEL_HOSTNAME`, `CF_TUNNEL_ID`, `CF_TUNNEL_CREDENTIALS`: Required only when using Cloudflare Tunnel.

Operational defaults to review intentionally:

- `MAX_ACTIVE_JOBS`
- `MAX_JOB_RETRIES`
- `WORKER_HEARTBEAT_TTL_SECONDS`
- `TMP_RETENTION_HOURS`
- `AUDIO_RETENTION_DAYS`
- `RETENTION_SWEEP_INTERVAL_SECONDS`

## Preflight checklist

1. Confirm Docker Desktop GPU support works on the host and NVIDIA drivers are healthy.
2. Generate real values for `APP_ACCESS_TOKEN` and `AUTH_SESSION_SECRET`.
3. Confirm `storage/` is on persistent storage with enough room for SQLite, uploads, and generated MP3s.
4. If using Cloudflare Tunnel, create a Cloudflare Access policy before exposing the hostname.
5. Take or prepare a storage backup location outside `storage/`.

## Deployment steps

1. Copy `.env.example` to `.env` and replace placeholder secrets.
2. If this is not a localhost-only deployment:
   - set `AUTH_COOKIE_SECURE=true`
   - set `CORS_ALLOW_ORIGINS` to the exact public origin
3. Build and start the stack:
   `docker compose -f ops/docker/docker-compose.yml up --build -d`
4. Wait for services to become healthy:
   `docker compose -f ops/docker/docker-compose.yml ps`
5. If healthchecks fail, inspect logs:
   `docker compose -f ops/docker/docker-compose.yml logs api worker redis --tail=200`

## Post-deploy validation

1. Confirm `http://localhost:8080` or the public hostname loads the login screen.
2. Confirm `GET /api/v1/health` returns `200`.
3. Confirm `GET /api/v1/ready` returns `200` and shows:
   - `redis: ok`
   - `worker.status: ok`
   - sensible `queue.pending` / `queue.processing` counts
4. Sign in through the web UI with `APP_ACCESS_TOKEN`.
5. Create a text job and confirm it reaches `completed`.
6. Play the audio in-browser and confirm MP3 download works.
7. Confirm unauthenticated `GET /api/v1/jobs` returns `401`.
8. Confirm JSON logs are present in `docker compose logs`.
9. Run a storage backup:
   `python ops/scripts/storage_snapshot.py backup --storage-root storage --output-root backups`

## Known v1 limits

- Scanned PDFs that require OCR are unsupported.
- The supported launch topology is single-node and SQLite-backed.
- Auth is shared-token based; there is no multi-user account model.
- Remote exposure is expected to sit behind Cloudflare Access if Cloudflare Tunnel is used.

## Backup and recovery

- Backup:
  `python ops/scripts/storage_snapshot.py backup --storage-root storage --output-root backups`
- Restore:
  `docker compose -f ops/docker/docker-compose.yml down`
  `python ops/scripts/storage_snapshot.py restore --backup-root backups/backup-YYYYMMDDTHHMMSSZ --storage-root storage`
  `docker compose -f ops/docker/docker-compose.yml up --build -d`

After restore, rerun the post-deploy validation steps.

## Rollback

1. Stop the stack:
   `docker compose -f ops/docker/docker-compose.yml down`
2. Check out the last known good commit or release tag.
3. Restore the matching storage backup if the schema or generated files changed.
4. Rebuild and start:
   `docker compose -f ops/docker/docker-compose.yml up --build -d`
5. Recheck `/api/v1/health`, `/api/v1/ready`, login, create-job flow, and download flow.

## Final go-live checklist

1. Secrets are non-placeholder and stored only in `.env`.
2. `AUTH_COOKIE_SECURE=true` is set for HTTPS deployments.
3. Cloudflare Access is protecting the public tunnel hostname if remote access is enabled.
4. A fresh backup has been created and restore instructions are ready.
5. `docker compose ps` shows healthy `redis`, `api`, and `worker` services.
6. `/api/v1/ready` reports healthy Redis and worker heartbeat.
7. Manual text-job smoke test passed.
8. Manual MP3 download smoke test passed.
9. Logs are flowing and readable as JSON.
10. Retention values are set intentionally for launch.
