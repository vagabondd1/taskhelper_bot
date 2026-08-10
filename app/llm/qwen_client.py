import asyncio
import hashlib
import json
import time
from typing import Any

from openai import APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.adapter import BaseLLMClient
from app.schemas.llm_response import LLMResponse

logger = get_logger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 2.0

# Circuit breaker: после _CB_FAIL_THRESHOLD подряд неудач переходим в OPEN
# и быстро отказываем все запросы в течение _CB_RESET_SECONDS, чтобы
# не молотить мёртвый upstream и не сжигать токены пользователей.
_CB_FAIL_THRESHOLD = 5
_CB_RESET_SECONDS = 30.0


class _CircuitBreaker:
    """Минимальный 3-state breaker (closed → open → half-open)."""

    def __init__(self, threshold: int, reset_seconds: float) -> None:
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None

    def allow(self) -> bool:
        if self._opened_at is None:
            return True
        if time.monotonic() - self._opened_at >= self._reset_seconds:
            # half-open: пропускаем один пробный вызов
            return True
        return False

    def on_success(self) -> None:
        was_open = self._opened_at is not None
        self._failures = 0
        self._opened_at = None
        if was_open:
            logger.info("llm_circuit_closed")

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures < self._threshold:
            return

        # Отсчёт окна сдвигаем и когда цепь уже открыта: неудачный пробный вызов
        # обязан закрыть её ещё раз. Иначе _opened_at застывает на первом
        # открытии, окно считается истёкшим навсегда и allow() пропускает всё.

        was_open = self._opened_at is not None
        self._opened_at = time.monotonic()
        if not was_open:
            logger.warning("llm_circuit_opened", failures=self._failures)


class QwenClient(BaseLLMClient):
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            timeout=settings.qwen_timeout,
        )
        self._model = settings.qwen_model
        self._breaker = _CircuitBreaker(_CB_FAIL_THRESHOLD, _CB_RESET_SECONDS)

    async def aclose(self) -> None:
        await self._client.close()

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        if not self._breaker.allow():
            raise RuntimeError("LLM временно недоступен (circuit open)")

        last_error: Exception | None = None
        non_retriable = False

        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                logger.info(
                    "llm_request",
                    model=self._model,
                    messages_count=len(messages),
                    max_tokens=max_tokens,
                    attempt=attempt,
                )

                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    temperature=0.4,
                )

                raw_content = response.choices[0].message.content or ""
                usage = response.usage

                logger.info(
                    "llm_response",
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=usage.completion_tokens if usage else None,
                    raw_len=len(raw_content),
                    raw_sha8=_short_hash(raw_content),
                )

                parsed = self._parse(raw_content)
                self._breaker.on_success()
                return parsed

            except APITimeoutError as e:
                last_error = e
                logger.warning("llm_timeout", attempt=attempt)

            except APIStatusError as e:
                last_error = e
                logger.error("llm_api_error", status_code=e.status_code)
                # 4xx — не ретраим (auth/quota/bad-request)
                if 400 <= e.status_code < 500:
                    non_retriable = True
                    break

            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_DELAY * attempt)

        # 4xx считаем «нашей» проблемой, не сетевой — breaker не трогаем.
        if not non_retriable:
            self._breaker.on_failure()
        raise RuntimeError(
            f"LLM недоступен после {_RETRY_ATTEMPTS} попыток: {last_error}"
        )

    def _parse(self, raw: str) -> LLMResponse:
        try:
            data: dict[str, Any] = json.loads(raw)
            return LLMResponse.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(
                "llm_parse_error",
                raw_len=len(raw),
                raw_sha8=_short_hash(raw),
                error=str(e)[:200],
            )
            raise ValueError(f"Не удалось распарсить ответ LLM: {e}") from e


def _short_hash(text: str) -> str:
    """Короткий SHA1 — для корреляции одинаковых ответов в логах без PII."""
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:8]
