from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.db.mongo import get_database
from app.models.domain.session import Session


class SessionsRepository:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db: AsyncIOMotorDatabase = db or get_database()
        self._collection: AsyncIOMotorCollection = self._db["sessions"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("session_id", unique=True)

    async def get_by_session_id(self, session_id: str) -> Optional[Session]:
        doc = await self._collection.find_one({"session_id": session_id})
        return Session(**doc) if doc else None

    async def create(self, session: Session) -> Session:
        await self._collection.insert_one(session.model_dump())
        return session

    async def update(self, session_id: str, session: Session) -> Session:
        await self._collection.update_one(
            {"session_id": session_id},
            {"$set": session.model_dump()},
        )
        return session
