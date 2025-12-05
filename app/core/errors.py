from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from .logging import get_logger


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400, *, extra: Optional[Dict[str, Any]] = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}
        super().__init__(message)


class UnknownTaskTypeError(AppError):
    def __init__(self, message: str = "Unknown task type. Please be more specific.") -> None:
        super().__init__(code="UNKNOWN_TASK_TYPE", message=message, status_code=400)


class RateLimitExceededError(AppError):
    def __init__(self, message: str = "Too many requests. Please try again later.") -> None:
        super().__init__(code="RATE_LIMIT_EXCEEDED", message=message, status_code=429)


class LLMError(AppError):
    def __init__(self, message: str = "LLM request failed.") -> None:
        super().__init__(code="LLM_ERROR", message=message, status_code=502)


class ErrorResponse(BaseModel):
    error: Dict[str, Any]


def _app_error_response(exc: AppError) -> JSONResponse:
    body: Dict[str, Any] = {"error": {"code": exc.code, "message": exc.message}}
    if exc.extra:
        body["error"]["details"] = exc.extra
    return JSONResponse(status_code=exc.status_code, content=body)


def setup_exception_handlers(app: FastAPI) -> None:
    logger = get_logger("exception-handler")

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        logger.warning("AppError", code=exc.code, message=exc.message, extra=exc.extra)
        return _app_error_response(exc)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        body: Dict[str, Any] = {
            "error": {
                "code": "HTTP_ERROR",
                "message": exc.detail,
            }
        }
        logger.warning("HTTPException", status_code=exc.status_code, detail=exc.detail)
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(ValidationError)
    async def pydantic_validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
        logger.warning("ValidationError", errors=exc.errors())
        body: Dict[str, Any] = {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": exc.errors(),
            }
        }
        return JSONResponse(status_code=422, content=body)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception", exc_info=exc)
        body: Dict[str, Any] = {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Unexpected error occurred.",
            }
        }
        return JSONResponse(status_code=500, content=body)
