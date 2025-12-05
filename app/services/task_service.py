from __future__ import annotations

import json
from typing import List, Optional, Tuple

from app.core.logging import get_logger
from app.core.redis_client import get_redis_client
from app.core.utils import generate_uuid, utc_now
from app.db.repositories.agent_runs_repo import AgentRunsRepository
from app.db.repositories.messages_repo import MessagesRepository
from app.db.repositories.tasks_repo import TaskRepository
from app.models.domain.agent_run import AgentRun
from app.models.domain.message import Message
from app.models.domain.task import (
    Citation,
    Task,
    TaskCost,
    TaskCreate,
    TaskErrorInfo,
    TaskMetadata,
    TaskResult,
    TaskStatus,
    TaskUpdate,
)


class TaskService:
    def __init__(self) -> None:
        self.tasks_repo = TaskRepository()
        self.agent_runs_repo = AgentRunsRepository()
        self.messages_repo = MessagesRepository()
        self.logger = get_logger("TaskService")

    async def create_task(
        self,
        *,
        task_text: str,
        session_id: str,
        metadata: TaskMetadata,
    ) -> Task:
        task_id = generate_uuid()
        task_create = TaskCreate(
            input_text=task_text,
            session_id=session_id,
            metadata=metadata,
        )
        task = await self.tasks_repo.create(task_id, task_create)

        # Persist user message for session context
        message = Message(
            session_id=session_id,
            task_id=task_id,
            role="user",
            agent_name=None,
            content=task_text,
            created_at=utc_now(),
        )
        await self.messages_repo.create(message)

        self.logger.info("TaskService.create_task", task_id=task_id, session_id=session_id)
        await self._publish_event(
            task_id,
            {
                "event": "status_changed",
                "status": TaskStatus.QUEUED.value,
                "timestamp": task.queued_at.isoformat(),
            },
        )
        return task

    async def get_task(self, task_id: str) -> Optional[Task]:
        return await self.tasks_repo.get_by_task_id(task_id)

    async def list_tasks(
        self,
        *,
        status: Optional[TaskStatus],
        agent_type: Optional[str],
        page: int,
        page_size: int,
    ) -> Tuple[List[Task], int]:
        return await self.tasks_repo.list(
            status=status,
            agent_type=agent_type,
            page=page,
            page_size=page_size,
        )

    async def mark_processing(self, task_id: str) -> Optional[Task]:
        update = TaskUpdate(
            status=TaskStatus.PROCESSING,
            started_at=utc_now(),
        )
        task = await self.tasks_repo.update(task_id, update)
        if task:
            await self._publish_event(
                task_id,
                {
                    "event": "status_changed",
                    "status": TaskStatus.PROCESSING.value,
                    "timestamp": task.started_at.isoformat() if task.started_at else utc_now().isoformat(),
                },
            )
        return task

    async def mark_completed(
        self,
        task: Task,
        *,
        selected_agent: str,
        agent_type: str,
        peer_reason: str,
        content: str,
        code_language: Optional[str],
        citations: List[Citation],
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
    ) -> Task:
        now = utc_now()
        cost = TaskCost(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            usd_estimate=None,
        )

        result = TaskResult(
            summary=None,
            raw_output=content,
            code_language=code_language,
            citations=citations,
        )

        update = TaskUpdate(
            status=TaskStatus.COMPLETED,
            selected_agent=selected_agent,
            agent_type=agent_type,
            peer_routing_reason=peer_reason,
            completed_at=now,
            result=result,
            cost=cost,
        )
        updated = await self.tasks_repo.update(task.task_id, update)
        if not updated:
            raise RuntimeError(f"Task {task.task_id} not found during mark_completed.")

        self.logger.info(
            "TaskService.mark_completed",
            task_id=task.task_id,
            selected_agent=selected_agent,
            agent_type=agent_type,
        )

        await self._publish_event(
            task.task_id,
            {
                "event": "status_changed",
                "status": TaskStatus.COMPLETED.value,
                "timestamp": now.isoformat(),
            },
        )

        # Assistant message stored in conversation history
        message = Message(
            session_id=task.session_id,
            task_id=task.task_id,
            role="assistant",
            agent_name=selected_agent,
            content=content,
            created_at=utc_now(),
        )
        await self.messages_repo.create(message)

        return updated

    async def mark_failed(
        self,
        task: Task,
        error_type: str,
        message: str,
        stack: Optional[str] = None,
    ) -> Task:
        info = TaskErrorInfo(type=error_type, message=message, stack=stack)
        update = TaskUpdate(
            status=TaskStatus.FAILED,
            error=info,
            completed_at=utc_now(),
        )
        updated = await self.tasks_repo.update(task.task_id, update)
        if not updated:
            raise RuntimeError(f"Task {task.task_id} not found during mark_failed.")

        self.logger.warning(
            "TaskService.mark_failed",
            task_id=task.task_id,
            error_type=error_type,
            message=message,
        )

        await self._publish_event(
            task.task_id,
            {
                "event": "status_changed",
                "status": TaskStatus.FAILED.value,
                "timestamp": utc_now().isoformat(),
                "error_type": error_type,
                "error_message": message,
            },
        )
        return updated

    async def get_agent_runs(self, task_id: str) -> List[AgentRun]:
        return await self.agent_runs_repo.get_by_task_id(task_id)

    async def _publish_event(self, task_id: str, payload: dict) -> None:
        """
        Publish task events on Redis pub/sub for SSE consumers.
        """
        try:
            channel = f"task_events:{task_id}"
            redis = get_redis_client()
            await redis.publish(channel, json.dumps(payload))
        except Exception as exc:
            self.logger.warning("TaskService.publish_event_failed", error=str(exc), task_id=task_id)
