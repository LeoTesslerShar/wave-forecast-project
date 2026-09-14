"""Redis cache for served forecast responses (PROMPT.md section 3). A Redis outage
degrades to uncached serving, per hard rule 7 -- it must never turn into a 500."""
import json
import logging

import redis.asyncio as redis

from app.logging_utils import log_event
from app.settings import get_settings

logger = logging.getLogger("cache")

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def cache_get(key: str) -> dict | list | None:
    try:
        raw = await get_client().get(key)
    except Exception as exc:  # noqa: BLE001 -- cache must never break serving
        log_event(logger, logging.WARNING, "cache get failed, degrading to uncached", error=str(exc))
        return None
    return json.loads(raw) if raw else None


async def cache_set(key: str, value: dict | list, ttl_seconds: int = 900) -> None:
    try:
        await get_client().set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, logging.WARNING, "cache set failed, continuing uncached", error=str(exc))


async def ping() -> bool:
    try:
        return bool(await get_client().ping())
    except Exception:  # noqa: BLE001
        return False
