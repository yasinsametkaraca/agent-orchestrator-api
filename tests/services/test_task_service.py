from __future__ import annotations

import pytest

from app.models.domain.task import TaskMetadata
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_task_service_create_and_get(monkeypatch):
    service = TaskService()
    metadata = TaskMetadata(ip="127.0.0.1", user_agent="pytest", request_id="req-1", api_key_id=None)

    task = await service.create_task(task_text="blog yaz", session_id="session-1", metadata=metadata)

    assert task.task_id
    fetched = await service.get_task(task.task_id)
    assert fetched is not None
    assert fetched.input_text == "blog yaz"
