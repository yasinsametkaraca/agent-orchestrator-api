from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.core.redis_client import get_redis_client
from app.db.mongo import get_client

router = APIRouter(tags=["health"])


@router.get("/health", response_class=PlainTextResponse)
async def health_check() -> str:
    settings = get_settings()
    # Simple dependency checks; we swallow exceptions to avoid long timeouts.
    try:
        client = get_client()
        await client.admin.command("ping")
        mongo_status = "up"
    except Exception:
        mongo_status = "down"

    try:
        redis = get_redis_client()
        await redis.ping()
        redis_status = "up"
    except Exception:
        redis_status = "down"

    return f"ok | mongo={mongo_status} | redis={redis_status} | env={settings.environment}"
