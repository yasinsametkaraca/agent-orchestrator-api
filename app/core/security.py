from __future__ import annotations

from typing import List, Optional

from fastapi import Depends, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.utils import get_authorization_scheme_param
from fastapi import FastAPI

from .config import get_settings
from .logging import get_logger


def configure_cors(app: FastAPI) -> None:
    settings = get_settings()

    origins: List[str] = settings.cors_origins
    if not origins:
        # Default to no wildcard for security; allow localhost for dev
        origins = ["http://localhost", "http://localhost:5173", "http://127.0.0.1"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


async def get_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> Optional[str]:
    return x_api_key


async def verify_api_key(api_key: Optional[str] = Depends(get_api_key)) -> Optional[str]:
    settings = get_settings()
    logger = get_logger("security")

    if not settings.api_keys:
        # API key auth disabled
        return None

    if not api_key:
        logger.warning("Missing API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key.",
        )

    if api_key not in settings.api_keys:
        logger.warning("Invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
        )

    return api_key


async def get_bearer_token(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> Optional[str]:
    if not authorization:
        return None
    scheme, credentials = get_authorization_scheme_param(authorization)
    if scheme.lower() != "bearer":
        return None
    return credentials
