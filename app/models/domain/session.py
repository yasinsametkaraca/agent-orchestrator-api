from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel, ConfigDict


class Session(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = {}
    last_task_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
