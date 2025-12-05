from __future__ import annotations

from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.db.mongo import get_database
from app.core.utils import utc_now


class LogsRepository:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db: AsyncIOMotorDatabase = db or get_database()
        self._collection: AsyncIOMotorCollection = self._db["logs"]

    async def create(
        self,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        doc = {
            "timestamp": utc_now(),
            "level": level,
            "message": message,
            "context": context or {},
        }
        await self._collection.insert_one(doc)
