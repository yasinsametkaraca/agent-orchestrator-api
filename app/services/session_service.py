from __future__ import annotations

from typing import Optional

from app.core.logging import get_logger
from app.core.utils import generate_uuid, utc_now
from app.db.repositories.sessions_repo import SessionsRepository
from app.models.domain.session import Session


class SessionService:
    def __init__(self) -> None:
        self.repo = SessionsRepository()
        self.logger = get_logger("SessionService")

    async def ensure_session(self, session_id: Optional[str], ip: Optional[str]) -> str:
        if session_id:
            existing = await self.repo.get_by_session_id(session_id)
            if existing:
                existing.updated_at = utc_now()
                await self.repo.update(session_id, existing)
                return session_id

        new_session_id = generate_uuid()
        now = utc_now()
        session = Session(
            session_id=new_session_id,
            created_at=now,
            updated_at=now,
            metadata={"ip": ip},
            last_task_id=None,
        )
        await self.repo.create(session)
        self.logger.info("SessionService.session_created", session_id=new_session_id)
        return new_session_id

    async def update_last_task(self, session_id: str, task_id: str) -> None:
        existing = await self.repo.get_by_session_id(session_id)
        if not existing:
            return
        existing.last_task_id = task_id
        existing.updated_at = utc_now()
        await self.repo.update(session_id, existing)
