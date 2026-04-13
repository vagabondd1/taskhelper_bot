from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EventLog


class EventLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        session_id: Optional[int] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> EventLog:
        entry = EventLog(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            payload=payload,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry
