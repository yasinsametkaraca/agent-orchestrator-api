from __future__ import annotations

from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.db.mongo import get_database
from app.models.domain.message import Message


class MessagesRepository:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db: AsyncIOMotorDatabase = db or get_database()
        self._collection: AsyncIOMotorCollection = self._db["messages"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("session_id")
        await self._collection.create_index("task_id")

    async def create(self, message: Message) -> None:
        await self._collection.insert_one(message.model_dump())

    async def list_by_session(self, session_id: str) -> List[Message]:
        cursor = self._collection.find({"session_id": session_id}).sort("created_at", 1)
        return [Message(**doc) async for doc in cursor]
