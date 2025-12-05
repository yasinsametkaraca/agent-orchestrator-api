from __future__ import annotations

import logging
import sys
from typing import Any, Dict

import structlog

from .config import get_settings


def _get_structlog_processors() -> list:
    return [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]


def configure_logging() -> None:
    settings = get_settings()

    logging_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging_level,
    )

    structlog.configure(
        processors=_get_structlog_processors(),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if name is None:
        name = get_settings().app_name
    return structlog.get_logger(name)


def bind_request_context(
    logger: structlog.stdlib.BoundLogger,
    *,
    request_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    agent_name: str | None = None,
    endpoint: str | None = None,
) -> structlog.stdlib.BoundLogger:
    context: Dict[str, Any] = {}
    if request_id:
        context["request_id"] = request_id
    if task_id:
        context["task_id"] = task_id
    if session_id:
        context["session_id"] = session_id
    if agent_name:
        context["agent_name"] = agent_name
    if endpoint:
        context["endpoint"] = endpoint
    return logger.bind(**context)
