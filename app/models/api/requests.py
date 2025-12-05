from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExecuteTaskRequest(BaseModel):
    task: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class PaginationQuery(BaseModel):
    page: int = 1
    page_size: int = 20
