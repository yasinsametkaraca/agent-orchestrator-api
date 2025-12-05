from __future__ import annotations

from celery import Celery

from app.core.config import get_settings
from app.core.logging import get_logger


logger = get_logger("CeleryApp")


def _create_celery_app() -> Celery:
    """
    Factory for the Celery application.

    Responsibilities:
    - Wire broker/backend from Settings
    - Ensure worker imports our task module via `include`
    - Emit a structured debug log for visibility in containers
    """
    settings = get_settings()

    app = Celery(
        "agent_orchestrator_worker",
        broker=settings.celery_broker,
        backend=settings.celery_backend,
        # Ensure the worker process imports this module and registers `process_task`.
        include=["app.worker.tasks"],
    )

    app.conf.update(
        task_default_queue="agent_tasks",
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_time_limit=900,
        task_soft_time_limit=840,
    )

    logger.info(
        "Celery app configured",
        broker=settings.celery_broker,
        backend=settings.celery_backend,
        default_queue=app.conf.task_default_queue,
    )

    return app


celery_app = _create_celery_app()
