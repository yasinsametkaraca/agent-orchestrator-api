from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    prompt: int = 0
    completion: int = 0
    total: int = 0


class AgentRun(BaseModel):
    run_id: str
    task_id: str
    session_id: Optional[str] = None
    agent_name: str
    agent_role: str  # "router" | "executor"
    input: str
    output: str
    model: str
    tools_used: List[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    token_usage: TokenUsage

    model_config = ConfigDict(from_attributes=True)
