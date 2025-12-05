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

    def _is_enabled(self) -> bool:
        """
        Decide whether rate limiting should be enforced for this process.

        In local/test environments we generally rely on upstream rate limiting
        (or none at all) and we never want Redis connectivity issues to break
        requests or tests.
        """
        env = self.settings.environment.lower()
        if env in {"local", "test"}:
            return False
        return self.settings.api_rate_limit_per_minute > 0

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if not self._is_enabled():
            # Lightweight debug hook – useful in CI and local dev to confirm
            # that rate limiting is intentionally disabled.
            self.logger.debug(
                "Rate limiting disabled",
                environment=self.settings.environment,
                limit=self.settings.api_rate_limit_per_minute,
            )
            return await call_next(request)

        limit_per_min = self.settings.api_rate_limit_per_minute

        client_ip = request.client.host if request.client else "unknown"
        api_key = request.headers.get("X-API-Key", "")

        key = self._build_key(client_ip, api_key)
        try:
            redis = get_redis_client()
        except Exception as exc:  # pragma: no cover - defensive
            # If Redis cannot even be constructed, we log and fail open; in
            # production this should be caught by infra alerts.
            self.logger.error(
                "Rate limit backend initialisation failed; continuing without enforcement",
                error=str(exc),
                redis_url=self.settings.redis_url,
            )
            return await call_next(request)

        now = utc_now()
        minute_bucket = int(now.timestamp() // 60)

        redis_key = f"rl:{minute_bucket}:{key}"
        try:
            current = await redis.incr(redis_key)
        except Exception as exc:
            # Redis is unavailable or timing out – we log and continue without
            # enforcing limits instead of breaking user requests.
            self.logger.error(
                "Rate limit backend error; continuing without enforcement",
                error=str(exc),
                redis_key=redis_key,
                redis_url=self.settings.redis_url,
            )
            return await call_next(request)

        if current == 1:
            # First request in this bucket: set TTL to remainder of minute.
            # TTL failures should not break the request.
            try:
                expires_in = 60 - (now.timestamp() % 60)
                await redis.expire(redis_key, math.ceil(expires_in))
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.warning(
                    "Rate limit TTL set failed",
                    error=str(exc),
                    redis_key=redis_key,
                )

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
