from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ActionType, Session, SessionMode, SessionStatus


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_by_user_id(self, user_id: int) -> Optional[Session]:
        result = await self._session.execute(
            select(Session)
            .where(Session.user_id == user_id, Session.status == SessionStatus.active)
            .order_by(Session.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, session_id: int) -> Optional[Session]:
        result = await self._session.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        task_text: str,
        mode: SessionMode = SessionMode.guided,
    ) -> Session:
        db_session = Session(
            user_id=user_id,
            current_task_text=task_text,
            last_user_message=task_text,
            current_mode=mode,
            status=SessionStatus.active,
        )
        self._session.add(db_session)
        await self._session.flush()
        return db_session

    async def deactivate_user_sessions(self, user_id: int) -> None:
        result = await self._session.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.status == SessionStatus.active,
            )
        )
        sessions = result.scalars().all()
        for s in sessions:
            s.status = SessionStatus.completed
        await self._session.flush()

    async def update_after_llm_response(
        self,
        session: Session,
        action_type: ActionType,
        assistant_message_id: int,
        assistant_summary: str,
        progress_summary: Optional[str] = None,
        step_increment: bool = False,
        awaiting_hypothesis: bool = False,
    ) -> Session:
        session.last_action_type = action_type
        session.last_assistant_message_id = assistant_message_id
        session.last_assistant_summary = assistant_summary
        session.awaiting_hypothesis = awaiting_hypothesis

        if progress_summary is not None:
            session.current_progress_summary = progress_summary

        if step_increment:
            session.current_step_index += 1

        await self._session.flush()
        return session

    async def set_task_summary(self, session: Session, task_summary: str) -> Session:
        session.task_summary = task_summary
        await self._session.flush()
        return session

    async def switch_mode(self, session: Session, mode: SessionMode) -> Session:
        session.current_mode = mode
        session.awaiting_hypothesis = False
        await self._session.flush()
        return session

    async def set_last_user_message(self, session: Session, message: str) -> Session:
        session.last_user_message = message
        await self._session.flush()
        return session
