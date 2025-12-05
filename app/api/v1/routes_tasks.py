from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from starlette.responses import StreamingResponse

from app.core.logging import bind_request_context, get_logger
from app.core.redis_client import get_redis_client
from app.core.security import verify_api_key
from app.models.api.responses import TaskDetailResponse, TaskSummaryResponse
from app.models.domain.task import TaskStatus
from app.services.task_service import TaskService

router = APIRouter(prefix="/v1", tags=["tasks"])


@router.get("/tasks", response_model=List[TaskSummaryResponse])
async def list_tasks(
    request: Request,
    status: Optional[TaskStatus] = Query(default=None),
    agent_type: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: str | None = Depends(verify_api_key),
) -> List[TaskSummaryResponse]:
    base_logger = get_logger("ListTasks")
    request_id = request.headers.get("X-Request-Id") or request.state.request_id  # type: ignore[attr-defined]
    logger = bind_request_context(base_logger, request_id=request_id, endpoint=str(request.url.path))

    task_service = TaskService()
    tasks, _total = await task_service.list_tasks(
        status=status,
        agent_type=agent_type,
        page=page,
        page_size=page_size,
    )

    logger.info("Tasks.list", count=len(tasks))

    summaries: List[TaskSummaryResponse] = []
    for t in tasks:
        summaries.append(
            TaskSummaryResponse(
                task_id=t.task_id,
                agent_type=t.agent_type,
                selected_agent=t.selected_agent,
                status=t.status,
                created_at=t.created_at,
                completed_at=t.completed_at,
                summary=t.result.summary if t.result else None if hasattr(t, "result") else None,
            )
        )
    return summaries


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task_detail(
    request: Request,
    task_id: str = Path(...),
    _: str | None = Depends(verify_api_key),
) -> TaskDetailResponse:
    base_logger = get_logger("GetTaskDetail")
    request_id = request.headers.get("X-Request-Id") or request.state.request_id  # type: ignore[attr-defined]
    logger = bind_request_context(base_logger, request_id=request_id, endpoint=str(request.url.path))

    task_service = TaskService()
    task = await task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    agent_runs = await task_service.get_agent_runs(task_id)

    logger.info("Task.detail", task_id=task_id)

    return TaskDetailResponse(
        task_id=task.task_id,
        session_id=task.session_id,
        input_text=task.input_text,
        status=task.status,
        selected_agent=task.selected_agent,
        agent_type=task.agent_type,
        peer_routing_reason=task.peer_routing_reason,
        created_at=task.created_at,
        queued_at=task.queued_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        result=task.result,
        error=task.error.model_dump() if task.error else None,
        agent_runs=agent_runs,
        api_version="v1",
    )


@router.get("/tasks/{task_id}/events")
async def stream_task_events(
    request: Request,
    task_id: str = Path(...),
    _: str | None = Depends(verify_api_key),
):
    """
    SSE endpoint streaming task status changes.

    Frontend should connect with EventSource to:
      GET /v1/tasks/{task_id}/events
    """
    base_logger = get_logger("TaskEvents")
    request_id = request.headers.get("X-Request-Id") or request.state.request_id  # type: ignore[attr-defined]
    logger = bind_request_context(base_logger, request_id=request_id, endpoint=str(request.url.path))

    channel = f"task_events:{task_id}"
    redis = get_redis_client()

    async def event_stream():
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        logger.info("TaskEvents.subscribe", channel=channel)

        try:
            while True:
                if await request.is_disconnected():
                    logger.info("TaskEvents.client_disconnected", task_id=task_id)
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                yield f"data: {data}\n\n"
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                logger.warning("TaskEvents.cleanup_failed", task_id=task_id)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
