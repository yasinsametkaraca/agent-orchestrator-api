from __future__ import annotations

from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.db.mongo import get_database
from app.models.domain.agent_run import AgentRun


class AgentRunsRepository:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db: AsyncIOMotorDatabase = db or get_database()
        self._collection: AsyncIOMotorCollection = self._db["agent_runs"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("task_id")
        await self._collection.create_index("agent_name")

    async def create(self, run: AgentRun) -> None:
        await self._collection.insert_one(run.model_dump())

    async def get_by_task_id(self, task_id: str) -> List[AgentRun]:
        cursor = self._collection.find({"task_id": task_id}).sort("started_at", 1)
        return [AgentRun(**doc) async for doc in cursor]
