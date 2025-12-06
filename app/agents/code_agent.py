from __future__ import annotations

import json
import textwrap
from typing import Any, Dict

from app.agents.base import AgentOutput, BaseAgent
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.openai_client import get_openai_client
from app.models.domain.task import Task


class CodeAgent(BaseAgent):
    name = "CodeAgent"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_openai_client()
        self.logger = get_logger(self.name)

    async def run(self, task: Task) -> AgentOutput:
        """
        Generate production-oriented code with explanation.
        Uses JSON response to capture language and code separately.
        """
        self.logger.info("CodeAgent.run.start", task_id=task.task_id)

        system_prompt = textwrap.dedent(
            """
            You are a senior backend engineer.
            You write production-ready code with:
            - Input validation
            - Error handling
            - Clear structure and comments

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
            User task (verbatim, in the user's own words):
            {task.input_text}

            Decide the most appropriate programming language for this task.
            Prefer Python unless the user clearly asks for another one.
            Then produce high-quality code and a concise "description" field that follows the Language rules from
            the system message.
            """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        response = await self.llm.chat(
            model=self.settings.llm_code_model,
            messages=messages,
            temperature=0.2,
        )

        try:
            payload: Dict[str, Any] = json.loads(response.content)
        except json.JSONDecodeError:
            # Fallback: treat whole response as description + generic Python code block
            self.logger.warning("CodeAgent JSON parse failed; falling back", task_id=task.task_id)
            language = "python"
            description = "Generated code based on the request."
            code = response.content
        else:
            language = str(payload.get("language") or "python")
            description = str(payload.get("description") or "Generated code based on the request.")
            code = str(payload.get("code") or "")

        code_block = f"```{language.lower()}\n{code}\n```"
        content = f"### Description\n\n{description}\n\n### Code\n\n{code_block}"

        self.logger.info(
            "CodeAgent.run.completed",
            task_id=task.task_id,
            language=language,
            description_length=len(description),
            code_length=len(code),
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )

        return AgentOutput(
            agent_name=self.name,
            content=content,
            code_language=language.lower(),
            citations=[],
        )
