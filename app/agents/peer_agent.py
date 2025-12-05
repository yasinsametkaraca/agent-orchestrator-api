from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, TypedDict

from langgraph.graph import StateGraph, START, END

from app.agents.base import AgentOutput
from app.agents.registry import AgentRegistry, get_agent_registry
from app.core.config import get_settings
from app.core.errors import UnknownTaskTypeError
from app.core.logging import get_logger
from app.db.repositories.agent_runs_repo import AgentRunsRepository
from app.llm.openai_client import get_openai_client
from app.llm.base_client import LLMResult
from app.models.domain.agent_run import AgentRun, TokenUsage
from app.models.domain.task import Task


@dataclass
class TaskClassification:
    agent_name: str
    agent_type: str  # "content" | "code"
    confidence: float
    reasoning: str


class PeerAgentState(TypedDict, total=False):
    task: Task
    classification: TaskClassification
    agent_output: AgentOutput


class PeerAgentRouter:
    """
    LangGraph-based router that:
    - classifies the task
    - validates routing decision
    - executes the selected agent
    - records agent runs
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_openai_client()
        self.registry: AgentRegistry = get_agent_registry()
        self.agent_runs_repo = AgentRunsRepository()
        self.logger = get_logger("PeerAgent")
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(PeerAgentState)

        graph.add_node("classify_task", self._classify_task_node)
        graph.add_node("route_to_agent", self._route_to_agent_node)
        graph.add_node("execute_agent", self._execute_agent_node)

        graph.add_edge(START, "classify_task")
        graph.add_edge("classify_task", "route_to_agent")
        graph.add_edge("route_to_agent", "execute_agent")
        graph.add_edge("execute_agent", END)

        return graph.compile()

    async def _classify_task_node(self, state: PeerAgentState) -> Dict[str, Any]:
        task = state["task"]
        self.logger.info("PeerAgent.classify_task.start", task_id=task.task_id)

        system_prompt = """
        You are a routing agent.
        Your job is to choose the most appropriate sub-agent for the given user task.

        Available agents:
        - ContentAgent: for blog posts, explanatory articles, long-form content, documentation-style text.
        - CodeAgent: for writing, refactoring, or debugging code in any programming language.

        Respond ONLY with a JSON object, no extra text:
        {
          "agent_name": "ContentAgent" | "CodeAgent" | "Unknown",
          "agent_type": "content" | "code" | "unknown",
          "confidence": 0.0-1.0,
          "reasoning": "short explanation"
        }
        """.strip()

        user_prompt = f"User task:\n{task.input_text}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result: LLMResult = await self.llm.chat(
            model=self.settings.llm_peer_model,
            messages=messages,
            temperature=0.0,
        )

        raw_content = result.content
        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            self.logger.warning(
                "PeerAgent.classify_task.invalid_json",
                content_preview=raw_content[:200],
            )
            raise UnknownTaskTypeError("Router could not classify task. Please clarify your request.")

        agent_name = str(payload.get("agent_name") or "Unknown")
        agent_type = str(payload.get("agent_type") or "unknown")
        confidence = float(payload.get("confidence") or 0.0)
        reasoning = str(payload.get("reasoning") or "")

        classification = TaskClassification(
            agent_name=agent_name,
            agent_type=agent_type,
            confidence=confidence,
            reasoning=reasoning,
        )

        # Persist agent run for router
        agent_run = AgentRun(
            run_id=task.task_id + ":router",
            task_id=task.task_id,
            session_id=task.session_id,
            agent_name="PeerAgent",
            agent_role="router",
            input=task.input_text,
            output=json.dumps(payload, ensure_ascii=False),
            model=result.model,
            tools_used=[],
            started_at=task.created_at,
            finished_at=task.created_at,
            duration_ms=0,
            token_usage=TokenUsage(
                prompt=result.usage.prompt_tokens,
                completion=result.usage.completion_tokens,
                total=result.usage.total_tokens,
            ),
        )
        await self.agent_runs_repo.create(agent_run)

        self.logger.info(
            "PeerAgent.classify_task.completed",
            task_id=task.task_id,
            agent_name=classification.agent_name,
            agent_type=classification.agent_type,
            confidence=classification.confidence,
        )

        return {"classification": classification}

    async def _route_to_agent_node(self, state: PeerAgentState) -> Dict[str, Any]:
        classification = state["classification"]
        self.logger.info(
            "PeerAgent.route_to_agent",
            agent_name=classification.agent_name,
            agent_type=classification.agent_type,
            confidence=classification.confidence,
        )

        if classification.agent_name not in ("ContentAgent", "CodeAgent"):
            raise UnknownTaskTypeError(
                "Task cannot be routed to a known agent. Please rephrase your request."
            )

        if classification.confidence < 0.6:
            raise UnknownTaskTypeError(
                "Router is not confident about the task type. Please provide more details."
            )

        return {}

    async def _execute_agent_node(self, state: PeerAgentState) -> Dict[str, Any]:
        task = state["task"]
        classification = state["classification"]

        agent = self.registry.get(classification.agent_name)
        self.logger.info(
            "PeerAgent.execute_agent.start",
            task_id=task.task_id,
            agent_name=agent.name,
        )

        output: AgentOutput = await agent.run(task)

        self.logger.info(
            "PeerAgent.execute_agent.completed",
            task_id=task.task_id,
            agent_name=agent.name,
        )

        return {"agent_output": output}

    async def run(self, task: Task) -> tuple[AgentOutput, TaskClassification]:
        state: PeerAgentState = {"task": task}
        result_state = await self._graph.ainvoke(state)
        return result_state["agent_output"], result_state["classification"]
