from __future__ import annotations

from typing import Optional

from redis.asyncio import Redis as AsyncRedis
from redis.asyncio import from_url as redis_from_url

from .config import get_settings

_redis_client: Optional[AsyncRedis] = None


def get_redis_client() -> AsyncRedis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis_from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client
