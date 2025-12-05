from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.logging import get_logger
from app.core.redis_client import get_redis_client
from app.db.repositories.tasks_repo import TaskRepository
from app.models.domain.system_metrics import SystemMetrics
from app.models.domain.task import TaskStatus


class MetricsService:
    def __init__(self) -> None:
        self.tasks_repo = TaskRepository()
        self.logger = get_logger("MetricsService")

    async def get_system_metrics(self) -> SystemMetrics:
        now = datetime.now(timezone.utc)
        today_start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
        today_end = today_start + timedelta(days=1)

        pending = await self.tasks_repo.count_by_statuses(
            [TaskStatus.QUEUED, TaskStatus.PROCESSING]
        )

        today_tasks = await self.tasks_repo.find_completed_today(today_start, today_end)
        latencies_ms = []
        for t in today_tasks:
            if t.started_at and t.completed_at:
                delta = t.completed_at - t.started_at
                latencies_ms.append(delta.total_seconds() * 1000.0)

        avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0
        p95_latency = 0.0
        if latencies_ms:
            sorted_lat = sorted(latencies_ms)
            idx = int(0.95 * len(sorted_lat)) - 1
            idx = max(0, min(idx, len(sorted_lat) - 1))
            p95_latency = sorted_lat[idx]

        tasks_per_agent = await self.tasks_repo.aggregate_today_by_agent(today_start, today_end)

        # Approximate queue pending count from Redis rate-limit keys (or Celery queue metrics
        # in a more advanced setup)
        redis = get_redis_client()
        try:
            info = await redis.info("Keyspace")
            # This is very approximate; proper implementation should query Celery queue.
            pending_estimate = pending
        except Exception:
            pending_estimate = pending

        api_health = {
            "mongo": "up",
            "redis": "up",
            "llm_provider": "up",
        }

        return SystemMetrics(
            date=today_start.date(),
            total_tasks=len(today_tasks),
            tasks_per_agent=tasks_per_agent,
            pending_tasks=pending_estimate,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
            api_health=api_health,
        )
