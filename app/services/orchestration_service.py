from __future__ import annotations

from typing import Tuple

from app.agents.peer_agent import PeerAgentRouter, TaskClassification
from app.agents.base import AgentOutput
from app.core.errors import LLMError, UnknownTaskTypeError
from app.core.logging import get_logger
from app.llm.openai_client import get_openai_client
from app.models.domain.task import Task


class OrchestrationService:
    def __init__(self) -> None:
        self.logger = get_logger("OrchestrationService")
        self.router = PeerAgentRouter()
        self.llm = get_openai_client()

    async def run_peer_agent(self, task: Task) -> Tuple[AgentOutput, TaskClassification]:
        try:
            output, classification = await self.router.run(task)
            return output, classification
        except UnknownTaskTypeError:
            raise
        except Exception as exc:
            self.logger.error(
                "OrchestrationService.run_peer_agent_error",
                task_id=task.task_id,
                error=str(exc),
                exc_info=exc,
            )
            raise LLMError("Failed to run peer agent.") from exc
