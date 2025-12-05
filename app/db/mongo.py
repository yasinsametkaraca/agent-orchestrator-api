from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

_mongo_client: Optional[AsyncIOMotorClient] = None
_mongo_db: Optional[AsyncIOMotorDatabase] = None


def get_client() -> AsyncIOMotorClient:
    global _mongo_client
    if _mongo_client is None:
        settings = get_settings()
        _mongo_client = AsyncIOMotorClient(settings.mongo_uri)
    return _mongo_client


def get_database() -> AsyncIOMotorDatabase:
    global _mongo_db
    if _mongo_db is None:
        client = get_client()
        settings = get_settings()
        _mongo_db = client[settings.mongo_db_name]
    return _mongo_db
