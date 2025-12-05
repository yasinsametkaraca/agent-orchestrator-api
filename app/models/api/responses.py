from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel

from app.models.domain.agent_run import AgentRun
from app.models.domain.system_metrics import SystemMetrics
from app.models.domain.task import Citation, TaskResult, TaskStatus


class ExecuteTaskResponse(BaseModel):
    task_id: str
    session_id: Optional[str]
    status: TaskStatus
    queued_at: datetime
    message: str
    api_version: str


class TaskSummaryResponse(BaseModel):
    task_id: str
    agent_type: Optional[str]
    selected_agent: Optional[str]
    status: TaskStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    summary: Optional[str] = None


class TaskDetailResponse(BaseModel):
    task_id: str
    session_id: Optional[str]
    input_text: str
    status: TaskStatus
    selected_agent: Optional[str]
    agent_type: Optional[str]
    peer_routing_reason: Optional[str]
    created_at: datetime
    queued_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    result: Optional[TaskResult]
    error: Optional[Dict[str, Any]]
    agent_runs: List[AgentRun]
    api_version: str


class SystemMetricsResponse(SystemMetrics):
    api_version: str


class HealthResponse(BaseModel):
    status: str
    mongo: str
    redis: str
    api_version: str


class ErrorEnvelope(BaseModel):
    error: Dict[str, Any]
