from __future__ import annotations

import textwrap
from typing import List

from app.agents.base import AgentOutput, BaseAgent
from app.core.config import get_settings
from app.llm.openai_client import get_openai_client
from app.llm.tools.web_search_tool import WebSearchResult, WebSearchTool
from app.models.domain.task import Citation, Task
from app.core.logging import get_logger


class ContentAgent(BaseAgent):
    name = "ContentAgent"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = get_openai_client()
        self.web_search = WebSearchTool()
        self.logger = get_logger(self.name)

    async def run(self, task: Task) -> AgentOutput:
        """
        Generate a blog-style, well-structured content piece using web context.
        """
        self.logger.info("ContentAgent.run.start", task_id=task.task_id)

        # Step 1: Build a concise search query
        query = task.input_text.strip()
        if len(query) > 200:
            query = query[:200]

        search_results: List[WebSearchResult] = await self.web_search.search(query=query, max_results=5)

        citations: List[Citation] = []
        search_context_lines: List[str] = []
        for idx, r in enumerate(search_results, start=1):
            citations.append(
                Citation(
                    source="tavily",
                    title=r.title,
                    url=r.url,
                )
            )
            snippet = r.content.replace("\n", " ")
            if len(snippet) > 400:
                snippet = snippet[:400] + "..."
            search_context_lines.append(
                f"[{idx}] Title: {r.title}\nURL: {r.url}\nSnippet: {snippet}"
            )

        search_context = "\n\n".join(search_context_lines) if search_context_lines else "No search results."

        system_prompt = textwrap.dedent(
            """
            You are a senior technical content writer.
            You write clear, well-structured, long-form content (like a blog post).
            You MUST:
            - Use Markdown headings, subheadings, and bullet points.
            - Explain concepts step by step.
            - Avoid hallucinations by using the provided web search context.
            - At the end, include a "References" section listing the main sources.

            IMPORTANT:
            - Do not invent URLs.
            - If something is not supported by the search context, say that explicitly.
            """
        ).strip()

        user_prompt = textwrap.dedent(
            f"""
            User Task:
            {task.input_text}

            Web Search Context:
            {search_context}

            Write a high-quality article in English that addresses the user task.
            """
        ).strip()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        result = await self.llm.chat(
            model=self.settings.llm_content_model,
            messages=messages,
            temperature=0.4,
        )

        content = result.content

        # Append references section if not present (simple heuristic)
        if "References" not in content:
            refs_lines = ["\n\n## References"]
            for c in citations:
                if c.url:
                    refs_lines.append(f"- [{c.title or c.url}]({c.url})")
            content = content + "\n" + "\n".join(refs_lines)

        self.logger.info(
            "ContentAgent.run.completed",
            task_id=task.task_id,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
        )

        return AgentOutput(
            agent_name=self.name,
            content=content,
            code_language=None,
            citations=citations,
        )
