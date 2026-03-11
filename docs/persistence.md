# Database Migrations and Storage Recovery

## Schema management

NAC-TTS now applies database schema changes through Alembic migrations instead of `create_all()`.

### Standard commands

- Upgrade to the latest schema:
  `python -m tts_shared.db_migrations upgrade head`
- The API and worker both run the same upgrade step during startup through `init_db()`.

### Current baseline

- Initial revision: `20260311_0001`
- Migration files live under `services/common/tts_shared/migrations/`

## Storage expectations

- `STORAGE_ROOT` must be an absolute path.
- The SQLite database must live under `STORAGE_ROOT/db`.
- Generated audio lives under `STORAGE_ROOT/audio`.
- Uploaded source PDFs live under `STORAGE_ROOT/uploads`.
- `STORAGE_ROOT/tmp` is disposable working space and is not part of backup scope.

## Backup procedure

1. Pick an output directory outside `storage/`, for example `backups/`.
2. Run:
   `python ops/scripts/storage_snapshot.py backup --storage-root storage --output-root backups`
3. Keep the generated backup directory together. It contains:
   - `db/nac_tts.sqlite3`
   - `audio/`
   - `uploads/`
   - `manifest.json`

The backup uses SQLite's online backup API, so it creates a consistent database snapshot without copying WAL files directly.

## Restore procedure

1. Stop the stack before restoring:
   `docker compose -f ops/docker/docker-compose.yml down`
2. Restore from a backup directory:
   `python ops/scripts/storage_snapshot.py restore --backup-root backups/backup-YYYYMMDDTHHMMSSZ --storage-root storage`
3. Start the stack again:
   `docker compose -f ops/docker/docker-compose.yml up --build`
4. Validate:
   - `GET /api/v1/health` returns `200`
   - Recent jobs appear in the library
   - Expected MP3 files exist and download correctly

## Upgrade guidance

- Take a storage backup before applying new migrations in production.
- Run the upgrade on a copy of production data before the real rollout if the schema changes again.
- Do not point `DATABASE_URL` at a SQLite file outside `STORAGE_ROOT/db`; startup validation now rejects that configuration.
