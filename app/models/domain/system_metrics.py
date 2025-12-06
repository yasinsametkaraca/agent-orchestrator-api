from datetime import date, datetime
from typing import Dict, List

from pydantic import BaseModel, ConfigDict, Field


class DailyMetrics(BaseModel):
    date: date
    total_tasks: int
    tasks_per_agent: Dict[str, int]
    avg_latency_ms: float
    p95_latency_ms: float


class AllTimeMetrics(BaseModel):
    total_tasks: int
    tasks_per_agent: Dict[str, int]
    avg_latency_ms: float
    p95_latency_ms: float
    first_task_at: datetime | None = None
    last_task_at: datetime | None = None


class SystemMetrics(BaseModel):
    date: date
    total_tasks: int
    tasks_per_agent: Dict[str, int]
    pending_tasks: int
    avg_latency_ms: float
    p95_latency_ms: float
    api_health: Dict[str, str]

    last_5_days: List[DailyMetrics] = Field(default_factory=list)

    all_time: AllTimeMetrics | None = None

    model_config = ConfigDict(from_attributes=True)
