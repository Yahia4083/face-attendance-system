"""add attendance corrections

Revision ID: 202605280001
Revises: 202605270001
Create Date: 2026-05-28 21:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "202605280001"
down_revision: Union[str, None] = "202605270001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_corrections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attendance_record_id", sa.Integer(), nullable=False),
        sa.Column("original_status", sa.String(length=50), nullable=False),
        sa.Column("corrected_status", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("corrected_by_user_id", sa.Integer(), nullable=False),
        sa.Column("corrected_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["attendance_record_id"], ["attendance_records.id"]),
        sa.ForeignKeyConstraint(["corrected_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attendance_corrections_attendance_record_id",
        "attendance_corrections",
        ["attendance_record_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_corrections_attendance_record_id", table_name="attendance_corrections")
    op.drop_table("attendance_corrections")
