from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.config import get_settings
from app.core.logging import bind_request_context, get_logger
from app.core.security import verify_api_key
from app.models.api.requests import ExecuteTaskRequest
from app.models.api.responses import ExecuteTaskResponse
from app.models.domain.task import TaskMetadata, TaskStatus
from app.services.session_service import SessionService
from app.services.task_service import TaskService
from app.worker.tasks import process_task

router = APIRouter(prefix="/v1/agent", tags=["agent"])


@router.post("/execute", response_model=ExecuteTaskResponse)
async def execute_task(
    payload: ExecuteTaskRequest,
    request: Request,
    _: str | None = Depends(verify_api_key),
) -> ExecuteTaskResponse:
    settings = get_settings()
    base_logger = get_logger("AgentExecute")

    request_id = request.headers.get("X-Request-Id") or request.state.request_id  # type: ignore[attr-defined]
    logger = bind_request_context(
        base_logger,
        request_id=request_id,
        endpoint=str(request.url.path),
    )

    if not payload.task.strip():
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Task cannot be empty.")

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    metadata = TaskMetadata(
        ip=client_ip,
        user_agent=user_agent,
        request_id=request_id,
        api_key_id=None,
    )

    session_service = SessionService()
    session_id = await session_service.ensure_session(payload.session_id, client_ip)

    task_service = TaskService()
    task = await task_service.create_task(
        task_text=payload.task,
        session_id=session_id,
        metadata=metadata,
    )
    await session_service.update_last_task(session_id, task.task_id)

    logger.info("Task enqueued", task_id=task.task_id, session_id=session_id)

    # Enqueue Celery job
    process_task.delay(task.task_id)

    return ExecuteTaskResponse(
        task_id=task.task_id,
        session_id=session_id,
        status=TaskStatus.QUEUED,
        queued_at=task.queued_at,
        message="Task accepted and queued.",
        api_version="v1",
    )
