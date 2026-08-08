"""Сервис новой задачи: cooldown, topic guardrail, обработка сбоев."""

from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.db.models import ActionType
from app.schemas.llm_response import LLMResponse, SessionStateUpdate
from app.services import task_service as task_service_module
from app.services.guided_service import TASK_SEPARATOR
from app.services.task_service import TaskService

from conftest import TELEGRAM_USER_ID

_TASK = "Написать функцию, которая разворачивает односвязный список"


@pytest.fixture
def redis(monkeypatch) -> AsyncMock:
    """Redis для cooldown. По умолчанию слот свободен (SET NX прошёл)."""
    fake = AsyncMock()
    fake.set.return_value = True
    monkeypatch.setattr(task_service_module, "redis_client", fake)
    return fake


@pytest.fixture
def service(uow, llm, user, redis, make_session) -> TaskService:
    uow.users.upsert.return_value = user
    uow.sessions.create.return_value = make_session()
    return TaskService(uow=uow, llm=llm)


@pytest.fixture
def new_task_response(make_llm_response) -> LLMResponse:
    return make_llm_response(
        action_type=ActionType.new_task,
        response_text="Привет! Задачу понял. Как двигаемся?",
        state_update=SessionStateUpdate(
            task_summary="Развернуть односвязный список",
            plan_steps=["Разобрать вход", "Развернуть", "Вывести"],
        ),
    )


class TestCooldown:
    async def test_active_cooldown_blocks_before_any_work(self, service, uow, llm, redis) -> None:
        redis.set.return_value = None  # SET NX не прошёл — ключ уже есть
        redis.ttl.return_value = 7

        result = await service.handle_new_task(TELEGRAM_USER_ID, _TASK)

        assert result.error is True
        assert "7" in result.text
        llm.complete.assert_not_awaited()
        uow.users.upsert.assert_not_awaited()
        uow.sessions.create.assert_not_awaited()

    async def test_redis_outage_is_fail_open(self, service, llm, redis, new_task_response) -> None:
        """Redis лёг — пользователь не должен остаться без бота.

        Cooldown просто пропускается, задача обрабатывается как обычно.
        """
        redis.set.side_effect = ConnectionError("redis недоступен")
        llm.complete.return_value = new_task_response

        result = await service.handle_new_task(TELEGRAM_USER_ID, _TASK)

        assert result.error is False
        llm.complete.assert_awaited_once()

    async def test_cooldown_slot_taken_with_configured_ttl(
        self, service, redis, llm, new_task_response
    ) -> None:
        llm.complete.return_value = new_task_response

        await service.handle_new_task(TELEGRAM_USER_ID, _TASK)

        kwargs = redis.set.await_args.kwargs
        assert kwargs["nx"] is True
        assert kwargs["ex"] == settings.new_task_cooldown_seconds


class TestHappyPath:
    async def test_offers_mode_selector(self, service, uow, llm, new_task_response) -> None:
        llm.complete.return_value = new_task_response

        result = await service.handle_new_task(TELEGRAM_USER_ID, _TASK)

        assert result.text == "Привет! Задачу понял. Как двигаемся?"
        assert result.show_mode_selector is True
        assert result.error is False
        uow.users.set_awaiting_task.assert_awaited_once()
        uow.commit.assert_awaited_once()

    async def test_plan_from_model_reaches_repository(
        self, service, uow, llm, new_task_response
    ) -> None:
        llm.complete.return_value = new_task_response

        await service.handle_new_task(TELEGRAM_USER_ID, _TASK)

        args = uow.sessions.set_plan.await_args.args
        assert args[1] == ["Разобрать вход", "Развернуть", "Вывести"]

    async def test_task_summary_from_model_reaches_repository(
        self, service, uow, llm, new_task_response
    ) -> None:
        """task_summary подставляется в КАЖДЫЙ последующий промпт как условие
        задачи (полный текст в модель больше не уходит). Не сохранился —
        дальше модель работает вслепую."""
        llm.complete.return_value = new_task_response

        await service.handle_new_task(TELEGRAM_USER_ID, _TASK)

        args = uow.sessions.set_task_summary.await_args.args
        assert args[1] == "Развернуть односвязный список"

    async def test_previous_session_marked_with_separator(
        self, service, uow, llm, make_session, new_task_response
    ) -> None:
        uow.sessions.get_active_by_user_id.return_value = make_session()
        llm.complete.return_value = new_task_response

        result = await service.handle_new_task(TELEGRAM_USER_ID, _TASK)

        assert result.text.startswith(TASK_SEPARATOR)
        uow.sessions.deactivate_user_sessions.assert_awaited()


class TestGuardrails:
    async def test_off_topic_closes_session_immediately(
        self, service, uow, llm, make_llm_response
    ) -> None:
        """Не-программистский запрос не должен оставлять активную сессию —
        иначе пользователь попадает в guided-режим по пустой задаче."""
        llm.complete.return_value = make_llm_response(
            action_type=ActionType.new_task,
            response_text="Я отвечаю только на вопросы по программированию.",
            is_off_topic=True,
        )

        result = await service.handle_new_task(TELEGRAM_USER_ID, "как пожарить картошку")

        assert result.show_start_menu is True
        assert result.show_mode_selector is False
        uow.sessions.deactivate_user_sessions.assert_awaited()

    async def test_too_long_task_rejected_before_cooldown(self, service, llm, redis) -> None:
        """Проверка длины идёт до Redis — иначе слишком длинный текст
        сжигал бы cooldown-слот."""
        oversized = "а" * (settings.max_user_message_length + 1)

        result = await service.handle_new_task(TELEGRAM_USER_ID, oversized)

        assert result.error is True
        redis.set.assert_not_awaited()
        llm.complete.assert_not_awaited()

    async def test_llm_failure_reports_error(self, service, uow, llm) -> None:
        llm.complete.side_effect = RuntimeError("upstream недоступен")

        result = await service.handle_new_task(TELEGRAM_USER_ID, _TASK)

        assert result.error is True
        assert "Не удалось обработать задачу" in result.text
        uow.commit.assert_awaited_once()
