from __future__ import annotations

import math
from typing import Callable, Awaitable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import get_settings
from .errors import RateLimitExceededError
from .logging import get_logger
from .redis_client import get_redis_client
from .utils import utc_now


class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        super().__init__(app)
        self.settings = get_settings()
        self.logger = get_logger("rate-limit")

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        limit_per_min = self.settings.api_rate_limit_per_minute
        if limit_per_min <= 0:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        api_key = request.headers.get("X-API-Key", "")

        key = self._build_key(client_ip, api_key)
        redis = get_redis_client()

        now = utc_now()
        minute_bucket = int(now.timestamp() // 60)

        redis_key = f"rl:{minute_bucket}:{key}"
        current = await redis.incr(redis_key)
        if current == 1:
            # first request: set TTL to remainder of minute
            expires_in = 60 - (now.timestamp() % 60)
            await redis.expire(redis_key, math.ceil(expires_in))

        if current > limit_per_min:
            self.logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                api_key=api_key or None,
                limit=limit_per_min,
            )
            raise RateLimitExceededError()

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit_per_min)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit_per_min - current))
        return response

    @staticmethod
    def _build_key(client_ip: str, api_key: str) -> str:
        if api_key:
            return f"key:{api_key}"
        return f"ip:{client_ip}"
