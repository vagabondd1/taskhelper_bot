"""Санитайзер плана решения.

Последняя точка обороны перед БД: SYSTEM_PROMPT просит у модели 3–7 шагов, но
это «надо», а не гарантия. Мусорный план ломает UI прогресса и счётчик шагов.
"""

from unittest.mock import AsyncMock

import pytest

from app.db.repositories.session_repo import (
    _PLAN_MAX_STEPS,
    _PLAN_MIN_STEPS,
    _PLAN_STEP_MAX_LEN,
    SessionRepository,
    _sanitize_plan_steps,
)


def _steps(n: int) -> list[str]:
    return [f"Шаг номер {i}" for i in range(n)]


@pytest.mark.parametrize("raw", [None, [], _steps(_PLAN_MIN_STEPS - 1)])
def test_unusable_plan_rejected(raw) -> None:
    """Меньше минимума — плана нет. None здесь значит «не перезаписывать»."""
    assert _sanitize_plan_steps(raw) is None


def test_minimum_accepted() -> None:
    assert len(_sanitize_plan_steps(_steps(_PLAN_MIN_STEPS))) == _PLAN_MIN_STEPS


def test_tail_cut_to_max() -> None:
    cleaned = _sanitize_plan_steps(_steps(_PLAN_MAX_STEPS + 5))

    assert len(cleaned) == _PLAN_MAX_STEPS
    assert cleaned[0] == "Шаг номер 0"


def test_duplicates_dropped_case_insensitively() -> None:
    cleaned = _sanitize_plan_steps([
        "Разобрать вход",
        "разобрать ВХОД",
        "Построить граф",
        "Запустить обход",
    ])

    assert cleaned == ["Разобрать вход", "Построить граф", "Запустить обход"]


def test_whitespace_collapsed() -> None:
    """Многоабзацный шаг схлопывается в одну строку — иначе ломает вёрстку меню."""
    cleaned = _sanitize_plan_steps([
        "  Разобрать\n\n  вход  ",
        "Построить\tграф",
        "Запустить обход",
    ])

    assert cleaned == ["Разобрать вход", "Построить граф", "Запустить обход"]


def test_long_step_truncated_with_ellipsis() -> None:
    cleaned = _sanitize_plan_steps(["А" * 500, "Построить граф", "Запустить обход"])

    assert len(cleaned[0]) == _PLAN_STEP_MAX_LEN
    assert cleaned[0].endswith("…")


def test_empty_and_non_string_items_filtered() -> None:
    cleaned = _sanitize_plan_steps([
        "Разобрать вход", "", "   ", None, 42, {"step": "x"},
        "Построить граф", "Запустить обход",
    ])

    assert cleaned == ["Разобрать вход", "Построить граф", "Запустить обход"]


def test_dedup_can_drop_plan_below_minimum() -> None:
    """Дубли режутся до санитарного минимума, а не после — иначе в БД уедет план
    из одного шага."""
    assert _sanitize_plan_steps(["Один и тот же шаг"] * 6) is None


class TestSetPlan:
    """set_plan поверх санитайзера — что реально доезжает до объекта сессии."""

    @pytest.fixture
    def repo(self) -> SessionRepository:
        return SessionRepository(session=AsyncMock())

    async def test_good_plan_written_with_total(self, repo, make_session) -> None:
        session = make_session()

        await repo.set_plan(session, _steps(4))

        assert session.plan_steps == _steps(4)
        assert session.total_steps == 4

    async def test_garbage_plan_keeps_previous(self, repo, make_session) -> None:
        """Лучше старый план, чем мусорный: счётчик шагов уже завязан на него."""
        session = make_session(plan_steps=_steps(4), total_steps=4)

        await repo.set_plan(session, ["всего один шаг"])

        assert session.plan_steps == _steps(4)
        assert session.total_steps == 4
