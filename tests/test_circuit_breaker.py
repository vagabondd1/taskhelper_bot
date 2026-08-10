"""Предохранитель перед LLM.

Нужен ради одного сценария: upstream лёг надолго. Без него каждый клик уходит
в три полных ретрая по таймауту и всё это время держит advisory-lock
пользователя. Поэтому проверяем не столько само открытие цепи, сколько её
повторное открытие после неудачного пробного вызова — на затяжной аварии
успешных вызовов не будет, и цепь обязана закрываться сама.
"""

import pytest

import app.llm.qwen_client as qwen_client
from app.llm.qwen_client import _CircuitBreaker

THRESHOLD = 3
RESET_SECONDS = 30.0


@pytest.fixture
def clock(monkeypatch):
    """Ручные часы вместо monotonic — иначе тест ждал бы окно реальным sleep.

    Подменяем модуль time только внутри qwen_client, глобальный не трогаем.
    """

    class FakeTime:
        def __init__(self) -> None:
            self.now = 1000.0

        def monotonic(self) -> float:
            return self.now

        def tick(self, seconds: float) -> None:
            self.now += seconds

    fake = FakeTime()
    monkeypatch.setattr(qwen_client, "time", fake)
    return fake


@pytest.fixture
def breaker(clock) -> _CircuitBreaker:
    return _CircuitBreaker(THRESHOLD, RESET_SECONDS)


def _break_it(breaker: _CircuitBreaker) -> None:
    for _ in range(THRESHOLD):
        breaker.on_failure()


def test_closed_below_threshold(breaker) -> None:
    for _ in range(THRESHOLD - 1):
        breaker.on_failure()

    assert breaker.allow() is True


def test_opens_on_threshold(breaker) -> None:
    _break_it(breaker)

    assert breaker.allow() is False


def test_stays_open_inside_window(breaker, clock) -> None:
    _break_it(breaker)
    clock.tick(RESET_SECONDS - 0.1)

    assert breaker.allow() is False


def test_probe_allowed_after_window(breaker, clock) -> None:
    _break_it(breaker)
    clock.tick(RESET_SECONDS)

    assert breaker.allow() is True


def test_failed_probe_reopens_circuit(breaker, clock) -> None:
    """Главный сценарий: upstream не поднялся, пробный вызов упал.

    Цепь обязана закрыться ещё на одно окно. Если отсчёт не сдвинуть, allow()
    начнёт пропускать всё подряд и предохранителя фактически не станет.
    """
    _break_it(breaker)
    clock.tick(RESET_SECONDS)
    breaker.allow()

    breaker.on_failure()

    assert breaker.allow() is False


def test_stays_shut_while_upstream_is_down(breaker, clock) -> None:
    """Час аварии без единого успеха — пробный вызов раз в окно, не больше."""
    _break_it(breaker)
    probes = 0

    for _ in range(120):
        clock.tick(RESET_SECONDS / 2)
        if breaker.allow():
            probes += 1
            breaker.on_failure()

    assert probes == 60


def test_successful_probe_closes_circuit(breaker, clock) -> None:
    _break_it(breaker)
    clock.tick(RESET_SECONDS)

    breaker.on_success()

    assert breaker.allow() is True


def test_success_resets_failure_count(breaker) -> None:
    """Счётчик именно «подряд»: одиночные отказы не должны копиться до порога."""
    for _ in range(THRESHOLD - 1):
        breaker.on_failure()
    breaker.on_success()

    for _ in range(THRESHOLD - 1):
        breaker.on_failure()

    assert breaker.allow() is True
