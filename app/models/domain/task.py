from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Citation(BaseModel):
    source: str
    title: Optional[str] = None
    url: Optional[str] = None

    model_config = ConfigDict(frozen=True)


class TaskErrorInfo(BaseModel):
    type: Optional[str] = None
    message: Optional[str] = None
    stack: Optional[str] = None


class TaskResult(BaseModel):
    summary: Optional[str] = None
    raw_output: Optional[str] = None
    code_language: Optional[str] = None
    citations: List[Citation] = Field(default_factory=list)


class TaskMetadata(BaseModel):
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    api_key_id: Optional[str] = None


class TaskCost(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    usd_estimate: Optional[float] = None


class Task(BaseModel):
    task_id: str
    session_id: Optional[str] = None
    input_text: str
    status: TaskStatus
    selected_agent: Optional[str] = None
    agent_type: Optional[str] = None  # "content" or "code"
    peer_routing_reason: Optional[str] = None

    created_at: datetime
    updated_at: datetime
    queued_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    error: Optional[TaskErrorInfo] = None
    result: Optional[TaskResult] = None
    metadata: Optional[TaskMetadata] = None
    cost: Optional[TaskCost] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        from_attributes=True,
    )


class TaskCreate(BaseModel):
    input_text: str
    session_id: Optional[str] = None
    metadata: Optional[TaskMetadata] = None


class TaskUpdate(BaseModel):
    status: Optional[TaskStatus] = None
    selected_agent: Optional[str] = None
    agent_type: Optional[str] = None
    peer_routing_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[TaskErrorInfo] = None
    result: Optional[TaskResult] = None
    cost: Optional[TaskCost] = None
