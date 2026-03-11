# Operational Health, Logging, and Retention

## Health signals

- `GET /api/v1/health`: Public liveness probe for the API process.
- `GET /api/v1/ready`: Readiness view for API, Redis, worker heartbeat, and queue depth.

`/api/v1/ready` returns:

- `api`: API readiness result
- `redis`: Redis connectivity result
- `worker.status`: `ok` or `stale`
- `worker.last_heartbeat`: Unix timestamp from the worker loop
- `queue.pending`: Count of queued jobs
- `queue.processing`: Count of reserved jobs being processed

## Logging

- API and worker logs are emitted as JSON to stdout.
- Important fields include `event`, `service`, `job_id`, `status_code`, `duration_ms`, and retention results where applicable.
- Core worker lifecycle events now include reservation and completion outcome logging.

## Retention policy

- `TMP_RETENTION_HOURS`: Removes stale working files under `storage/tmp` after the configured age.
- `AUDIO_RETENTION_DAYS`: Removes generated MP3 files for old completed jobs and clears their `audio_path` in the database.
- `RETENTION_SWEEP_INTERVAL_SECONDS`: How often the worker performs background retention sweeps.

The API also performs one retention sweep at startup so stale files do not accumulate if the worker has been idle.

## Compose healthchecks

The Docker Compose stack now includes healthchecks for:

- `redis`: `redis-cli ping`
- `api`: HTTP readiness probe against `http://127.0.0.1:8000/api/v1/ready`
- `worker`: Redis heartbeat freshness check

## Recommended operator checks

1. Confirm `docker compose ps` reports `healthy` for `redis`, `api`, and `worker`.
2. Call `/api/v1/ready` and verify worker heartbeat and queue counts look reasonable.
3. Watch stdout logs for JSON events instead of plain text.
4. Set retention values deliberately before launch rather than leaving them implicit.
