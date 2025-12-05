from celery import Celery

from app.core.config import Settings, get_settings
from app.core.logging import get_logger


logger = get_logger("CeleryApp")


def _build_global_keyprefix(settings: Settings) -> str:
    """
    Build a Redis Cluster-friendly global keyprefix for Celery.

    We purposely use a Redis hash tag (the part inside `{}`) so that all
    Celery-related keys (queues, pidbox, results) land in the same hash
    slot when the broker is backed by a Redis Cluster (e.g. AWS ElastiCache
    with cluster-mode enabled). This avoids `ClusterCrossSlotError` when
    Celery issues multi-key or pipelined operations.
    """
    base = (settings.redis_global_keyprefix or settings.app_name).strip()
    if not base:
        base = "celery"

    # If the operator already provided an explicit hash tag, respect it.
    if "{" in base or "}" in base:
        hash_tag = base
    else:
        hash_tag = f"{{{base}}}"

    # Celery's redis transport will prepend this to every key.
    # Example: "{agent-orchestrator-api}.agent_tasks"
    return f"{hash_tag}."


def _create_celery_app() -> Celery:
    """
    Factory for the Celery application.

    Responsibilities:
    - Wire broker/backend from Settings
    - Ensure worker imports our task module via `include`
    - Emit a structured debug log for visibility in containers
    """
    settings = get_settings()
    global_keyprefix = _build_global_keyprefix(settings)

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

    # Redis Cluster compatibility: force all Celery keys into the same
    # hash slot via a shared hash tag prefix.
    app.conf.broker_transport_options = {
        "global_keyprefix": global_keyprefix,
    }
    app.conf.result_backend_transport_options = {
        "global_keyprefix": global_keyprefix,
    }

    logger.info(
        "Celery app configured",
        broker=settings.celery_broker,
        backend=settings.celery_backend,
        default_queue=app.conf.task_default_queue,
        redis_url=settings.redis_url,
        redis_global_keyprefix=settings.redis_global_keyprefix,
        global_keyprefix=global_keyprefix,
    )

    return app


celery_app = _create_celery_app()
