from __future__ import annotations

from typing import Protocol

from app.models.domain.task import Citation, Task


class AgentOutput:
    def __init__(
        self,
        *,
        agent_name: str,
        content: str,
        code_language: str | None = None,
        citations: list[Citation] | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.content = content
        self.code_language = code_language
        self.citations = citations or []


class BaseAgent(Protocol):
    name: str

    async def run(self, task: Task) -> AgentOutput: ...
