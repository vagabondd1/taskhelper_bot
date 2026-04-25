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

TASK_SEPARATOR = "━━━━━━━━━━━━━━━\n✅ Предыдущая задача завершена\n━━━━━━━━━━━━━━━"


class GuidedService(BaseService):

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
        await self._uow.sessions.deactivate_user_sessions(user.id)
        await self._uow.commit()

        outro = "\n\nГотово, задача решена! 🎉 Нажми «Описать задачу», чтобы взять новую."
        return BotResponse(
            text=llm_response.response_text + outro,
            show_start_menu=True,
        )

    async def handle_hint(self, telegram_user_id: int) -> BotResponse:
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_hint, "hint"
        )

    async def handle_next_step(self, telegram_user_id: int) -> BotResponse:
        user = await self._uow.users.get_by_telegram_id(telegram_user_id)
        if not user:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)
        session = await self._get_active_session(user.id)
        if not session:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        if not session.plan_steps or session.total_steps is None:
            await self._uow.commit()
            return BotResponse(
                text="⚠️ План ещё не сформирован. Нажми «💡 Подсказка» — "
                     "это подгрузит контекст задачи.",
                show_guided_menu=True,
            )

        if session.current_step_index + 1 >= session.total_steps:
            await self._log_event("next_step_plan_end", session)
            await self._uow.commit()
            text = (
                f"🏁 Все шаги плана пройдены (всего: {session.total_steps}).\n"
                "Нажми «🚪 Завершить», чтобы закрыть задачу."
            )
            return BotResponse(text=text, show_end_of_plan_menu=True)

        try:
            llm_response = await self._call_llm(
                action=ActionType.guided_next_step, session=session
            )
        except Exception as e:
            logger.error("next_step_llm_error", error=str(e), session_id=session.id)
            await self._uow.commit()
            return BotResponse(text=_LLM_ERROR, show_guided_menu=True, error=True)

        assistant_msg = await self._save_assistant_message(
            session, llm_response.response_text, llm_response.action_type
        )
        await self._apply_llm_response(
            session, llm_response, assistant_msg.id, force_step_increment=True
        )
        await self._log_event("next_step", session)
        await self._uow.commit()

        return BotResponse(text=llm_response.response_text, show_guided_menu=True)

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
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_validate_idea, "validate_idea_request"
        )

    async def handle_share_thinking_request(self, telegram_user_id: int) -> BotResponse:
        return await self._simple_guided_action(
            telegram_user_id, ActionType.guided_share_thinking, "share_thinking_request"
        )

    async def handle_share_thinking_message(
        self, telegram_user_id: int, thinking: str
    ) -> BotResponse:
        ok, error_msg = validate_user_input_length(thinking)
        if not ok:
            return BotResponse(text=error_msg, error=True)

        user = await self._uow.users.get_by_telegram_id(telegram_user_id)
        if not user:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        session = await self._get_active_session(user.id)
        if not session:
            return BotResponse(text=_NO_ACTIVE_SESSION, error=True)

        await self._uow.sessions.set_last_user_message(session, thinking)
        await self._save_user_message(session, thinking, ActionType.guided_share_thinking)

        try:
            llm_response = await self._call_llm(
                action=ActionType.guided_share_thinking,
                session=session,
                user_input=thinking,
            )
        except Exception as e:
            logger.error("share_thinking_llm_error", error=str(e), session_id=session.id)
            session.awaiting_hypothesis = False
            await self._uow.commit()
            return BotResponse(text=_LLM_ERROR, show_guided_menu=True, error=True)

        assistant_msg = await self._save_assistant_message(
            session, llm_response.response_text, llm_response.action_type
        )
        await self._apply_llm_response(session, llm_response, assistant_msg.id)
        await self._log_event("share_thinking_submit", session)
        await self._uow.commit()

        return BotResponse(
            text=llm_response.response_text,
            show_guided_menu=True,
        )

    async def handle_validate_my_idea_message(
        self, telegram_user_id: int, hypothesis: str
    ) -> BotResponse:
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
            session.awaiting_hypothesis = False
            await self._uow.commit()
            return BotResponse(text=_LLM_ERROR, show_guided_menu=True, error=True)

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

    async def handle_exit(self, telegram_user_id: int) -> BotResponse:
        user = await self._uow.users.get_by_telegram_id(telegram_user_id)
        if not user:
            return BotResponse(
                text="Активного диалога нет. Нажми «Описать задачу», чтобы начать.",
                show_start_menu=True,
            )

        session = await self._get_active_session(user.id)
        had_session = session is not None
        if had_session:
            await self._uow.sessions.deactivate_user_sessions(user.id)
            await self._log_event("session_exit", session)
        await self._uow.users.set_awaiting_task(user, False)
        await self._uow.commit()

        if had_session:
            text = TASK_SEPARATOR + "\n\nДиалог завершён. Нажми «Описать задачу», чтобы начать новую."
        else:
            text = "Активного диалога нет. Нажми «Описать задачу», чтобы начать."

        return BotResponse(text=text, show_start_menu=True)

    async def handle_describe_task(
        self, telegram_user_id: int, username: str | None = None, first_name: str | None = None
    ) -> BotResponse:
        user = await self._uow.users.upsert(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
        )

        had_session = False
        session = await self._get_active_session(user.id)
        if session is not None:
            had_session = True
            await self._uow.sessions.deactivate_user_sessions(user.id)
            await self._log_event("session_reset_on_describe", session)

        await self._uow.users.set_awaiting_task(user, True)
        await self._uow.commit()

        prompt = "Опиши условие задачи одним сообщением — я помогу её решить."
        if had_session:
            text = TASK_SEPARATOR + "\n\n" + prompt
        else:
            text = prompt

        return BotResponse(text=text, show_start_menu=True)

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

        in_guided = session.current_mode == SessionMode.guided
        return BotResponse(
            text=llm_response.response_text,
            show_guided_menu=in_guided,
            show_full_solution_menu=not in_guided,
        )
