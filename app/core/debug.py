# app/core/debug.py

from __future__ import annotations

from typing import Any, Dict

from app.core.config import Settings
from app.core.logging import get_logger


def _mask_secret(value: str | None) -> str:
    if not value:
        return "<empty>"
    # Expose only a small portion to confirm wiring without leaking full secrets.
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:3]}***{value[-3:]}"


def build_settings_debug_snapshot(settings: Settings) -> Dict[str, Any]:
    """
    Build a safe, non-sensitive snapshot of key runtime settings.

    This is useful for debugging configuration issues in containers and CI
    without exposing actual secrets in logs.
    """
    return {
        "environment": settings.environment,
        "app_name": settings.app_name,
        "log_level": settings.log_level,
        "mongo_db_name": settings.mongo_db_name,
        "redis_url_present": bool(settings.redis_url),
        "redis_global_keyprefix": settings.redis_global_keyprefix,
        "openai_api_key_masked": _mask_secret(settings.openai_api_key),
        "tavily_api_key_masked": _mask_secret(settings.tavily_api_key),
        "api_keys_count": len(settings.api_keys),
        "cors_origins": settings.cors_origins,
        "prometheus_enabled": settings.prometheus_enabled,
        "celery_broker": settings.celery_broker,
        "celery_backend": settings.celery_backend,
    }


def log_settings_debug(settings: Settings) -> None:
    """
    Emit a single structured debug log entry with the sanitized settings snapshot.
    """
    logger = get_logger("SettingsDebug")
    snapshot = build_settings_debug_snapshot(settings)
    logger.debug("Runtime settings snapshot", **snapshot)
