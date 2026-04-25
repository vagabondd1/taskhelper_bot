from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.core.utils import validate_user_input_length
from app.db.models import ActionType, MessageRole
from app.schemas.bot_response import BotResponse
from app.services.base import BaseService
from app.services.guided_service import TASK_SEPARATOR

logger = get_logger(__name__)

_NEW_TASK_CD_PREFIX = "new_task_cd:"


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

        # Cooldown: не позволяем отправлять новые задачи слишком часто.
        # SET NX атомарно занимает слот; если ключ уже есть — cooldown активен.
        cd_key = f"{_NEW_TASK_CD_PREFIX}{telegram_user_id}"
        try:
            acquired = await redis_client.set(
                cd_key, "1", ex=settings.new_task_cooldown_seconds, nx=True
            )
            if acquired is None:
                ttl = await redis_client.ttl(cd_key)
                wait = max(1, ttl)
                logger.warning("new_task_cooldown", user_id=telegram_user_id, wait=wait)
                return BotResponse(
                    text=f"⏳ Подожди {wait} сек перед отправкой новой задачи.",
                    error=True,
                )
        except Exception as exc:
            # Redis недоступен — пропускаем проверку (fail-open).
            logger.error("new_task_cooldown_redis_error", error=str(exc))

        user = await self._uow.users.upsert(
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
        )

        had_active = await self._uow.sessions.get_active_by_user_id(user.id) is not None
        await self._uow.sessions.deactivate_user_sessions(user.id)
        await self._uow.users.set_awaiting_task(user, False)
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

        if llm_response.is_off_topic:
            await self._uow.sessions.deactivate_user_sessions(user.id)
            await self._log_event("off_topic", session, {"task_length": len(task_text)})
            await self._uow.commit()
            logger.info("new_task_off_topic", session_id=session.id, user_id=user.id)
            return BotResponse(
                text=llm_response.response_text,
                show_start_menu=True,
            )

        await self._log_event("new_task", session, {"task_length": len(task_text)})
        await self._uow.commit()

        logger.info("new_task_created", session_id=session.id, user_id=user.id)

        text = llm_response.response_text
        if had_active:
            text = TASK_SEPARATOR + "\n\n" + text

        return BotResponse(
            text=text,
            show_mode_selector=True,
        )
