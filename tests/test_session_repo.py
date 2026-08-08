"""Точечные тесты репозитория сессий.

Сервисные тесты проверяют, что сервис ПОПРОСИЛ сделать нужное (моки UoW).
Здесь — что запрошенное реально применяется к объекту сессии. Это ровно тот
слой, который моком UnitOfWork не покрывается: там настоящий код репозитория
не выполняется вообще.

AsyncSession замокан — flush() никуда не летит, проверяем мутацию объекта.
"""

from unittest.mock import AsyncMock

import pytest

from app.db.models import ActionType, Session as DbSession, SessionMode
from app.db.repositories.session_repo import SessionRepository


@pytest.fixture
def repo() -> SessionRepository:
    return SessionRepository(session=AsyncMock())


async def _update(repo: SessionRepository, session: DbSession, **overrides) -> DbSession:
    kwargs = {
        "session": session,
        "action_type": ActionType.guided_hint,
        "assistant_message_id": 1,
        "assistant_summary": "краткое содержание",
    }
    kwargs.update(overrides)
    return await repo.update_after_llm_response(**kwargs)


class TestStepIncrement:
    """Прогресс по плану двигает только сервер — это ключевой инвариант бота."""

    async def test_increment_applied_when_requested(self, repo, make_session) -> None:
        session = make_session(current_step_index=2)

        await _update(repo, session, step_increment=True)

        assert session.current_step_index == 3

    async def test_step_untouched_by_default(self, repo, make_session) -> None:
        session = make_session(current_step_index=2)

        await _update(repo, session)

        assert session.current_step_index == 2


class TestAwaitingHypothesis:
    """Флаг ожидания ввода: залипший true запирает пользователя в свободном вводе."""

    async def test_switch_mode_resets_flag(self, repo, make_session) -> None:
        session = make_session(current_mode=SessionMode.guided, awaiting_hypothesis=True)

        await repo.switch_mode(session, SessionMode.full_solution)

        assert session.current_mode is SessionMode.full_solution
        assert session.awaiting_hypothesis is False

    async def test_update_overwrites_flag(self, repo, make_session) -> None:
        session = make_session(awaiting_hypothesis=True)

        await _update(repo, session, awaiting_hypothesis=False)

        assert session.awaiting_hypothesis is False


class TestProgressSummary:
    async def test_none_keeps_previous_value(self, repo, make_session) -> None:
        """LLM не прислала progress_summary — старый прогресс не затираем."""
        session = make_session(current_progress_summary="Шаг 2 / 5 сделан")

        await _update(repo, session, progress_summary=None)

        assert session.current_progress_summary == "Шаг 2 / 5 сделан"

    async def test_new_value_replaces(self, repo, make_session) -> None:
        session = make_session(current_progress_summary="Шаг 2 / 5 сделан")

        await _update(repo, session, progress_summary="Шаг 3 / 5 сделан")

        assert session.current_progress_summary == "Шаг 3 / 5 сделан"


async def test_last_assistant_fields_written(repo, make_session) -> None:
    """last_* поля кормят следующий промпт — без них модель теряет контекст."""
    session = make_session()

    await _update(
        repo,
        session,
        action_type=ActionType.guided_code_hint,
        assistant_message_id=99,
        assistant_summary="дал сниппет на 5 строк",
    )

    assert session.last_action_type is ActionType.guided_code_hint
    assert session.last_assistant_message_id == 99
    assert session.last_assistant_summary == "дал сниппет на 5 строк"
