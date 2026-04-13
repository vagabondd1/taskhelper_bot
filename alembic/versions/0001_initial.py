"""initial

Revision ID: 0001
Revises:
Create Date: 2026-04-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_index("ix_users_telegram_user_id", "users", ["telegram_user_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("current_task_text", sa.Text(), nullable=True),
        sa.Column("task_summary", sa.Text(), nullable=True),
        sa.Column("current_mode", sa.Enum("guided", "full_solution", name="sessionmode"), nullable=False),
        sa.Column("status", sa.Enum("active", "completed", "paused", name="sessionstatus"), nullable=False),
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_progress_summary", sa.Text(), nullable=True),
        sa.Column(
            "last_action_type",
            sa.Enum(
                "guided_hint", "guided_next_step", "guided_validate_idea",
                "guided_explain", "guided_code_hint", "guided_recheck",
                "full_solution", "new_task", "mode_switch",
                name="actiontype",
            ),
            nullable=True,
        ),
        sa.Column("last_assistant_message_id", sa.Integer(), nullable=True),
        sa.Column("last_assistant_summary", sa.Text(), nullable=True),
        sa.Column("last_user_message", sa.Text(), nullable=True),
        sa.Column("awaiting_hypothesis", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.Enum("user", "assistant", "system", name="messagerole"), nullable=False),
        sa.Column("message_text", sa.Text(), nullable=False),
        sa.Column(
            "message_type",
            sa.Enum(
                "guided_hint", "guided_next_step", "guided_validate_idea",
                "guided_explain", "guided_code_hint", "guided_recheck",
                "full_solution", "new_task", "mode_switch",
                name="actiontype",
            ),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_user_id", "messages", ["user_id"])
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    # FK last_assistant_message_id добавляем после создания messages
    op.create_foreign_key(
        "fk_sessions_last_assistant_message_id",
        "sessions", "messages",
        ["last_assistant_message_id"], ["id"],
    )

    op.create_table(
        "attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("user_hypothesis", sa.Text(), nullable=False),
        sa.Column("user_hypothesis_summary", sa.Text(), nullable=True),
        sa.Column(
            "validation_result",
            sa.Enum("correct", "partially_correct", "incorrect", name="validationresult"),
            nullable=True,
        ),
        sa.Column("llm_feedback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attempts_user_id", "attempts", ["user_id"])
    op.create_index("ix_attempts_session_id", "attempts", ["session_id"])

    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_logs_user_id", "event_logs", ["user_id"])
    op.create_index("ix_event_logs_session_id", "event_logs", ["session_id"])
    op.create_index("ix_event_logs_event_type", "event_logs", ["event_type"])


def downgrade() -> None:
    op.drop_table("event_logs")
    op.drop_table("attempts")
    op.drop_constraint("fk_sessions_last_assistant_message_id", "sessions", type_="foreignkey")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS validationresult")
    op.execute("DROP TYPE IF EXISTS actiontype")
    op.execute("DROP TYPE IF EXISTS messagerole")
    op.execute("DROP TYPE IF EXISTS sessionstatus")
    op.execute("DROP TYPE IF EXISTS sessionmode")
