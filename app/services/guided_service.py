from app.core.logging import get_logger
from app.core.utils import validate_user_input_length
from app.db.models import ActionType, SessionMode
from app.schemas.bot_response import BotResponse
from app.services.base import BaseService

logger = get_logger(__name__)

_NO_ACTIVE_SESSION = (
    "Нет активной задачи. Отправь текст задачи, чтобы начать."
)
_LLM_ERROR = (
    "Что-то пошло не так при обращении к модели. "
    "Попробуй ещё раз — сессия сохранена."
)


class GuidedService(BaseService):

    # ------------------------------------------------------------------ #
    #  Переключение режимов                                                #
    # ------------------------------------------------------------------ #

    async def handle_switch_to_guided_mode(self, telegram_user_id: int) -> BotResponse:
        user = await self._uow.users.get_by_telegram_id(telegram_user_id)
        if not user:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        session = await self._get_active_session(user.id)
        if not session:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        await self._uow.sessions.switch_mode(session, SessionMode.guided)
        await self._log_event("mode_switch", session, {"mode": "guided"})
        await self._uow.commit()

        return BotResponse(
            text="Переключился в пошаговый режим. Используй кнопки ниже.",
            show_guided_menu=True,
        )

    async def handle_switch_to_full_solution_mode(self, telegram_user_id: int) -> BotResponse:
        user = await self._uow.users.get_by_telegram_id(telegram_user_id)
        if not user:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        session = await self._get_active_session(user.id)
        if not session:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        await self._uow.sessions.switch_mode(session, SessionMode.full_solution)
        await self._log_event("mode_switch", session, {"mode": "full_solution"})
        await self._uow.commit()

        return BotResponse(
            text="Переключился в режим полного решения. Нажми кнопку ниже, чтобы получить решение.",
            show_guided_menu=False,
        )

    # ------------------------------------------------------------------ #
    #  Guided mode actions                                                 #
    # ------------------------------------------------------------------ #

    async def handle_hint(self, telegram_user_id: int) -> BotResponse:
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_hint, "hint"
        )

    async def handle_next_step(self, telegram_user_id: int) -> BotResponse:
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_next_step, "next_step"
        )

    async def handle_explain(self, telegram_user_id: int) -> BotResponse:
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_explain, "explain"
        )

    async def handle_code_hint(self, telegram_user_id: int) -> BotResponse:
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_code_hint, "code_hint"
        )

    async def handle_this_is_wrong(self, telegram_user_id: int) -> BotResponse:
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_recheck, "this_is_wrong"
        )

    async def handle_validate_my_idea_request(self, telegram_user_id: int) -> BotResponse:
        """Нажатие кнопки validate my idea — переводим сессию в ожидание гипотезы."""
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_validate_idea, "validate_idea_request"
        )

    async def handle_validate_my_idea_message(
        self, telegram_user_id: int, hypothesis: str
    ) -> BotResponse:
        """Пользователь прислал гипотезу после validate my idea."""
        ok, error_msg = validate_user_input_length(hypothesis)
        if not ok:
            return BotResponse(text=error_msg, error=True)

        user = await self._uow.users.get_by_telegram_id(telegram_user_id)
        if not user:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        session = await self._get_active_session(user.id)
        if not session:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        await self._uow.sessions.set_last_user_message(session, hypothesis)
        await self._save_user_message(session, hypothesis, ActionType.guided_validate_idea)

        try:
            llm_response = await self._call_llm(
                action=ActionType.guided_validate_idea,
                session=session,
                user_input=hypothesis,
            )
        except Exception as e:
            logger.error("validate_idea_llm_error", error=str(e), session_id=session.id)
            await self._uow.commit()
            return BotResponse(text=_LLM_ERROR, error=True)

        await self._uow.attempts.create(
            user_id=user.id,
            session_id=session.id,
            user_hypothesis=hypothesis,
            user_hypothesis_summary=hypothesis[:200],
            validation_result=llm_response.validation_result,
            llm_feedback=llm_response.answer_summary,
        )

        assistant_msg = await self._save_assistant_message(
            session, llm_response.response_text, llm_response.action_type
        )
        await self._apply_llm_response(session, llm_response, assistant_msg.id)
        await self._log_event(
            "validate_idea_submit",
            session,
            {"result": llm_response.validation_result.value if llm_response.validation_result else None},
        )
        await self._uow.commit()

        return BotResponse(
            text=llm_response.response_text,
            show_guided_menu=True,
        )

    # ------------------------------------------------------------------ #
    #  Full solution                                                       #
    # ------------------------------------------------------------------ #

    async def handle_full_solution(self, telegram_user_id: int) -> BotResponse:
        user = await self._uow.users.get_by_telegram_id(telegram_user_id)
        if not user:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        session = await self._get_active_session(user.id)
        if not session:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        try:
            llm_response = await self._call_llm(
                action=ActionType.full_solution,
                session=session,
            )
        except Exception as e:
            logger.error("full_solution_llm_error", error=str(e), session_id=session.id)
            await self._uow.commit()
            return BotResponse(text=_LLM_ERROR, error=True)

        assistant_msg = await self._save_assistant_message(
            session, llm_response.response_text, llm_response.action_type
        )
        await self._apply_llm_response(session, llm_response, assistant_msg.id)
        await self._log_event("full_solution", session)
        await self._uow.commit()

        return BotResponse(
            text=llm_response.response_text,
            show_guided_menu=False,
        )

    # ------------------------------------------------------------------ #
    #  Internal                                                            #
    # ------------------------------------------------------------------ #

    async def _simple_guided_action(
        self,
        telegram_user_id: int,
        action: ActionType,
        event_type: str,
    ) -> BotResponse:
        user = await self._uow.users.get_by_telegram_id(telegram_user_id)
        if not user:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        session = await self._get_active_session(user.id)
        if not session:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        try:
            llm_response = await self._call_llm(action=action, session=session)
        except Exception as e:
            logger.error(f"{event_type}_llm_error", error=str(e), session_id=session.id)
            await self._uow.commit()
            return BotResponse(text=_LLM_ERROR, error=True)

        assistant_msg = await self._save_assistant_message(
            session, llm_response.response_text, llm_response.action_type
        )
        await self._apply_llm_response(session, llm_response, assistant_msg.id)
        await self._log_event(event_type, session)
        await self._uow.commit()

        show_guided = session.current_mode == SessionMode.guided
        return BotResponse(
            text=llm_response.response_text,
            show_guided_menu=show_guided,
        )
