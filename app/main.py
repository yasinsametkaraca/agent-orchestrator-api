from __future__ import annotations

import uuid
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware import Middleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.v1 import routes_agent, routes_health, routes_metrics, routes_tasks
from app.core.config import get_settings
from app.core.debug import log_settings_debug
from app.core.errors import setup_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import RateLimiterMiddleware
from app.core.security import configure_cors


REQUEST_COUNT = Counter(
    "api_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "api_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id  # type: ignore[attr-defined]
        logger = get_logger("RequestContext")
        logger.info("request.start", request_id=request_id, path=str(request.url.path), method=request.method)
        with REQUEST_LATENCY.labels(request.method, str(request.url.path)).time():
            response = await call_next(request)
        REQUEST_COUNT.labels(request.method, str(request.url.path), str(response.status_code)).inc()
        response.headers["X-Request-Id"] = request_id
        return response


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    log_settings_debug(settings)

    middleware = [
        Middleware(RequestContextMiddleware),
        Middleware(RateLimiterMiddleware),
    ]

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        middleware=middleware,
    )

    configure_cors(app)
    setup_exception_handlers(app)

    app.include_router(routes_agent.router)
    app.include_router(routes_tasks.router)
    app.include_router(routes_metrics.router)
    app.include_router(routes_health.router)

    @app.get("/metrics")
    async def metrics() -> Response:
        data = generate_latest()
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
