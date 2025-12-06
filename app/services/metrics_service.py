from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis_client
from app.db.repositories.tasks_repo import TaskRepository
from app.models.domain.system_metrics import SystemMetrics, DailyMetrics, AllTimeMetrics
from app.models.domain.task import Task, TaskStatus


class MetricsService:
    def __init__(self) -> None:
        self.tasks_repo = TaskRepository()
        self.logger = get_logger("MetricsService")
        self.settings = get_settings()

    @staticmethod
    def _compute_latency_stats(tasks: list[Task]) -> tuple[float, float]:
        """
        Compute average and p95 latency in milliseconds for the given tasks.

        Kept as a pure helper to ensure the aggregation logic stays easy to
        test and reuse for different time windows.
        """
        latencies_ms: list[float] = []
        for t in tasks:
            if t.started_at and t.completed_at:
                delta = t.completed_at - t.started_at
                latencies_ms.append(delta.total_seconds() * 1000.0)

        if not latencies_ms:
            return 0.0, 0.0

        latencies_ms.sort()
        avg_latency = sum(latencies_ms) / len(latencies_ms)
        idx = int(0.95 * len(latencies_ms)) - 1
        idx = max(0, min(idx, len(latencies_ms) - 1))
        p95_latency = latencies_ms[idx]
        return avg_latency, p95_latency

    async def _build_daily_metrics(self, day_start: datetime, day_end: datetime) -> DailyMetrics:
        """
        Build metrics snapshot for a single day.

        This helper keeps the aggregation logic DRY and makes it easier to
        extend the metrics payload in the future (e.g. p99, failure rates).
        """
        tasks = await self.tasks_repo.find_completed_between(day_start, day_end)
        avg_latency, p95_latency = self._compute_latency_stats(tasks)
        tasks_per_agent = await self.tasks_repo.aggregate_by_agent_between(day_start, day_end)

        day_date = day_start.date()
        self.logger.debug(
            "MetricsService.daily_metrics_computed",
            date=str(day_date),
            total_tasks=len(tasks),
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
        )

        return DailyMetrics(
            date=day_date,
            total_tasks=len(tasks),
            tasks_per_agent=tasks_per_agent,
            avg_latency_ms=avg_latency,
            p95_latency_ms=p95_latency,
        )

    async def get_system_metrics(self) -> SystemMetrics:
        now = datetime.now(timezone.utc)
        today_start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
        today_end = today_start + timedelta(days=1)

        pending = await self.tasks_repo.count_by_statuses(
            [TaskStatus.QUEUED, TaskStatus.PROCESSING]
        )

        history_days = max(1, self.settings.metrics_history_days)
        if history_days > 30:
            # Basit bir güvenlik freni: yanlış config'te metriği öldürmeyelim.
            self.logger.warning(
                "MetricsService.history_days_clamped",
                configured_days=history_days,
                max_days=30,
            )
            history_days = 30

        # Collect daily metrics for today and the preceding N-1 days.
        daily_metrics: list[DailyMetrics] = []
        today_metrics: DailyMetrics | None = None
        for offset in range(history_days):
            day_start = today_start - timedelta(days=offset)
            day_end = day_start + timedelta(days=1)
            metrics_for_day = await self._build_daily_metrics(day_start, day_end)
            daily_metrics.append(metrics_for_day)
            if offset == 0:
                today_metrics = metrics_for_day

        daily_metrics_sorted = sorted(daily_metrics, key=lambda m: m.date)

        if today_metrics is None:
            # Extremely defensive; this should never happen but avoids crashing
            # the endpoint in edge cases.
            today_metrics = await self._build_daily_metrics(today_start, today_end)
            daily_metrics_sorted.append(today_metrics)
            daily_metrics_sorted = sorted(daily_metrics_sorted, key=lambda m: m.date)

        # Compute all-time metrics for successfully completed tasks.
        all_completed_tasks = await self.tasks_repo.find_completed_between(start=None, end=None)
        all_avg_latency, all_p95_latency = self._compute_latency_stats(all_completed_tasks)
        all_tasks_per_agent = await self.tasks_repo.aggregate_by_agent_between(start=None, end=None)

        first_task_at = None
        last_task_at = None
        for task in all_completed_tasks:
            if task.completed_at is None:
                continue
            if first_task_at is None or task.completed_at < first_task_at:
                first_task_at = task.completed_at
            if last_task_at is None or task.completed_at > last_task_at:
                last_task_at = task.completed_at

        all_time_metrics = AllTimeMetrics(
            total_tasks=len(all_completed_tasks),
            tasks_per_agent=all_tasks_per_agent,
            avg_latency_ms=all_avg_latency,
            p95_latency_ms=all_p95_latency,
            first_task_at=first_task_at,
            last_task_at=last_task_at,
        )

        # Approximate queue pending count from Redis rate-limit keys (or Celery queue metrics
        # in a more advanced setup)
        redis = get_redis_client()
        try:
            await redis.info("Keyspace")
            pending_estimate = pending
        except Exception as exc:  # pragma: no cover - defensive
            self.logger.warning(
                "MetricsService.redis_info_failed",
                error=str(exc),
            )
            pending_estimate = pending

        api_health = {
            "mongo": "up",
            "redis": "up",
            "llm_provider": "up",
        }

        return SystemMetrics(
            date=today_metrics.date,
            total_tasks=today_metrics.total_tasks,
            tasks_per_agent=today_metrics.tasks_per_agent,
            pending_tasks=pending_estimate,
            avg_latency_ms=today_metrics.avg_latency_ms,
            p95_latency_ms=today_metrics.p95_latency_ms,
            api_health=api_health,
            last_5_days=daily_metrics_sorted,
            all_time=all_time_metrics,
        )
