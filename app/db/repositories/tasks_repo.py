from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.db.mongo import get_database
from app.models.domain.task import Task, TaskCreate, TaskStatus, TaskUpdate
from app.core.utils import utc_now


class TaskRepository:
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None) -> None:
        self._db: AsyncIOMotorDatabase = db or get_database()
        self._collection: AsyncIOMotorCollection = self._db["tasks"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("task_id", unique=True)
        await self._collection.create_index("status")
        await self._collection.create_index("agent_type")
        await self._collection.create_index("created_at")
        await self._collection.create_index("session_id")

    async def create(self, task_id: str, task: TaskCreate) -> Task:
        now = utc_now()
        doc: Dict[str, Any] = {
            "task_id": task_id,
            "session_id": task.session_id,
            "input_text": task.input_text,
            "status": TaskStatus.QUEUED.value,
            "selected_agent": None,
            "agent_type": None,
            "peer_routing_reason": None,
            "created_at": now,
            "updated_at": now,
            "queued_at": now,
            "started_at": None,
            "completed_at": None,
            "error": None,
            "result": None,
            "metadata": task.metadata.model_dump() if task.metadata else None,
            "cost": None,
        }
        await self._collection.insert_one(doc)
        return Task(**doc)

    async def get_by_task_id(self, task_id: str) -> Optional[Task]:
        doc = await self._collection.find_one({"task_id": task_id})
        return Task(**doc) if doc else None

    async def update(self, task_id: str, update: TaskUpdate) -> Optional[Task]:
        update_doc: Dict[str, Any] = {}
        for field, value in update.model_dump(exclude_unset=True).items():
            update_doc[field] = value
        if not update_doc:
            return await self.get_by_task_id(task_id)

        update_doc["updated_at"] = utc_now()
        await self._collection.update_one({"task_id": task_id}, {"$set": update_doc})
        return await self.get_by_task_id(task_id)

    async def list(
        self,
        *,
        status: Optional[TaskStatus] = None,
        agent_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Task], int]:
        query: Dict[str, Any] = {}
        if status:
            query["status"] = status.value
        if agent_type:
            query["agent_type"] = agent_type

        skip = (page - 1) * page_size
        cursor = self._collection.find(query).sort("created_at", -1).skip(skip).limit(page_size)
        docs = [Task(**doc) async for doc in cursor]
        total = await self._collection.count_documents(query)
        return docs, total

    async def count_by_statuses(self, statuses: List[TaskStatus]) -> int:
        return await self._collection.count_documents(
            {"status": {"$in": [s.value for s in statuses]}}
        )

    async def find_completed_today(self, today_start: datetime, today_end: datetime) -> List[Task]:
        cursor = self._collection.find(
            {
                "completed_at": {"$gte": today_start, "$lt": today_end},
                "status": TaskStatus.COMPLETED.value,
            }
        )
        return [Task(**doc) async for doc in cursor]

    async def aggregate_today_by_agent(
        self, today_start: datetime, today_end: datetime
    ) -> Dict[str, int]:
        pipeline = [
            {
                "$match": {
                    "created_at": {"$gte": today_start, "$lt": today_end},
                    "agent_type": {"$ne": None},
                }
            },
            {"$group": {"_id": "$selected_agent", "count": {"$sum": 1}}},
        ]
        result: Dict[str, int] = {}
        async for row in self._collection.aggregate(pipeline):
            agent_name = row["_id"] or "unknown"
            result[agent_name] = row["count"]
        return result
