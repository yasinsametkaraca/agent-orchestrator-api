from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.llm.base_client import BaseLLMClient, LLMResult, LLMUsage


class OpenAILLMClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)

    async def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
        response_format: Dict[str, Any] | None = None,
    ) -> LLMResult:
        params: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            params["response_format"] = response_format

        response = await self._client.chat.completions.create(**params)
        choice = response.choices[0]
        content = choice.message.content or ""

        usage = LLMUsage(
            prompt_tokens=getattr(response.usage, "prompt_tokens", 0),
            completion_tokens=getattr(response.usage, "completion_tokens", 0),
            total_tokens=getattr(response.usage, "total_tokens", 0),
        )
        return LLMResult(content=content, usage=usage, model=response.model or model)


_llm_client: Optional[OpenAILLMClient] = None


def get_openai_client() -> OpenAILLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAILLMClient()
    return _llm_client
