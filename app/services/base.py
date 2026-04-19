from app.core.logging import get_logger
from app.db.models import ActionType, MessageRole, Session, SessionMode
from app.db.uow import UnitOfWork
from app.llm.adapter import BaseLLMClient
from app.llm.prompt_builder import build_messages
from app.schemas.llm_response import LLMResponse
from app.schemas.session_state import SessionContext

logger = get_logger(__name__)


class BaseService:
    def __init__(self, uow: UnitOfWork, llm: BaseLLMClient) -> None:
        self._uow = uow
        self._llm = llm

    async def _get_active_session(self, user_id: int) -> Session | None:
        return await self._uow.sessions.get_active_by_user_id(user_id)

    async def _call_llm(
        self,
        action: ActionType,
        session: Session,
        user_input: str | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        from app.core.config import settings

        if max_tokens is None:
            if session.current_mode == SessionMode.full_solution:
                max_tokens = settings.full_solution_max_tokens
            else:
                max_tokens = settings.guided_mode_max_tokens

        ctx = SessionContext.from_db_session(session)
        messages = build_messages(action, ctx, user_input)

        logger.info(
            "llm_call",
            action=action.value,
            session_id=session.id,
            user_id=session.user_id,
            mode=session.current_mode.value,
        )

        return await self._llm.complete(messages, max_tokens)

    async def _save_user_message(
        self,
        session: Session,
        text: str,
        action: ActionType | None = None,
    ) -> None:
        await self._uow.messages.create(
            user_id=session.user_id,
            session_id=session.id,
            role=MessageRole.user,
            text=text,
            message_type=action,
        )

    async def _save_assistant_message(
        self,
        session: Session,
        text: str,
        action: ActionType,
    ):
        return await self._uow.messages.create(
            user_id=session.user_id,
            session_id=session.id,
            role=MessageRole.assistant,
            text=text,
            message_type=action,
        )

    async def _apply_llm_response(
        self,
        session: Session,
        llm_response: LLMResponse,
        assistant_message_id: int,
    ) -> None:
        from app.db.models import SessionMode as SM

        upd = llm_response.state_update

        if upd.task_summary:
            await self._uow.sessions.set_task_summary(session, upd.task_summary)

        switch_mode = None
        if upd.switch_mode == "guided":
            switch_mode = SM.guided
        elif upd.switch_mode == "full_solution":
            switch_mode = SM.full_solution

        if switch_mode is not None:
            await self._uow.sessions.switch_mode(session, switch_mode)

        await self._uow.sessions.update_after_llm_response(
            session=session,
            action_type=llm_response.action_type,
            assistant_message_id=assistant_message_id,
            assistant_summary=llm_response.answer_summary,
            progress_summary=upd.progress_summary,
            step_increment=upd.step_increment,
            awaiting_hypothesis=upd.awaiting_hypothesis,
        )

    async def _log_event(
        self,
        event_type: str,
        session: Session,
        payload: dict | None = None,
    ) -> None:
        await self._uow.events.log(
            event_type=event_type,
            user_id=session.user_id,
            session_id=session.id,
            payload=payload,
        )
