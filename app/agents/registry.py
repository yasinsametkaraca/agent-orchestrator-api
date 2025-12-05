from __future__ import annotations

from typing import Dict

from app.agents.base import BaseAgent
from app.agents.code_agent import CodeAgent
from app.agents.content_agent import ContentAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}
        self._register_default_agents()

    def _register_default_agents(self) -> None:
        self.register(ContentAgent())
        self.register(CodeAgent())

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent:
        if name not in self._agents:
            raise KeyError(f"Agent '{name}' not registered.")
        return self._agents[name]

    @property
    def agents(self) -> Dict[str, BaseAgent]:
        return dict(self._agents)


_agent_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry
