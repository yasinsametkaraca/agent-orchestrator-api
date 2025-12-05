from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class Message(BaseModel):
    session_id: Optional[str] = None
    task_id: str
    role: str  # "user" | "system" | "assistant" | "tool"
    agent_name: Optional[str] = None
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
