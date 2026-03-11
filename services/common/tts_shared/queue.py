from __future__ import annotations

import json
import time

from redis import Redis

from .config import get_settings


settings = get_settings()


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def _pending_queue_name() -> str:
    return settings.queue_name


def _processing_queue_name() -> str:
    return f"{settings.queue_name}:processing"


def _worker_heartbeat_key() -> str:
    return f"{settings.queue_name}:worker:heartbeat"


def _capabilities_key() -> str:
    return "tts:capabilities"


def enqueue_job(job_id: str) -> None:
    redis = get_redis()
    redis.lrem(_pending_queue_name(), 0, job_id)
    redis.lrem(_processing_queue_name(), 0, job_id)
    redis.lpush(_pending_queue_name(), job_id)


def reserve_job(timeout_seconds: int = 5) -> str | None:
    return get_redis().brpoplpush(_pending_queue_name(), _processing_queue_name(), timeout=timeout_seconds)


def ack_job(job_id: str) -> None:
    get_redis().lrem(_processing_queue_name(), 0, job_id)


def requeue_job(job_id: str) -> None:
    redis = get_redis()
    redis.lrem(_processing_queue_name(), 0, job_id)
    redis.lrem(_pending_queue_name(), 0, job_id)
    redis.lpush(_pending_queue_name(), job_id)


def remove_pending_job(job_id: str) -> None:
    get_redis().lrem(_pending_queue_name(), 0, job_id)


def clear_job(job_id: str) -> None:
    redis = get_redis()
    redis.lrem(_pending_queue_name(), 0, job_id)
    redis.lrem(_processing_queue_name(), 0, job_id)


def list_pending_jobs() -> list[str]:
    return get_redis().lrange(_pending_queue_name(), 0, -1)


def list_processing_jobs() -> list[str]:
    return get_redis().lrange(_processing_queue_name(), 0, -1)


def queue_depth() -> dict[str, int]:
    redis = get_redis()
    return {
        "pending": int(redis.llen(_pending_queue_name())),
        "processing": int(redis.llen(_processing_queue_name())),
    }


def record_worker_heartbeat(now: float | None = None) -> None:
    get_redis().set(_worker_heartbeat_key(), str(now if now is not None else time.time()))


def read_worker_heartbeat() -> float | None:
    raw = get_redis().get(_worker_heartbeat_key())
    return float(raw) if raw else None


def publish_capabilities(payload: dict) -> None:
    get_redis().set(_capabilities_key(), json.dumps(payload))


def read_capabilities() -> dict | None:
    raw = get_redis().get(_capabilities_key())
    return json.loads(raw) if raw else None
