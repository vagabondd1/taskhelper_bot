"""Контракт ответа LLM.

Фиксирует границу между промптом (что модель обязана вернуть) и кодом (что он
готов принять). Ломается, если формат ответа в system.py разъедется со схемой —
раньше, чем это долетит до пользователя.
"""

import pytest
from pydantic import ValidationError

from app.db.models import ActionType, SessionMode, ValidationResult
from app.llm.qwen_client import QwenClient
from app.schemas.llm_response import LLMResponse

_MINIMAL = {
    "response_text": "Подумай, что произойдёт с указателем на предыдущий узел.",
    "action_type": "guided_hint",
    "answer_summary": "намёк про предыдущий узел",
}


def test_minimal_payload_parses_with_defaults() -> None:
    resp = LLMResponse.model_validate(_MINIMAL)

    assert resp.action_type is ActionType.guided_hint
    assert resp.confidence == 1.0
    assert resp.is_off_topic is False
    assert resp.validation_result is None
    # state_update отсутствует в payload — должен подставиться пустой объект,
    # иначе _apply_llm_response упадёт на обращении к llm_response.state_update
    assert resp.state_update.plan_steps is None
    assert resp.state_update.step_increment is False
    assert resp.state_update.awaiting_hypothesis is False


def test_full_payload_parses() -> None:
    resp = LLMResponse.model_validate({
        **_MINIMAL,
        "action_type": "new_task",
        "state_update": {
            "task_summary": "Развернуть список",
            "progress_summary": "Не начато. Шаг 0 / 4",
            "step_increment": False,
            "awaiting_hypothesis": True,
            "switch_mode": "full_solution",
            "plan_steps": ["Разобрать вход", "Развернуть", "Вывести"],
        },
        "validation_result": "partially_correct",
        "confidence": 0.75,
        "is_off_topic": True,
    })

    assert resp.action_type is ActionType.new_task
    assert resp.state_update.switch_mode is SessionMode.full_solution
    assert resp.state_update.plan_steps == ["Разобрать вход", "Развернуть", "Вывести"]
    assert resp.validation_result is ValidationResult.partially_correct
    assert resp.is_off_topic is True


@pytest.mark.parametrize("field", ["response_text", "action_type", "answer_summary"])
def test_missing_required_field_rejected(field) -> None:
    payload = {k: v for k, v in _MINIMAL.items() if k != field}
    with pytest.raises(ValidationError):
        LLMResponse.model_validate(payload)


def test_unknown_action_type_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMResponse.model_validate({**_MINIMAL, "action_type": "guided_teleport"})


def test_unknown_validation_result_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMResponse.model_validate({**_MINIMAL, "validation_result": "maybe"})


def test_unknown_switch_mode_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMResponse.model_validate({
            **_MINIMAL,
            "state_update": {"switch_mode": "turbo"},
        })


@pytest.mark.parametrize("value", [-0.1, 1.5])
def test_confidence_out_of_range_rejected(value) -> None:
    with pytest.raises(ValidationError):
        LLMResponse.model_validate({**_MINIMAL, "confidence": value})


def test_switch_mode_compares_as_plain_string() -> None:
    """_apply_llm_response сравнивает switch_mode со строкой ("guided").

    Работает только потому, что SessionMode — str-enum. Тест сторожит это:
    если enum перестанет наследовать str, сравнение станет молча ложным и
    переключение режима отвалится без единой ошибки.
    """
    resp = LLMResponse.model_validate({**_MINIMAL, "state_update": {"switch_mode": "guided"}})

    assert resp.state_update.switch_mode == "guided"


class TestRawParsing:
    """Разбор сырого ответа модели — то, что реально приходит из API."""

    @pytest.fixture(scope="class")
    def client(self) -> QwenClient:
        # Конструктор только собирает httpx-клиент, наружу не ходит.
        return QwenClient()

    def test_valid_json_string_parsed(self, client) -> None:
        raw = (
            '{"response_text": "Привет", "action_type": "new_task",'
            ' "answer_summary": "приветствие"}'
        )
        assert client._parse(raw).action_type is ActionType.new_task

    @pytest.mark.parametrize("raw", [
        "",
        "не json вовсе",
        "```json\n{\"response_text\": \"x\"}\n```",   # модель обернула в markdown
        '{"response_text": "x"}',                      # валидный json, невалидная схема
    ])
    def test_broken_response_raises_value_error(self, client, raw) -> None:
        """Любой мусор от модели превращается в ValueError, а не в падение.

        Сервисный слой ловит его и отдаёт пользователю понятный fallback.
        """
        with pytest.raises(ValueError):
            client._parse(raw)
