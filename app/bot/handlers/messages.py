from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    ALL_MENU_BUTTONS,
    BTN_CLEAR, BTN_CODE_HINT, BTN_DESCRIBE_TASK, BTN_EXIT, BTN_EXPLAIN,
    BTN_HINT, BTN_MODE_FULL_SOLUTION, BTN_MODE_GUIDED,
    BTN_NEXT_STEP, BTN_SHARE_THINKING,
    BTN_THIS_IS_WRONG, BTN_VALIDATE_IDEA,
    end_of_plan_menu, full_solution_menu, guided_menu, mode_selector,
    remove_menu, start_menu,
)
from app.bot.sender import send_response
from app.core.utils import sanitize_text
from app.db.models import ActionType
from app.db.uow import UnitOfWork
from app.schemas.bot_response import BotResponse
from app.services.factory import make_guided_service, make_task_service

router = Router()


@router.message(CommandStart())
async def on_start(message: Message, session: AsyncSession) -> None:
    uow = UnitOfWork(session)
    has_active = False
    user = await uow.users.get_by_telegram_id(message.from_user.id)
    if user:
        active = await uow.sessions.get_active_by_user_id(user.id)
        has_active = active is not None

    await message.answer(
        "Привет! Я помогаю решать задачи по программированию.\n\n"
        "Нажми «Описать задачу», чтобы начать.",
        reply_markup=start_menu(has_active_session=has_active),
    )


async def _clear_chat(message: Message, session: AsyncSession) -> None:
    if message.chat.type != "private":
        return

    bot = message.bot
    chat_id = message.chat.id
    cmd_id = message.message_id

    start_id = max(1, cmd_id - 200)
    ids = list(range(start_id, cmd_id + 1))
    for i in range(0, len(ids), 100):
        batch = ids[i:i + 100]
        try:
            await bot.delete_messages(chat_id=chat_id, message_ids=batch)  # type: ignore[call-arg]
        except Exception:
            for mid in batch:
                try:
                    await bot.delete_message(chat_id, mid)  # type: ignore[call-arg]
                except Exception:
                    pass

    uow = UnitOfWork(session)
    user = await uow.users.get_by_telegram_id(message.from_user.id)
    if user:
        await uow.sessions.deactivate_user_sessions(user.id)
        await uow.users.set_awaiting_task(user, False)
        await uow.commit()

    try:
        await message.answer(
            "Чат очищен. Нажми «Описать задачу», чтобы начать новую сессию.",
            reply_markup=start_menu(has_active_session=False),
        )
    except Exception:
        pass


@router.message(Command("clear"))
async def on_clear(message: Message, session: AsyncSession) -> None:
    await _clear_chat(message, session)


@router.message()
async def on_message(message: Message, session: AsyncSession) -> None:
    text = sanitize_text(message.text or "").strip()
    if not text:
        return

    tg_user = message.from_user
    telegram_user_id = tg_user.id

    # Describe task
    if text == BTN_DESCRIBE_TASK:
        service = make_guided_service(session)
        result = await service.handle_describe_task(
            telegram_user_id,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
        await _respond(message, result)
        return

    # Clear chat (button)
    if text == BTN_CLEAR:
        await _clear_chat(message, session)
        return

    # Exit
    if text == BTN_EXIT:
        service = make_guided_service(session)
        result = await service.handle_exit(telegram_user_id)
        await _respond(message, result)
        return

    # Guided actions
    if text in _GUIDED_ACTION_MAP:
        service = make_guided_service(session)
        result = await _GUIDED_ACTION_MAP[text](service, telegram_user_id)
        await _respond(message, result)
        return

    # Switch to guided
    if text == BTN_MODE_GUIDED:
        service = make_guided_service(session)
        result = await service.handle_switch_to_guided_mode(telegram_user_id)
        await _respond(message, result)
        return

    # Full solution — сразу решаем
    if text == BTN_MODE_FULL_SOLUTION:
        service = make_guided_service(session)
        result = await service.handle_switch_to_full_solution_mode(telegram_user_id)
        await _respond(message, result)
        return

    # Ignore accidental clicks on stale button text
    if text in ALL_MENU_BUTTONS:
        return

    # Свободный ввод разрешён только в трёх случаях:
    # (1) user.awaiting_task_description — пользователь нажал «Описать задачу»
    # (2) active_session.awaiting_hypothesis — нажал «Проверить идею» или «Мой контекст»
    uow = UnitOfWork(session)
    user = await uow.users.get_by_telegram_id(telegram_user_id)
    active_session = None
    if user:
        active_session = await uow.sessions.get_active_by_user_id(user.id)

    if active_session and active_session.awaiting_hypothesis:
        service = make_guided_service(session)
        if active_session.last_action_type == ActionType.guided_share_thinking:
            result = await service.handle_share_thinking_message(
                telegram_user_id=telegram_user_id,
                thinking=text,
            )
        else:
            result = await service.handle_validate_my_idea_message(
                telegram_user_id=telegram_user_id,
                hypothesis=text,
            )
        await _respond(message, result)
        return

    if user and user.awaiting_task_description:
        service = make_task_service(session)
        result = await service.handle_new_task(
            telegram_user_id=telegram_user_id,
            task_text=text,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
        await _respond(message, result)
        return

    # Иначе — свободный ввод запрещён. Показываем текущее меню и просим нажать кнопку.
    await _respond(message, _build_reject_response(active_session))


def _build_reject_response(active_session) -> BotResponse:
    from app.db.models import SessionMode
    hint = "Пожалуйста, используй кнопки ниже."
    if active_session is None:
        return BotResponse(text=hint, show_start_menu=True)
    if active_session.last_action_type == ActionType.new_task:
        return BotResponse(text=hint, show_mode_selector=True)
    if active_session.current_mode == SessionMode.full_solution:
        return BotResponse(text=hint, show_full_solution_menu=True)
    return BotResponse(text=hint, show_guided_menu=True)


_GUIDED_ACTION_MAP = {
    BTN_HINT: lambda svc, uid: svc.handle_hint(uid),
    BTN_NEXT_STEP: lambda svc, uid: svc.handle_next_step(uid),
    BTN_VALIDATE_IDEA: lambda svc, uid: svc.handle_validate_my_idea_request(uid),
    BTN_SHARE_THINKING: lambda svc, uid: svc.handle_share_thinking_request(uid),
    BTN_EXPLAIN: lambda svc, uid: svc.handle_explain(uid),
    BTN_CODE_HINT: lambda svc, uid: svc.handle_code_hint(uid),
    BTN_THIS_IS_WRONG: lambda svc, uid: svc.handle_this_is_wrong(uid),
}


async def _respond(message: Message, result: BotResponse) -> None:
    if result.remove_keyboard:
        markup = remove_menu()
    elif result.show_end_of_plan_menu:
        markup = end_of_plan_menu()
    elif result.show_start_menu:
        markup = start_menu(has_active_session=result.start_menu_with_exit)
    elif result.show_guided_menu:
        markup = guided_menu()
    elif result.show_mode_selector:
        markup = mode_selector()
    elif result.show_full_solution_menu:
        markup = full_solution_menu()
    else:
        markup = None
    await send_response(message, result.text, markup)
