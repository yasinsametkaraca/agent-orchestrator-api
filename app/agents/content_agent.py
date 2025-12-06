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
        self._min_citations = 2
        self._max_citations = 5

    def _build_search_query(self, raw_text: str) -> str:
        """
        Build a concise, Tavily-friendly search query from the user input.

        Keeping this logic in a dedicated helper makes it easier to extend
        (e.g., keyword extraction, trimming boilerplate) without touching
        the main run() flow.
        """
        query = raw_text.strip()
        if len(query) > 200:
            return query[:200]
        return query

    def _append_reference_section_if_missing(self, content: str, citations: List[Citation]) -> str:
        """
        Ensure there is a well-formed References section that:
        - Uses numeric indices [1], [2], ...
        - Renders links as HTML anchors so clients can open them in new tabs.

        We intentionally keep this post-processing lightweight and additive:
        if the model already produced a References section, we leave it as-is.
        """
        if not citations:
            return content

        normalized = content.lower()
        if "## references" in normalized or "\nreferences\n" in normalized:
            # Assume the model already produced a references section.
            return content

        lines: List[str] = ["", "## References"]
        index = 1
        for citation in citations:
            if not citation.url:
                continue
            title = citation.title or citation.url
            lines.append(
                f'- [{index}] <a href="{citation.url}" target="_blank" rel="noopener noreferrer">{title}</a>'
            )
            index += 1

        if index == 1:
            # No usable URLs were available; avoid adding an empty section.
            return content

        return content.rstrip() + "\n\n" + "\n".join(lines) + "\n"

    async def run(self, task: Task) -> AgentOutput:
        """
        Generate a blog-style, well-structured content piece using web context.
        """
        self.logger.info("ContentAgent.run.start", task_id=task.task_id)

        # Step 1: Build a concise search query
        query = self._build_search_query(task.input_text)
        self.logger.debug("ContentAgent.search.query_built", task_id=task.task_id, query=query)

        # Step 2: Run web search with defensive error handling
        search_results: List[WebSearchResult] = []
        try:
            search_results = await self.web_search.search(query=query, max_results=self._max_citations)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.error(
                "ContentAgent.search.failed",
                task_id=task.task_id,
                query=query,
                error=str(exc),
                exc_info=exc,
            )

        limited_results = search_results[: self._max_citations]
        if not limited_results:
            self.logger.warning(
                "ContentAgent.search.no_results",
                task_id=task.task_id,
                query=query,
            )
        elif len(limited_results) < self._min_citations:
            self.logger.warning(
                "ContentAgent.search.too_few_results",
                task_id=task.task_id,
                found=len(limited_results),
                min_required=self._min_citations,
            )
        else:
            self.logger.debug(
                "ContentAgent.search.results_ok",
                task_id=task.task_id,
                count=len(limited_results),
            )

        citations: List[Citation] = []
        search_context_lines: List[str] = []
        for idx, r in enumerate(limited_results, start=1):
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

            Your responsibilities:
            - Produce clear, well-structured, long-form content (like a high-quality blog post or article).
            - Use Markdown headings, subheadings, and bullet points where appropriate.
            - Explain concepts step by step, with coherent sections and smooth transitions.
            - Minimise hallucinations by grounding your content in the provided web search context.

            Citation requirements:
            - Treat the provided "Web Search Context" as the only authoritative external sources.
            - Each source in the context is labeled with a numeric index like [1], [2], etc.
            - When you rely on a specific source, append an inline numeric citation such as [1] or [2]
              immediately after the relevant sentence.
            - Use at least two distinct sources if that many are available, and never more than five.
            - Do not invent new indices or URLs.

            References section:
            - At the end of the article, include a "## References" section.
            - List the sources in numeric order using their indices [1], [2], etc.
            - For each source, render a clickable link using HTML so that clients can open it in a new
              browser tab, for example:
              <a href="https://example.com" target="_blank" rel="noopener noreferrer">Source title</a>

            Language rules:
            - By default, respond in the same language as the user's request.
            - If the user explicitly asks for a specific output language (for example: "write the article in English"),
              you MUST follow that explicit instruction even if the request itself is written in another language.
            - Ensure that the overall article (excluding code snippets, technical terms, or quoted fragments) follows
              the chosen output language consistently.

            Important:
            - If some information is not supported by the web search context, say that explicitly or keep the
              explanation high-level instead of hallucinating details.
            - If the web search context is empty, write a best-effort article using your general knowledge and clearly
              mention that references are limited or unavailable.
            """
        ).strip()

        user_prompt = textwrap.dedent(
            f"""
            User task (verbatim):
            {task.input_text}

            Web Search Context:
            {search_context}

            Instructions:
            - Determine the most appropriate output language by applying the Language rules from the system message.
            - Then write a high-quality, well-structured article that fully addresses the user task.
            - Make sure to include inline numeric citations [1], [2], ... whenever you rely on specific sources from
              the Web Search Context.
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
        content = self._append_reference_section_if_missing(content, citations)

        self.logger.info(
            "ContentAgent.run.completed",
            task_id=task.task_id,
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            citations=len(citations),
        )

        return AgentOutput(
            agent_name=self.name,
            content=content,
            code_language=None,
            citations=citations,
        )
