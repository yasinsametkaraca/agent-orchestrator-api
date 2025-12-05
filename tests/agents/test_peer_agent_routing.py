from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from app.agents.peer_agent import PeerAgentRouter
from app.llm.base_client import BaseLLMClient, LLMResult, LLMUsage
from app.models.domain.task import Task, TaskStatus
from app.core.utils import utc_now


class DummyLLM(BaseLLMClient):
    async def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
        response_format: Dict[str, Any] | None = None,
    ) -> LLMResult:
        user_content = messages[-1]["content"].lower()
        if "kod yaz" in user_content or "code" in user_content:
            payload = {
                "agent_name": "CodeAgent",
                "agent_type": "code",
                "confidence": 0.9,
                "reasoning": "User explicitly asked to write code.",
            }
        else:
            payload = {
                "agent_name": "ContentAgent",
                "agent_type": "content",
                "confidence": 0.9,
                "reasoning": "User seems to want a blog-style answer.",
            }
        return LLMResult(
            content=json.dumps(payload),
            usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            model=model,
        )


@pytest.mark.asyncio
async def test_peer_agent_routes_code_task(monkeypatch):
    global _llm_client
    _llm_client = DummyLLM()  # type: ignore[assignment]

    router = PeerAgentRouter()

    now = utc_now()
    task = Task(
        task_id="test-task-1",
        session_id="session-1",
        input_text="Python ile bir dosyayı okuyup yazan kod yaz",
        status=TaskStatus.QUEUED,
        selected_agent=None,
        agent_type=None,
        peer_routing_reason=None,
        created_at=now,
        updated_at=now,
        queued_at=now,
        started_at=None,
        completed_at=None,
        error=None,
        result=None,
        metadata=None,
        cost=None,
    )

    output, classification = await router.run(task)
    assert classification.agent_name == "CodeAgent"
    assert classification.agent_type == "code"
    assert "CodeAgent" in output.agent_name
