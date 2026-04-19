from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import guided_menu, mode_selector
from app.bot.sender import send_response
from app.db.engine import async_session_factory
from app.db.uow import UnitOfWork
from app.llm.client import llm_client
from app.services.factory import make_guided_service, make_task_service

router = Router()


@router.message(CommandStart())
async def on_start(message: Message, session: AsyncSession) -> None:
    await message.answer(
        "Привет! Я помогаю решать задачи по программированию.\n\n"
        "Отправь мне условие задачи, и мы начнём 🚀"
    )


@router.message()
async def on_message(message: Message, session: AsyncSession) -> None:
    text = (message.text or "").strip()
    if not text:
        return

    tg_user = message.from_user
    telegram_user_id = tg_user.id

    # Проверяем, ждёт ли активная сессия гипотезу пользователя
    uow = UnitOfWork(session)
    user = await uow.users.get_by_telegram_id(telegram_user_id)

    if user:
        active_session = await uow.sessions.get_active_by_user_id(user.id)
        if active_session and active_session.awaiting_hypothesis:
            service = make_guided_service(session)
            result = await service.handle_validate_my_idea_message(
                telegram_user_id=telegram_user_id,
                hypothesis=text,
            )
            markup = guided_menu() if result.show_guided_menu else None
            await send_response(message, result.text, markup)
            return

    # Обычное сообщение — новая задача
    service = make_task_service(session)
    result = await service.handle_new_task(
        telegram_user_id=telegram_user_id,
        task_text=text,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )

    markup = mode_selector() if result.show_mode_selector else None
    await send_response(message, result.text, markup)
