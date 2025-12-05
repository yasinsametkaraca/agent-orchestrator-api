from __future__ import annotations

import asyncio
from typing import Any, Awaitable

from app.core.logging import get_logger


_logger = get_logger("AsyncRunner")

_loop: asyncio.AbstractEventLoop | None = None


def get_worker_event_loop() -> asyncio.AbstractEventLoop:
    """
    Lazily create and cache a single asyncio event loop for the Celery worker
    process.

    We intentionally DO NOT close this loop for the lifetime of the process.
    Closing/recreating loops in a long-lived worker causes issues with
    libraries such as Motor and aioredis which bind to the first loop they see
    and later try to schedule work on it.
    """
    global _loop

    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _logger.info("AsyncRunner.loop.initialised")

    return _loop


def run_worker_coroutine(coro: Awaitable[Any]) -> Any:
    """
    Run the given coroutine on the shared worker event loop and block until
    it finishes.

    This function is safe to call from the synchronous Celery task body and
    keeps all async orchestration in one place.
    """
    loop = get_worker_event_loop()
    _logger.debug("AsyncRunner.run.start", coroutine=str(coro))

    try:
        result = loop.run_until_complete(coro)
    except Exception as exc:  # pragma: no cover - defensive logging
        _logger.error("AsyncRunner.run.error", exc_info=exc)
        raise
    else:
        _logger.debug("AsyncRunner.run.completed")
        return result
