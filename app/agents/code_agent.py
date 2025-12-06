from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from typing import Any, Dict, TypedDict

from langgraph.graph import StateGraph, START, END

from app.agents.base import AgentOutput, BaseAgent
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base_client import LLMResult, LLMUsage
from app.llm.openai_client import get_openai_client
from app.models.domain.task import Task


@dataclass
class CodeTaskPlan:
    language: str
    description: str
    tests_required: bool
    notes: str


@dataclass
class GeneratedCodeArtifact:
    language: str
    description: str
    code: str


class CodeAgentState(TypedDict, total=False):
    task: Task
    plan: CodeTaskPlan
    generated: GeneratedCodeArtifact
    plan_usage: LLMUsage
    generate_usage: LLMUsage


class CodeAgent(BaseAgent):
    name = "CodeAgent"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_openai_client()
        self.logger = get_logger(self.name)
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(CodeAgentState)

        graph.add_node("plan_task", self._plan_task_node)
        graph.add_node("generate_code", self._generate_code_node)

        graph.add_edge(START, "plan_task")
        graph.add_edge("plan_task", "generate_code")
        graph.add_edge("generate_code", END)

        return graph.compile()

    async def _plan_task_node(self, state: CodeAgentState) -> Dict[str, Any]:
        task = state["task"]
        self.logger.info("CodeAgent.plan_task.start", task_id=task.task_id)

        system_prompt = textwrap.dedent(
            """
            You are helping another agent generate production-grade code.
            Your job is to analyse the user's request and produce a compact plan.

            Output requirements:
            - Respond ONLY with valid JSON, with no surrounding commentary:
              {
                "language": "<programming-language-name>",
                "description": "<high level description of what needs to be implemented>",
                "tests_required": <true|false>,
                "notes": "<short reasoning or important constraints>"
              }

            Language rules:
            - Choose the most appropriate programming language based on the user task.
            - Prefer Python unless the user clearly asks for a different language.
            """
        ).strip()

        user_prompt = textwrap.dedent(
            f"""
            User programming task (verbatim):
            {task.input_text}

            Analyse the task and produce the planning JSON as described above.
            """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result: LLMResult = await self.llm.chat(
            model=self.settings.llm_peer_model,
            messages=messages,
            temperature=0.0,
        )

        try:
            payload: Dict[str, Any] = json.loads(result.content)
        except json.JSONDecodeError:
            self.logger.warning(
                "CodeAgent.plan_task.json_parse_failed",
                task_id=task.task_id,
                content_preview=result.content[:200],
            )
            plan = CodeTaskPlan(
                language="python",
                description="Fallback plan generated because planning JSON could not be parsed.",
                tests_required=False,
                notes="Check planner prompt and model behaviour.",
            )
        else:
            language = str(payload.get("language") or "python")
            description = str(
                payload.get("description")
                or "Implement the behaviour described in the user task."
            )
            tests_required_raw = payload.get("tests_required")
            tests_required = bool(tests_required_raw) if tests_required_raw is not None else False
            notes = str(payload.get("notes") or payload.get("reasoning") or "")

            plan = CodeTaskPlan(
                language=language,
                description=description,
                tests_required=tests_required,
                notes=notes,
            )

        self.logger.info(
            "CodeAgent.plan_task.completed",
            task_id=task.task_id,
            language=plan.language,
            tests_required=plan.tests_required,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
        )

        return {"plan": plan, "plan_usage": result.usage}

    async def _generate_code_node(self, state: CodeAgentState) -> Dict[str, Any]:
        task = state["task"]
        plan = state.get("plan")

        if plan is None:
            self.logger.warning(
                "CodeAgent.generate_code.missing_plan",
                task_id=task.task_id,
            )
            plan = CodeTaskPlan(
                language="python",
                description="Default plan (no planner output available).",
                tests_required=False,
                notes="Planner was unavailable; using defaults.",
            )

        self.logger.info(
            "CodeAgent.generate_code.start",
            task_id=task.task_id,
            language=plan.language,
        )

        system_prompt = textwrap.dedent(
            """
            You are a senior developer.
            You write production-ready code with:
            - Input validation
            - Error handling
            - Clear structure and comments
            - Small, single-responsibility functions where appropriate

            Output requirements:
            - You MUST respond in the following JSON format ONLY (no extra text):
              {
                "language": "<programming-language-name>",
                "description": "<short explanation of what the code does>",
                "code": "<the full code, without markdown fences>"
              }
            - The "language" field describes the programming language of the code (e.g., "python", "typescript").
            - The "description" field MUST be written in the appropriate natural language, following the language
              rules below.

            Language rules:
            - By default, the "description" must use the same language as the user's request.
            - If the user explicitly asks for a specific output language (for example: "write the explanation in English"),
              you MUST follow that explicit instruction even if the request itself is written in another language.
            - Keep technical identifiers (variable names, function names, etc.) in the most idiomatic form for the
              chosen programming language, but keep surrounding explanation text aligned with the requested natural
              language.
            """
        ).strip()

        user_prompt = textwrap.dedent(
            f"""
            User programming task (verbatim):
            {task.input_text}

            Planning summary:
            - Target language: {plan.language}
            - High-level description: {plan.description}
            - Tests required: {plan.tests_required}
            - Notes: {plan.notes}

            Implement the requested behaviour according to this plan and return JSON as described in the system message.
            """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result: LLMResult = await self.llm.chat(
            model=self.settings.llm_code_model,
            messages=messages,
            temperature=0.2,
        )

        try:
            payload: Dict[str, Any] = json.loads(result.content)
        except json.JSONDecodeError:
            self.logger.warning(
                "CodeAgent.generate_code.json_parse_failed",
                task_id=task.task_id,
                content_preview=result.content[:200],
            )
            language = plan.language or "python"
            description = "Generated code based on the request and planning information."
            code = result.content
        else:
            language = str(payload.get("language") or plan.language or "python")
            description = str(
                payload.get("description")
                or "Generated code based on the request and planning information."
            )
            code = str(payload.get("code") or "")

        artifact = GeneratedCodeArtifact(
            language=language,
            description=description,
            code=code,
        )

        self.logger.info(
            "CodeAgent.generate_code.completed",
            task_id=task.task_id,
            language=artifact.language,
            description_length=len(artifact.description),
            code_length=len(artifact.code),
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
        )

        return {"generated": artifact, "generate_usage": result.usage}

    async def run(self, task: Task) -> AgentOutput:
        """
        Generate production-oriented code with explanation using an internal LangGraph pipeline.
        """
        self.logger.info("CodeAgent.run.start", task_id=task.task_id)

        state: CodeAgentState = {"task": task}
        try:
            result_state: CodeAgentState = await self._graph.ainvoke(state)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "CodeAgent.run.error",
                task_id=task.task_id,
                error=str(exc),
                exc_info=exc,
            )
            raise

        artifact = result_state.get("generated")
        if artifact is None:
            self.logger.warning(
                "CodeAgent.run.no_artifact",
                task_id=task.task_id,
            )
            language = "python"
            description = "Code generation did not produce a structured artifact; see logs for details."
            code = ""
        else:
            language = artifact.language
            description = artifact.description
            code = artifact.code

        code_block = f"```{language.lower()}\n{code}\n```"
        content = f"### Description\n\n{description}\n\n### Code\n\n{code_block}"

        plan_usage = result_state.get("plan_usage")
        generate_usage = result_state.get("generate_usage")

        total_prompt_tokens = 0
        total_completion_tokens = 0
        if isinstance(plan_usage, LLMUsage):
            total_prompt_tokens += plan_usage.prompt_tokens
            total_completion_tokens += plan_usage.completion_tokens
        if isinstance(generate_usage, LLMUsage):
            total_prompt_tokens += generate_usage.prompt_tokens
            total_completion_tokens += generate_usage.completion_tokens

        self.logger.info(
            "CodeAgent.run.completed",
            task_id=task.task_id,
            language=language,
            description_length=len(description),
            code_length=len(code),
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
        )

        return AgentOutput(
            agent_name=self.name,
            content=content,
            code_language=language.lower(),
            citations=[],
        )
