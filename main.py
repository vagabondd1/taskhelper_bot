import asyncio
import signal

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from app.bot.handlers import messages
from app.bot.middleware import (
    DbSessionMiddleware,
    UserLockMiddleware,
    build_rate_limit_middleware,
)
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.redis import redis_client
from app.llm.client import llm_client


async def main() -> None:
    setup_logging()
    logger = get_logger(__name__)

    # parse_mode сознательно НЕ задаём по умолчанию — sender.py сам решает,
    # когда использовать Markdown (при наличии fenced-блока кода).
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()

    dp.update.middleware(build_rate_limit_middleware())
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(UserLockMiddleware())
    dp.include_router(messages.router)

    @dp.errors()
    async def on_any_error(event: ErrorEvent) -> None:
        exc = event.exception
        logger.exception(
            "unhandled_update_error",
            exc_type=type(exc).__name__,
        )
        msg = getattr(event.update, "message", None) or getattr(
            getattr(event.update, "callback_query", None), "message", None
        )
        if msg is None:
            return
        try:
            await msg.answer("Что-то пошло не так. Попробуй ещё раз или /clear.")
        except Exception:
            pass

    logger.info("bot_starting", model=settings.qwen_model)

    await bot.delete_webhook(drop_pending_updates=True)

    # Graceful shutdown: SIGTERM/SIGINT → останавливаем polling,
    # дожидаемся завершения активных handler'ов, закрываем клиенты.
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        if not stop_event.is_set():
            logger.info("shutdown_signal_received")
            stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows / некоторые контейнеры — пропускаем, fallback на KeyboardInterrupt
            pass

    polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))

    try:
        done, _ = await asyncio.wait(
            {polling_task, asyncio.create_task(stop_event.wait())},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if polling_task not in done:
            await dp.stop_polling()
            await polling_task
    finally:
        await llm_client.aclose()
        await redis_client.aclose()
        await bot.session.close()
        logger.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
