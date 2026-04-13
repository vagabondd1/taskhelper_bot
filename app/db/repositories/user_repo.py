from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_user_id: int) -> Optional[User]:
        result = await self._session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> User:
        user = User(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def upsert(
        self,
        telegram_user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_user_id)
        if user is None:
            user = await self.create(telegram_user_id, username, first_name)
        else:
            user.username = username
            user.first_name = first_name
            user.last_seen_at = datetime.now(timezone.utc)
            await self._session.flush()
        return user
