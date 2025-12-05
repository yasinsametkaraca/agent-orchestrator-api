from functools import lru_cache
from typing import List, Optional

import logging
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # General
    environment: str = Field("local", alias="ENVIRONMENT")
    app_name: str = Field("agent-orchestrator-api", alias="APP_NAME")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    api_rate_limit_per_minute: int = Field(60, alias="RATE_LIMIT_PER_MINUTE")

    # MongoDB
    mongo_uri: str = Field(..., alias="MONGO_URI")
    mongo_db_name: str = Field("agent-orchestrator-db", alias="MONGO_DB_NAME")

    # Redis / Queue
    redis_url: str = Field(..., alias="REDIS_URL")
    redis_global_keyprefix: Optional[str] = Field(None, alias="REDIS_GLOBAL_KEYPREFIX")
    celery_broker_url: Optional[str] = Field(None, alias="CELERY_BROKER_URL")
    celery_result_backend: Optional[str] = Field(None, alias="CELERY_RESULT_BACKEND")

    # LLM / OpenAI
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    llm_peer_model: str = Field("gpt-4.1-mini", alias="LLM_PEER_MODEL")
    llm_content_model: str = Field("gpt-4.1", alias="LLM_CONTENT_MODEL")
    llm_code_model: str = Field("gpt-4o", alias="LLM_CODE_MODEL")

    # Web search
    web_search_provider: str = Field("tavily", alias="WEB_SEARCH_PROVIDER")
    tavily_api_key: Optional[str] = Field(None, alias="TAVILY_API_KEY")

    # Security
    cors_origins: List[str] = Field(default_factory=list, alias="CORS_ORIGINS")
    api_keys: List[str] = Field(default_factory=list, alias="API_KEYS")

    # Observability
    prometheus_enabled: bool = Field(True, alias="PROMETHEUS_ENABLED")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    @property
    def celery_broker(self) -> str:
        if self.celery_broker_url:
            return self.celery_broker_url
        return self.redis_url

    @property
    def celery_backend(self) -> str:
        if self.celery_result_backend:
            return self.celery_result_backend
        return self.redis_url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Centralised settings factory with a defensive debug block.

    If configuration cannot be loaded (e.g. invalid env for list fields),
    we log a small, sanitised snapshot of the relevant environment before
    re-raising the exception. This is especially helpful inside containers
    where interactive debugging is harder.
    """
    try:
        return Settings()  # type: ignore[arg-type]
    except Exception as exc:
        # Use stdlib logging here to avoid circular imports with the structured logger.
        logging.error("Failed to initialise Settings from environment.", exc_info=exc)
        logging.error(
            "Settings env snapshot (sanitised)",
            extra={
                "ENVIRONMENT": os.getenv("ENVIRONMENT"),
                "MONGO_URI_present": bool(os.getenv("MONGO_URI")),
                "MONGO_DB_NAME": os.getenv("MONGO_DB_NAME"),
                "REDIS_URL_present": bool(os.getenv("REDIS_URL")),
                # These are the fields that most often cause parsing issues:
                "CORS_ORIGINS_raw": os.getenv("CORS_ORIGINS"),
                "API_KEYS_raw": os.getenv("API_KEYS"),
            },
        )
        raise
