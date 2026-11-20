"""complete phase 9 attendance admin request fields

Revision ID: 202605270001
Revises: 202605260002
Create Date: 2026-05-27 00:01:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "202605270001"
down_revision: Union[str, None] = "202605260002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attendance_records",
        sa.Column("is_missing_checkout", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("attendance_records", sa.Column("processed_at", sa.DateTime(), nullable=True))
    op.add_column(
        "justification_requests",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "overtime_requests",
        sa.Column(
            "eligible_minutes_at_submission",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column("overtime_requests", sa.Column("approved_minutes", sa.Integer(), nullable=True))
    op.add_column("overtime_requests", sa.Column("reason", sa.Text(), nullable=True))
    op.add_column("overtime_requests", sa.Column("reviewer_note", sa.Text(), nullable=True))
    op.add_column(
        "overtime_requests",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("overtime_requests", "updated_at")
    op.drop_column("overtime_requests", "reviewer_note")
    op.drop_column("overtime_requests", "reason")
    op.drop_column("overtime_requests", "approved_minutes")
    op.drop_column("overtime_requests", "eligible_minutes_at_submission")
    op.drop_column("justification_requests", "updated_at")
    op.drop_column("attendance_records", "processed_at")
    op.drop_column("attendance_records", "is_missing_checkout")
