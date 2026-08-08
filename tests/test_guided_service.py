"""Сервисный слой guided-режима.

Проверяем решения сервиса на замоканных зависимостях: какой BotResponse ушёл
в Telegram-слой, дошло ли дело до LLM и с каким state вызван репозиторий.
Сами мутации состояния — в test_session_repo.py.
"""

from typing import Callable

import pytest

from app.core.config import settings
from app.db.models import ActionType, Session as DbSession, SessionMode, ValidationResult
from app.schemas.llm_response import SessionStateUpdate
from app.services.guided_service import TASK_SEPARATOR, GuidedService

from conftest import TELEGRAM_USER_ID


@pytest.fixture
def service(uow, llm) -> GuidedService:
    return GuidedService(uow=uow, llm=llm)


@pytest.fixture
def active(uow, user, make_session) -> Callable[..., DbSession]:
    """Пользователь с активной сессией: фабрика нужной сессии."""

    def _activate(**overrides) -> DbSession:
        session = make_session(**overrides)
        uow.users.get_by_telegram_id.return_value = user
        uow.sessions.get_active_by_user_id.return_value = session
        return session

    return _activate


class TestGuards:
    """Без пользователя или сессии сервис не должен ходить в LLM."""

    async def test_unknown_user_rejected(self, service, llm) -> None:
        result = await service.handle_hint(TELEGRAM_USER_ID)

        assert result.error is True
        llm.complete.assert_not_awaited()

    async def test_user_without_session_rejected(self, service, uow, llm, user) -> None:
        uow.users.get_by_telegram_id.return_value = user

        result = await service.handle_hint(TELEGRAM_USER_ID)

        assert result.error is True
        llm.complete.assert_not_awaited()

    async def test_too_long_input_rejected_before_any_work(self, service, uow, llm) -> None:
        oversized = "а" * (settings.max_user_message_length + 1)

        result = await service.handle_validate_my_idea_message(TELEGRAM_USER_ID, oversized)

        assert result.error is True
        llm.complete.assert_not_awaited()
        uow.users.get_by_telegram_id.assert_not_awaited()


class TestHint:
    async def test_returns_model_text_with_guided_menu(
        self, service, uow, llm, active, make_llm_response
    ) -> None:
        active()
        llm.complete.return_value = make_llm_response(response_text="Подумай про два указателя.")

        result = await service.handle_hint(TELEGRAM_USER_ID)

        assert result.text == "Подумай про два указателя."
        assert result.show_guided_menu is True
        assert result.error is False
        uow.commit.assert_awaited_once()

    async def test_full_solution_mode_gets_its_own_menu(
        self, service, llm, active, make_llm_response
    ) -> None:
        active(current_mode=SessionMode.full_solution)
        llm.complete.return_value = make_llm_response()

        result = await service.handle_hint(TELEGRAM_USER_ID)

        assert result.show_full_solution_menu is True
        assert result.show_guided_menu is False

    async def test_llm_failure_returns_fallback_and_keeps_session(
        self, service, uow, llm, active
    ) -> None:
        active()
        llm.complete.side_effect = RuntimeError("upstream недоступен")

        result = await service.handle_hint(TELEGRAM_USER_ID)

        assert result.error is True
        assert "Попробуй ещё раз" in result.text
        uow.commit.assert_awaited_once()
        uow.sessions.update_after_llm_response.assert_not_awaited()


class TestNextStep:
    async def test_no_plan_warns_without_calling_llm(self, service, llm, active) -> None:
        active(plan_steps=None, total_steps=None)

        result = await service.handle_next_step(TELEGRAM_USER_ID)

        assert "План ещё не сформирован" in result.text
        assert result.show_guided_menu is True
        llm.complete.assert_not_awaited()

    async def test_last_step_closes_plan_without_calling_llm(self, service, llm, active) -> None:
        active(plan_steps=["раз", "два", "три"], total_steps=3, current_step_index=2)

        result = await service.handle_next_step(TELEGRAM_USER_ID)

        assert "Все шаги плана пройдены" in result.text
        assert result.show_end_of_plan_menu is True
        llm.complete.assert_not_awaited()

    async def test_server_drives_the_increment(
        self, service, uow, llm, active, make_llm_response
    ) -> None:
        active(plan_steps=["раз", "два", "три"], total_steps=3, current_step_index=0)
        llm.complete.return_value = make_llm_response(action_type=ActionType.guided_next_step)

        await service.handle_next_step(TELEGRAM_USER_ID)

        kwargs = uow.sessions.update_after_llm_response.await_args.kwargs
        assert kwargs["step_increment"] is True

    async def test_llm_failure_does_not_advance_plan(self, service, uow, llm, active) -> None:
        active(plan_steps=["раз", "два", "три"], total_steps=3, current_step_index=0)
        llm.complete.side_effect = RuntimeError("upstream недоступен")

        result = await service.handle_next_step(TELEGRAM_USER_ID)

        assert result.error is True
        assert result.show_guided_menu is True
        uow.sessions.update_after_llm_response.assert_not_awaited()


async def test_model_cannot_advance_the_plan_itself(
    service, uow, llm, active, make_llm_response
) -> None:
    """Модель просит инкремент шага — сервер обязан это проигнорировать.

    Прогрессом управляет только серверный код (force_step_increment у
    _apply_llm_response). Иначе галлюцинация модели уводит план вперёд, и
    пользователь получает подсказки не к тому шагу.
    """
    active(plan_steps=["раз", "два", "три"], total_steps=3, current_step_index=1)
    llm.complete.return_value = make_llm_response(
        state_update=SessionStateUpdate(step_increment=True),
    )

    await service.handle_hint(TELEGRAM_USER_ID)

    kwargs = uow.sessions.update_after_llm_response.await_args.kwargs
    assert kwargs["step_increment"] is False


class TestValidateIdea:
    async def test_hypothesis_saved_as_attempt(
        self, service, uow, llm, active, make_llm_response
    ) -> None:
        active(awaiting_hypothesis=True)
        llm.complete.return_value = make_llm_response(
            action_type=ActionType.guided_validate_idea,
            validation_result=ValidationResult.partially_correct,
            answer_summary="идея верна наполовину",
        )

        result = await service.handle_validate_my_idea_message(
            TELEGRAM_USER_ID, "Думаю, нужен стек"
        )

        kwargs = uow.attempts.create.await_args.kwargs
        assert kwargs["user_hypothesis"] == "Думаю, нужен стек"
        assert kwargs["validation_result"] is ValidationResult.partially_correct
        assert result.show_guided_menu is True

    async def test_llm_failure_unlocks_free_input(self, service, uow, llm, active) -> None:
        """Флаг ожидания обязан сброситься даже при падении модели.

        Иначе сессия залипает в awaiting_hypothesis: кнопки не работают,
        любой текст снова уходит на валидацию — и снова падает.
        """
        session = active(awaiting_hypothesis=True)
        llm.complete.side_effect = RuntimeError("upstream недоступен")

        result = await service.handle_validate_my_idea_message(TELEGRAM_USER_ID, "гипотеза")

        assert session.awaiting_hypothesis is False
        assert result.error is True
        uow.attempts.create.assert_not_awaited()
        uow.commit.assert_awaited_once()


class TestShareThinking:
    async def test_thinking_is_not_graded(
        self, service, uow, llm, active, make_llm_response
    ) -> None:
        """«Мой контекст» принимает ход мыслей как прогресс, без оценки —
        значит и попытки (attempts) заводить не должен."""
        active(awaiting_hypothesis=True, last_action_type=ActionType.guided_share_thinking)
        llm.complete.return_value = make_llm_response(
            action_type=ActionType.guided_share_thinking
        )

        result = await service.handle_share_thinking_message(TELEGRAM_USER_ID, "я на середине")

        uow.attempts.create.assert_not_awaited()
        uow.sessions.set_last_user_message.assert_awaited_once()
        assert result.show_guided_menu is True


class TestModeSwitch:
    async def test_to_guided_skips_llm(self, service, uow, llm, active) -> None:
        active(current_mode=SessionMode.full_solution)

        result = await service.handle_switch_to_guided_mode(TELEGRAM_USER_ID)

        assert result.show_guided_menu is True
        llm.complete.assert_not_awaited()
        uow.sessions.switch_mode.assert_awaited_once()

    async def test_full_solution_closes_session_and_uses_bigger_budget(
        self, service, uow, llm, active, make_llm_response
    ) -> None:
        session = active()

        # switch_mode замокан и сам объект не меняет, а _call_llm выбирает
        # лимит токенов именно по session.current_mode — воспроизводим мутацию,
        # иначе тест проверял бы бюджет guided-режима.
        async def _switch(sess: DbSession, mode: SessionMode) -> DbSession:
            sess.current_mode = mode
            return sess

        uow.sessions.switch_mode.side_effect = _switch
        llm.complete.return_value = make_llm_response(
            action_type=ActionType.full_solution,
            response_text="Вот решение",
        )

        result = await service.handle_switch_to_full_solution_mode(TELEGRAM_USER_ID)

        assert session.current_mode is SessionMode.full_solution
        assert llm.complete.await_args.args[1] == settings.full_solution_max_tokens
        assert result.text.startswith("Вот решение")
        assert "задача решена" in result.text
        assert result.show_start_menu is True
        uow.sessions.deactivate_user_sessions.assert_awaited_once()


class TestSessionLifecycle:
    async def test_exit_closes_active_session(self, service, uow, active) -> None:
        active()

        result = await service.handle_exit(TELEGRAM_USER_ID)

        assert TASK_SEPARATOR in result.text
        assert result.show_start_menu is True
        uow.sessions.deactivate_user_sessions.assert_awaited_once()
        assert uow.users.set_awaiting_task.await_args.args[1] is False

    async def test_exit_without_session_is_noop(self, service, uow, user) -> None:
        uow.users.get_by_telegram_id.return_value = user

        result = await service.handle_exit(TELEGRAM_USER_ID)

        assert TASK_SEPARATOR not in result.text
        assert "Активного диалога нет" in result.text
        uow.sessions.deactivate_user_sessions.assert_not_awaited()

    async def test_describe_task_resets_previous_session(
        self, service, uow, user, make_session
    ) -> None:
        uow.users.upsert.return_value = user
        uow.sessions.get_active_by_user_id.return_value = make_session()

        result = await service.handle_describe_task(TELEGRAM_USER_ID)

        assert TASK_SEPARATOR in result.text
        uow.sessions.deactivate_user_sessions.assert_awaited_once()
        assert uow.users.set_awaiting_task.await_args.args[1] is True

    async def test_describe_task_without_previous_session_has_no_separator(
        self, service, uow, user
    ) -> None:
        uow.users.upsert.return_value = user

        result = await service.handle_describe_task(TELEGRAM_USER_ID)

        assert TASK_SEPARATOR not in result.text
        uow.sessions.deactivate_user_sessions.assert_not_awaited()
