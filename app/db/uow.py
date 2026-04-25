from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.attempt_repo import AttemptRepository
from app.db.repositories.event_log_repo import EventLogRepository
from app.db.repositories.message_repo import MessageRepository
from app.db.repositories.session_repo import SessionRepository
from app.db.repositories.user_repo import UserRepository


# Постоянный namespace для advisory-локов (произвольный int4).
# Защищает от случайного пересечения с локами, которые кто-то может
# взять в миграциях или сторонних расширениях.
_LOCK_NAMESPACE_USER = 0x7B07_0001


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

    async def lock_user(self, telegram_user_id: int) -> None:
        """Сериализует обработку update'ов одного пользователя.

        pg_advisory_xact_lock — exclusive, отпускается на commit/rollback.
        Защищает от двойных кликов / гонок: второй handler ждёт первого,
        вместо того чтобы создавать дубликат сессии или писать state поверх
        свежего состояния.
        """
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :uid)"),
            {"ns": _LOCK_NAMESPACE_USER, "uid": telegram_user_id},
        )
