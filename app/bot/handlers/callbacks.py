from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import (
    CB_CODE_HINT, CB_EXPLAIN, CB_GET_FULL_SOLUTION,
    CB_HINT, CB_MODE_FULL_SOLUTION, CB_MODE_GUIDED,
    CB_NEXT_STEP, CB_THIS_IS_WRONG, CB_VALIDATE_IDEA,
    full_solution_menu, guided_menu,
)
from app.bot.sender import send_response
from app.services.factory import make_guided_service

router = Router()


def _user_id(callback: CallbackQuery) -> int:
    return callback.from_user.id


async def _handle(
    callback: CallbackQuery,
    session: AsyncSession,
    coro,
) -> None:
    await callback.answer()
    result = await coro

    if result.show_guided_menu:
        markup = guided_menu()
    elif result.show_mode_selector:
        from app.bot.keyboards import mode_selector
        markup = mode_selector()
    else:
        markup = full_solution_menu() if not result.show_guided_menu else None

    await send_response(callback.message, result.text, markup)


@router.callback_query(F.data == CB_MODE_GUIDED)
async def on_mode_guided(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_switch_to_guided_mode(_user_id(callback))
    await send_response(callback.message, result.text, guided_menu() if not result.error else None)


@router.callback_query(F.data == CB_MODE_FULL_SOLUTION)
async def on_mode_full_solution(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_switch_to_full_solution_mode(_user_id(callback))
    await send_response(callback.message, result.text, full_solution_menu() if not result.error else None)


@router.callback_query(F.data == CB_HINT)
async def on_hint(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_hint(_user_id(callback))
    await send_response(callback.message, result.text, guided_menu() if result.show_guided_menu else None)


@router.callback_query(F.data == CB_NEXT_STEP)
async def on_next_step(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_next_step(_user_id(callback))
    await send_response(callback.message, result.text, guided_menu() if result.show_guided_menu else None)


@router.callback_query(F.data == CB_VALIDATE_IDEA)
async def on_validate_idea(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_validate_my_idea_request(_user_id(callback))
    # После запроса гипотезы меню не показываем — ждём текст от пользователя
    await send_response(callback.message, result.text, None)


@router.callback_query(F.data == CB_EXPLAIN)
async def on_explain(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_explain(_user_id(callback))
    await send_response(callback.message, result.text, guided_menu() if result.show_guided_menu else None)


@router.callback_query(F.data == CB_CODE_HINT)
async def on_code_hint(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_code_hint(_user_id(callback))
    await send_response(callback.message, result.text, guided_menu() if result.show_guided_menu else None)


@router.callback_query(F.data == CB_THIS_IS_WRONG)
async def on_this_is_wrong(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_this_is_wrong(_user_id(callback))
    await send_response(callback.message, result.text, guided_menu() if result.show_guided_menu else None)


@router.callback_query(F.data == CB_GET_FULL_SOLUTION)
async def on_get_full_solution(callback: CallbackQuery, session: AsyncSession) -> None:
    await callback.answer()
    service = make_guided_service(session)
    result = await service.handle_full_solution(_user_id(callback))
    markup = full_solution_menu() if not result.error else None
    await send_response(callback.message, result.text, markup)
