from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from tavily import AsyncTavilyClient

from app.core.config import get_settings
from app.core.logging import get_logger


@dataclass
class WebSearchResult:
    title: str
    url: str
    content: str
    score: float


class WebSearchTool:
    def __init__(self) -> None:
        self._logger = get_logger("WebSearchTool")
        settings = get_settings()
        api_key = settings.tavily_api_key

        if not api_key:
            # Run in "no-op" mode so the rest of the system can still function
            # (e.g. local dev, tests, or when web search is intentionally disabled).
            self._logger.warning(
                "Tavily web search disabled: TAVILY_API_KEY is not configured.",
                web_search_provider=settings.web_search_provider,
            )
            self._client: Optional[AsyncTavilyClient] = None
            return

        self._client = AsyncTavilyClient(api_key=api_key)

    async def search(self, query: str, max_results: int = 5) -> List[WebSearchResult]:
        """
        Use Tavily to search the web. We only need title, url, content, score.
        """
        if self._client is None:
            self._logger.debug(
                "WebSearchTool.search.skip",
                reason="no_api_key",
                query=query,
            )
            return []

        self._logger.debug(
            "WebSearchTool.search.start",
            query=query,
            max_results=max_results,
        )

        try:
            response = await self._client.search(
                query=query,
                max_results=max_results,
                include_answer=False,
                include_raw_content=False,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.error(
                "WebSearchTool.search.error",
                query=query,
                max_results=max_results,
                error=str(exc),
                exc_info=exc,
            )
            return []

        results: List[WebSearchResult] = []
        for item in response.get("results", []):
            results.append(
                WebSearchResult(
                    title=item.get("title") or "",
                    url=item.get("url") or "",
                    content=item.get("content") or "",
                    score=float(item.get("score") or 0.0),
                )
            )

        self._logger.debug(
            "WebSearchTool.search.completed",
            query=query,
            max_results=max_results,
            result_count=len(results),
        )
        return results
