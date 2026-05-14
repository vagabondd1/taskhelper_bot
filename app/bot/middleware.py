import time
from typing import Any, Awaitable, Callable

import redis.asyncio as aioredis
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import redis_client
from app.db.engine import async_session_factory
from app.db.uow import _LOCK_NAMESPACE_USER

logger = get_logger(__name__)

# sliding window rate limit
_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window) + 1)
    return {0, 0}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
if #oldest > 0 then
    return {1, tonumber(oldest[2])}
end
return {1, now - window}
"""


def _extract_user_id(event: TelegramObject) -> int | None:
    update = event if isinstance(event, Update) else None
    if update is None:
        return None
    if update.message and update.message.from_user:
        return update.message.from_user.id
    if update.callback_query and update.callback_query.from_user:
        return update.callback_query.from_user.id
    return None


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_factory() as session:
            data["session"] = session
            return await handler(event, data)


class UserLockMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = _extract_user_id(event)
        session: AsyncSession | None = data.get("session")
        if user_id is not None and session is not None:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, :ns))"),
                {"key": f"user:{user_id}", "ns": _LOCK_NAMESPACE_USER},
            )
        return await handler(event, data)


# команды без обращения к LLM
_RATE_LIMIT_EXEMPT_TEXTS: frozenset[str] = frozenset({
    "/start", "/clear", "🚪 Завершить", "🧹 Очистить чат",
})


class RateLimitMiddleware(BaseMiddleware):
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        redis: aioredis.Redis,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._redis = redis

    async def _is_limited(self, user_id: int) -> tuple[bool, float]:
        key = f"rl:{user_id}"
        now = time.time()
        member = f"{now:.6f}"
        try:
            result = await self._redis.eval(
                _RATE_LIMIT_LUA, 1, key,
                str(now), str(self._window), str(self._max), member,
            )
            if result[0] == 0:
                return False, 0.0
            oldest_ts = float(result[1])
            retry_after = self._window - (now - oldest_ts)
            return True, max(1.0, retry_after)
        except Exception as exc:
            # fail-open
            logger.error("rate_limit_redis_error", error=str(exc))
            return False, 0.0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        update = event if isinstance(event, Update) else None
        message: Message | None = None
        user_id: int | None = None
        if update is not None:
            if update.message and update.message.from_user:
                message = update.message
                user_id = update.message.from_user.id
            elif update.callback_query and update.callback_query.from_user:
                user_id = update.callback_query.from_user.id

        if user_id is None:
            return await handler(event, data)

        if message is not None and message.text in _RATE_LIMIT_EXEMPT_TEXTS:
            return await handler(event, data)

        limited, retry_after = await self._is_limited(user_id)
        if limited:
            logger.warning(
                "rate_limited", user_id=user_id, retry_after=round(retry_after),
            )
            if message is not None:
                try:
                    await message.answer(
                        f"⏳ Слишком часто. Подожди {int(retry_after)} сек и повтори."
                    )
                except Exception:
                    pass
            return None

        return await handler(event, data)


def build_rate_limit_middleware() -> RateLimitMiddleware:
    return RateLimitMiddleware(
        max_requests=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
        redis=redis_client,
    )
