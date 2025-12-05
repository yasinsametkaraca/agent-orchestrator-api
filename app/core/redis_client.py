from typing import Optional

from redis.asyncio import Redis as AsyncRedis
from redis.asyncio import from_url as redis_from_url

from .config import get_settings
from .logging import get_logger

_redis_client: Optional[AsyncRedis] = None
_logger = get_logger("RedisClient")


def get_redis_client() -> AsyncRedis:
    """
    Lazily construct and cache a single async Redis client for the process.

    We log the (sanitised) configuration once to make it easier to debug
    connectivity or cluster-related issues in production.
    """
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        try:
            _logger.info("RedisClient.initialising", redis_url=settings.redis_url)
            _redis_client = redis_from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            _logger.info("RedisClient.initialised")
        except Exception as exc:  # pragma: no cover - defensive logging
            _logger.error(
                "RedisClient.initialise_failed",
                error=str(exc),
                redis_url=settings.redis_url,
            )
            raise
    return _redis_client
