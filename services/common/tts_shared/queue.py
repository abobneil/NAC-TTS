from __future__ import annotations

import json

from redis import Redis

from .config import get_settings


settings = get_settings()


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def enqueue_job(job_id: str) -> None:
    get_redis().lpush(settings.queue_name, job_id)


def pop_job(timeout_seconds: int = 5) -> str | None:
    item = get_redis().brpop(settings.queue_name, timeout=timeout_seconds)
    if item is None:
        return None
    _, job_id = item
    return job_id


def publish_capabilities(payload: dict) -> None:
    get_redis().set("tts:capabilities", json.dumps(payload))


def read_capabilities() -> dict | None:
    raw = get_redis().get("tts:capabilities")
    return json.loads(raw) if raw else None
