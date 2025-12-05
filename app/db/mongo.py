from __future__ import annotations

import asyncio
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings
from app.core.logging import get_logger

_logger = get_logger("Mongo")

_mongo_client: Optional[AsyncIOMotorClient] = None
_mongo_client_loop: Optional[asyncio.AbstractEventLoop] = None
_mongo_db: Optional[AsyncIOMotorDatabase] = None


def get_client() -> AsyncIOMotorClient:
    """
    Return a process-wide AsyncIOMotorClient that is safe across pytest's
    multiple event loops.

    If the previously associated event loop has been closed (common between
    tests), we transparently re-initialise the client and drop the cached
    database reference.
    """
    global _mongo_client, _mongo_client_loop, _mongo_db

    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        # Called outside of an active event loop (e.g. at import time).
        current_loop = None

    if _mongo_client is None:
        settings = get_settings()
        _logger.debug(
            "Mongo client initialising",
            mongo_uri=settings.mongo_uri,
            has_loop=current_loop is not None,
        )
        _mongo_client = AsyncIOMotorClient(settings.mongo_uri)
        _mongo_client_loop = current_loop
        return _mongo_client

    # If the loop that originally created this client has since been closed
    # (typical between pytest async tests), recreate the client.
    if _mongo_client_loop is not None and _mongo_client_loop.is_closed():
        settings = get_settings()
        _logger.warning(
            "Mongo client event loop closed; reinitialising client",
            mongo_uri=settings.mongo_uri,
        )
        try:
            _mongo_client.close()
        except Exception:  # pragma: no cover - defensive
            _logger.warning("Mongo client close failed during reinit")

        _mongo_client = AsyncIOMotorClient(settings.mongo_uri)
        _mongo_client_loop = current_loop
        _mongo_db = None

    return _mongo_client


def get_database() -> AsyncIOMotorDatabase:
    """
    Return the default database for the current process.

    We keep a cached AsyncIOMotorDatabase instance but ensure it always points
    at the currently active client.
    """
    global _mongo_db

    client = get_client()
    if _mongo_db is None or getattr(_mongo_db, "client", None) is not client:
        settings = get_settings()
        _logger.debug(
            "Mongo database binding (or rebinding)",
            db_name=settings.mongo_db_name,
        )
        _mongo_db = client[settings.mongo_db_name]

    return _mongo_db
