from __future__ import annotations

from datetime import date
from typing import Dict

from pydantic import BaseModel, ConfigDict


class SystemMetrics(BaseModel):
    date: date
    total_tasks: int
    tasks_per_agent: Dict[str, int]
    pending_tasks: int
    avg_latency_ms: float
    p95_latency_ms: float
    api_health: Dict[str, str]

    model_config = ConfigDict(from_attributes=True)
