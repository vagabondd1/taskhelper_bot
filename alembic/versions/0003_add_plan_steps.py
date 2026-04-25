"""add plan_steps and total_steps to sessions

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-23

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("plan_steps", postgresql.JSONB(), nullable=True))
    op.add_column("sessions", sa.Column("total_steps", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "total_steps")
    op.drop_column("sessions", "plan_steps")
