"""Общие фикстуры.

Тесты гоняются без БД, Redis и сети: сервисный слой изолирован моками
UnitOfWork и BaseLLMClient, rate limiter работает поверх fakeredis.
"""

import os

# app.core.config.settings — module-level singleton: инстанцируется на импорте
# любого app.*-модуля и падает без обязательных переменных. Подставляем
# заглушки ДО первого импорта app.* — реальные креды тестам не нужны.
os.environ["TELEGRAM_BOT_TOKEN"] = "test-token"
os.environ["QWEN_API_KEY"] = "test-key"
os.environ["POSTGRES_PASSWORD"] = "test-password"

from typing import Callable
from unittest.mock import AsyncMock

import pytest

from app.db.models import (
    ActionType,
    Message,
    Session as DbSession,
    SessionMode,
    SessionStatus,
    User,
)
from app.db.repositories.attempt_repo import AttemptRepository
from app.db.repositories.event_log_repo import EventLogRepository
from app.db.repositories.message_repo import MessageRepository
from app.db.repositories.session_repo import SessionRepository
from app.db.repositories.user_repo import UserRepository
from app.llm.adapter import BaseLLMClient
from app.schemas.llm_response import LLMResponse, SessionStateUpdate

TELEGRAM_USER_ID = 424242
USER_ID = 1
SESSION_ID = 10
ASSISTANT_MESSAGE_ID = 777


@pytest.fixture
def user() -> User:
    return User(id=USER_ID, telegram_user_id=TELEGRAM_USER_ID)


@pytest.fixture
def make_session() -> Callable[..., DbSession]:
    """Фабрика сессий БД.

    Поля с дефолтом на уровне модели (awaiting_hypothesis, current_step_index)
    задаём явно: объект не проходит через flush, поэтому default/server_default
    не применяются и остались бы None — а SessionContext валидирует их как
    bool/int и упал бы на ValidationError.
    """

    def _make(**overrides) -> DbSession:
        fields = {
            "id": SESSION_ID,
            "user_id": USER_ID,
            "current_task_text": "Развернуть односвязный список",
            "task_summary": "Развернуть односвязный список за O(n) без доп. памяти.",
            "current_mode": SessionMode.guided,
            "status": SessionStatus.active,
            "current_step_index": 0,
            "awaiting_hypothesis": False,
        }
        fields.update(overrides)
        return DbSession(**fields)

    return _make


@pytest.fixture
def make_llm_response() -> Callable[..., LLMResponse]:
    def _make(**overrides) -> LLMResponse:
        fields = {
            "response_text": "Ответ модели",
            "action_type": ActionType.guided_hint,
            "answer_summary": "краткое содержание ответа",
            "state_update": SessionStateUpdate(),
        }
        fields.update(overrides)
        return LLMResponse(**fields)

    return _make


@pytest.fixture
def uow() -> AsyncMock:
    """UnitOfWork с замоканными репозиториями.

    spec на каждом репозитории — не косметика: без него мок молча проглотит
    вызов метода, который в коде переименовали или удалили, и тест продолжит
    «проходить» на несуществующем API. Со spec такой вызов падает сразу.
    """
    mock = AsyncMock()
    mock.users = AsyncMock(spec=UserRepository)
    mock.sessions = AsyncMock(spec=SessionRepository)
    mock.messages = AsyncMock(spec=MessageRepository)
    mock.attempts = AsyncMock(spec=AttemptRepository)
    mock.events = AsyncMock(spec=EventLogRepository)

    # Дефолт «ничего нет»: иначе AsyncMock вернёт мок-объект и проверки вида
    # `if not user` / `is not None` уйдут не в ту ветку.
    mock.users.get_by_telegram_id.return_value = None
    mock.sessions.get_active_by_user_id.return_value = None
    mock.messages.create.return_value = Message(id=ASSISTANT_MESSAGE_ID)
    return mock


@pytest.fixture
def llm() -> AsyncMock:
    return AsyncMock(spec=BaseLLMClient)
