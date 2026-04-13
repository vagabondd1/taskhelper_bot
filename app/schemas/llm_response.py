from typing import Any, Optional
from pydantic import BaseModel, Field
from app.db.models import ActionType, SessionMode, ValidationResult


class SessionStateUpdate(BaseModel):
    task_summary: Optional[str] = None
    progress_summary: Optional[str] = None
    step_increment: bool = False
    awaiting_hypothesis: bool = False
    switch_mode: Optional[SessionMode] = None


class LLMResponse(BaseModel):
    response_text: str
    action_type: ActionType
    answer_summary: str = Field(
        description="Краткое machine-friendly summary ответа для хранения в сессии"
    )
    state_update: SessionStateUpdate = Field(default_factory=SessionStateUpdate)
    validation_result: Optional[ValidationResult] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
