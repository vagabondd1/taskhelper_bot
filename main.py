import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import callbacks, messages
from app.bot.middleware import DbSessionMiddleware
from app.core.config import settings
from app.core.logging import get_logger, setup_logging


async def main() -> None:
    setup_logging()
    logger = get_logger(__name__)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()

    dp.update.middleware(DbSessionMiddleware())

    dp.include_router(messages.router)
    dp.include_router(callbacks.router)

    logger.info("bot_starting", model=settings.qwen_model)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
