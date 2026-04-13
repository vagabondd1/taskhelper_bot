from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionType, Message, MessageRole


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        session_id: int,
        role: MessageRole,
        text: str,
        message_type: Optional[ActionType] = None,
    ) -> Message:
        message = Message(
            user_id=user_id,
            session_id=session_id,
            role=role,
            message_text=text,
            message_type=message_type,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def get_by_id(self, message_id: int) -> Optional[Message]:
        result = await self._session.execute(
            select(Message).where(Message.id == message_id)
        )
        return result.scalar_one_or_none()

    async def get_last_n_by_session(
        self, session_id: int, n: int = 10
    ) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(n)
        )
        messages = result.scalars().all()
        return list(reversed(messages))
