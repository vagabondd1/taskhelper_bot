import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class SessionMode(str, enum.Enum):
    guided = "guided"
    full_solution = "full_solution"


class SessionStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    paused = "paused"


class ActionType(str, enum.Enum):
    guided_hint = "guided_hint"
    guided_next_step = "guided_next_step"
    guided_validate_idea = "guided_validate_idea"
    guided_explain = "guided_explain"
    guided_code_hint = "guided_code_hint"
    guided_recheck = "guided_recheck"
    full_solution = "full_solution"
    new_task = "new_task"
    mode_switch = "mode_switch"


class ValidationResult(str, enum.Enum):
    correct = "correct"
    partially_correct = "partially_correct"
    incorrect = "incorrect"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sessions: Mapped[list["Session"]] = relationship("Session", back_populates="user", lazy="select")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="user", lazy="select")


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    current_task_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    current_mode: Mapped[SessionMode] = mapped_column(
        Enum(SessionMode), nullable=False, default=SessionMode.guided
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus), nullable=False, default=SessionStatus.active
    )

    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_progress_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    last_action_type: Mapped[Optional[ActionType]] = mapped_column(Enum(ActionType), nullable=True)
    last_assistant_message_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("messages.id"), nullable=True
    )
    last_assistant_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_user_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Флаг ожидания гипотезы пользователя после validate_my_idea
    awaiting_hypothesis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session", foreign_keys="Message.session_id", lazy="select"
    )
    attempts: Mapped[list["Attempt"]] = relationship("Attempt", back_populates="session", lazy="select")
    last_assistant_message: Mapped[Optional["Message"]] = relationship(
        "Message", foreign_keys=[last_assistant_message_id]
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)

    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[Optional[ActionType]] = mapped_column(Enum(ActionType), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="messages")
    session: Mapped["Session"] = relationship(
        "Session", back_populates="messages", foreign_keys=[session_id]
    )


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)

    user_hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    user_hypothesis_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_result: Mapped[Optional[ValidationResult]] = mapped_column(
        Enum(ValidationResult), nullable=True
    )
    llm_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped["Session"] = relationship("Session", back_populates="attempts")


class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("sessions.id"), nullable=True, index=True)

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
