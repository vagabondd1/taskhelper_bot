from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attempt, ValidationResult


class AttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        session_id: int,
        user_hypothesis: str,
        user_hypothesis_summary: Optional[str] = None,
        validation_result: Optional[ValidationResult] = None,
        llm_feedback: Optional[str] = None,
    ) -> Attempt:
        attempt = Attempt(
            user_id=user_id,
            session_id=session_id,
            user_hypothesis=user_hypothesis,
            user_hypothesis_summary=user_hypothesis_summary,
            validation_result=validation_result,
            llm_feedback=llm_feedback,
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def get_by_session(self, session_id: int) -> list[Attempt]:
        result = await self._session.execute(
            select(Attempt)
            .where(Attempt.session_id == session_id)
            .order_by(Attempt.created_at.asc())
        )
        return list(result.scalars().all())
