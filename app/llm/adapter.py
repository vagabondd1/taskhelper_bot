from abc import ABC, abstractmethod
from app.schemas.llm_response import LLMResponse


class BaseLLMClient(ABC):
    """Абстракция LLM-провайдера. Замена провайдера = новый класс, не правка логики."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        max_tokens: int,
    ) -> LLMResponse:
        """Отправляет сообщения в модель, возвращает распарсенный LLMResponse."""
        ...
