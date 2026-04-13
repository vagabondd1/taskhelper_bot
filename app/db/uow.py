from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.attempt_repo import AttemptRepository
from app.db.repositories.event_log_repo import EventLogRepository
from app.db.repositories.message_repo import MessageRepository
from app.db.repositories.session_repo import SessionRepository
from app.db.repositories.user_repo import UserRepository


class UnitOfWork:
    """Группирует все репозитории в одну транзакцию."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.users = UserRepository(session)
        self.sessions = SessionRepository(session)
        self.messages = MessageRepository(session)
        self.attempts = AttemptRepository(session)
        self.events = EventLogRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
