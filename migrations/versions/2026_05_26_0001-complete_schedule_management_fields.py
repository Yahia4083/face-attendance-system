"""complete schedule management fields

Revision ID: 202605260001
Revises: d5e8780616b3
Create Date: 2026-05-26 00:01:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202605260001"
down_revision: Union[str, None] = "d5e8780616b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("schedule_templates", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "schedule_templates",
        sa.Column("is_overnight", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "schedule_templates",
        sa.Column("check_in_grace_minutes", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "schedule_templates",
        sa.Column(
            "early_departure_tolerance_minutes",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    op.add_column(
        "employee_schedules",
        sa.Column(
            "working_days",
            sa.String(length=50),
            server_default="0,1,2,3,4,5,6",
            nullable=False,
            comment="Comma-separated ISO weekday numbers, 0=Mon ... 6=Sun",
        ),
    )
    op.add_column(
        "employee_schedules",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.execute(
        "UPDATE schedule_templates "
        "SET check_in_grace_minutes = grace_period_minutes "
        "WHERE check_in_grace_minutes = 0"
    )


def downgrade() -> None:
    op.drop_column("employee_schedules", "updated_at")
    op.drop_column("employee_schedules", "working_days")
    op.drop_column("schedule_templates", "early_departure_tolerance_minutes")
    op.drop_column("schedule_templates", "check_in_grace_minutes")
    op.drop_column("schedule_templates", "is_overnight")
    op.drop_column("schedule_templates", "description")
