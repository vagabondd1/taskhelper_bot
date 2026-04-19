from app.core.logging import get_logger
from app.core.utils import validate_user_input_length
from app.db.models import ActionType, MessageRole
from app.schemas.bot_response import BotResponse
from app.services.base import BaseService

logger = get_logger(__name__)


class TaskService(BaseService):

    async def handle_new_task(
        self,
        telegram_user_id: int,
        task_text: str,
        username: str | None = None,
        first_name: str | None = None,
    ) -> BotResponse:
        ok, error_msg = validate_user_input_length(task_text)
        if not ok:
            return BotResponse(text=error_msg, error=True)

        user = await self._uow.users.upsert(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
        )

        await self._uow.sessions.deactivate_user_sessions(user.id)
        session = await self._uow.sessions.create(user_id=user.id, task_text=task_text)

        await self._uow.messages.create(
            user_id=user.id,
            session_id=session.id,
            role=MessageRole.user,
            text=task_text,
            message_type=ActionType.new_task,
        )

        try:
            llm_response = await self._call_llm(
                action=ActionType.new_task,
                session=session,
                user_input=task_text,
            )
        except Exception as e:
            logger.error("new_task_llm_error", error=str(e), session_id=session.id)
            await self._uow.commit()
            return BotResponse(
                text="Не удалось обработать задачу. Попробуй ещё раз.",
                error=True,
            )

        assistant_msg = await self._save_assistant_message(
            session, llm_response.response_text, llm_response.action_type
        )
        await self._apply_llm_response(session, llm_response, assistant_msg.id)
        await self._log_event("new_task", session, {"task_length": len(task_text)})
        await self._uow.commit()

        logger.info("new_task_created", session_id=session.id, user_id=user.id)

        return BotResponse(
            text=llm_response.response_text,
            show_mode_selector=True,
        )
