from __future__ import annotations

import traceback

from app.agents.base import AgentOutput
from app.core.errors import UnknownTaskTypeError
from app.core.logging import get_logger
from app.core.utils import start_timer, stop_timer
from app.models.domain.task import TaskStatus
from app.services.orchestration_service import OrchestrationService
from app.services.session_service import SessionService
from app.services.task_service import TaskService
from .celery_app import celery_app
from app.worker.async_runner import run_worker_coroutine


logger = get_logger("CeleryWorker")


async def _process_task_async(task_id: str) -> None:
    task_service = TaskService()
    orchestration = OrchestrationService()
    session_service = SessionService()

    task = await task_service.get_task(task_id)
    if not task:
        logger.warning("Worker.task_not_found", task_id=task_id)
        return

    await task_service.mark_processing(task_id)
    timer_start = start_timer()

    try:
        agent_output: AgentOutput
        classification = None

        agent_output, classification = await orchestration.run_peer_agent(task)

        duration_ms = int(stop_timer(timer_start))

        # We do not re-query usage here; OrchestrationService/agents already recorded.
        await task_service.mark_completed(
            task=task,
            selected_agent=agent_output.agent_name,
            agent_type=classification.agent_type,
            peer_reason=classification.reasoning,
            content=agent_output.content,
            code_language=agent_output.code_language,
            citations=agent_output.citations,
            prompt_tokens=0,
            completion_tokens=0,
            model="",
        )

        if task.session_id:
            await session_service.update_last_task(task.session_id, task.task_id)

        logger.info(
            "Worker.process_task.completed",
            task_id=task_id,
            status=TaskStatus.COMPLETED.value,
            duration_ms=duration_ms,
        )
    except UnknownTaskTypeError as exc:
        await task_service.mark_failed(
            task=task,
            error_type="UNKNOWN_TASK_TYPE",
            message=str(exc),
        )
        logger.warning(
            "Worker.process_task.unknown_task_type",
            task_id=task_id,
            error=str(exc),
        )
    except Exception as exc:
        stack = traceback.format_exc()
        await task_service.mark_failed(
            task=task,
            error_type=exc.__class__.__name__,
            message=str(exc),
            stack=stack,
        )
        logger.error(
            "Worker.process_task.error",
            task_id=task_id,
            error=str(exc),
            stack=stack,
        )


@celery_app.task(name="process_task")
def process_task(task_id: str) -> None:
    """
    Celery entrypoint for background agent execution.

    IMPORTANT:
    We do NOT use asyncio.run() here because it creates and then closes a
    fresh event loop on every invocation. Motor/aioredis keep references to
    the first loop they interact with, so closing it leads to
    'RuntimeError("Event loop is closed")' on subsequent tasks.

    Instead we delegate to a long-lived event loop managed by
    app.worker.async_runner and synchronously wait for the coroutine to
    finish.
    """
    run_worker_coroutine(_process_task_async(task_id))
