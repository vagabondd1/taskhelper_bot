"""add guided_share_thinking to actiontype enum

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE actiontype ADD VALUE IF NOT EXISTS 'guided_share_thinking'"
    )


def downgrade() -> None:
    # Postgres не поддерживает удаление значения из enum без пересоздания типа.
    pass
