import json
import asyncio
from typing import Any

from openai import AsyncOpenAI, APITimeoutError, APIStatusError
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.adapter import BaseLLMClient
from app.schemas.llm_response import LLMResponse

logger = get_logger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_DELAY = 2.0


class QwenClient(BaseLLMClient):
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
            timeout=settings.qwen_timeout,
        )
        self._model = settings.qwen_model

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        last_error: Exception | None = None

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
                )

                return self._parse(raw_content)

            except APITimeoutError as e:
                last_error = e
                logger.warning("llm_timeout", attempt=attempt)

            except APIStatusError as e:
                last_error = e
                logger.error("llm_api_error", status_code=e.status_code, message=str(e))
                # 4xx — не ретраим
                if 400 <= e.status_code < 500:
                    break

            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_RETRY_DELAY * attempt)

        raise RuntimeError(
            f"LLM недоступен после {_RETRY_ATTEMPTS} попыток: {last_error}"
        )

    def _parse(self, raw: str) -> LLMResponse:
        try:
            data: dict[str, Any] = json.loads(raw)
            return LLMResponse.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error("llm_parse_error", raw=raw[:500], error=str(e))
            raise ValueError(f"Не удалось распарсить ответ LLM: {e}") from e
