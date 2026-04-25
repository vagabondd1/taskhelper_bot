from typing import Optional
from pydantic import BaseModel
from app.db.models import ActionType, Session, SessionMode

# Символьные лимиты полей промпта — для справки и документации.
# Пользовательский ввод отклоняется ДО попадания сюда (см. core/utils.py).
# Эти константы используются в prompt_builder для обрезки LLM-генерированных
# summary (task_summary, progress_summary), которые тоже могут быть длинными.
TASK_SUMMARY_MAX_CHARS = 1500
PROGRESS_SUMMARY_MAX_CHARS = 900
LAST_ASSISTANT_SUMMARY_MAX_CHARS = 600
LAST_USER_MESSAGE_MAX_CHARS = 1200


def _trim(value: Optional[str], max_chars: int) -> Optional[str]:
    """Обрезает LLM-генерированные строки, которые превысили ожидаемый размер."""
    if value is None or len(value) <= max_chars:
        return value
    return value[:max_chars - 3] + "..."


class SessionContext(BaseModel):
    """Минимальный контекст, который уходит в LLM-промпт.

    Суммарный бюджет ~1750 токенов на контекст сессии.
    Полный диалог в промпт не отправляется.
    """

    task_summary: str
    current_mode: SessionMode
    current_step_index: int
    current_progress_summary: Optional[str] = None
    last_action_type: Optional[ActionType] = None
    last_assistant_summary: Optional[str] = None
    last_user_message: Optional[str] = None
    awaiting_hypothesis: bool = False
    plan_steps: Optional[list[str]] = None
    total_steps: Optional[int] = None

    @property
    def current_step_title(self) -> Optional[str]:
        if not self.plan_steps:
            return None
        idx = self.current_step_index
        if 0 <= idx < len(self.plan_steps):
            return self.plan_steps[idx]
        return None

    @property
    def next_step_title(self) -> Optional[str]:
        if not self.plan_steps:
            return None
        idx = self.current_step_index + 1
        if 0 <= idx < len(self.plan_steps):
            return self.plan_steps[idx]
        return None

    @classmethod
    def from_db_session(cls, session: Session) -> "SessionContext":
        return cls(
            task_summary=_trim(
                session.task_summary or session.current_task_text or "",
                TASK_SUMMARY_MAX_CHARS,
            ),
            current_mode=session.current_mode,
            current_step_index=session.current_step_index,
            current_progress_summary=_trim(
                session.current_progress_summary, PROGRESS_SUMMARY_MAX_CHARS
            ),
            last_action_type=session.last_action_type,
            last_assistant_summary=_trim(
                session.last_assistant_summary, LAST_ASSISTANT_SUMMARY_MAX_CHARS
            ),
            last_user_message=_trim(
                session.last_user_message, LAST_USER_MESSAGE_MAX_CHARS
            ),
            awaiting_hypothesis=session.awaiting_hypothesis,
            plan_steps=session.plan_steps,
            total_steps=session.total_steps,
        )
