"""complete attendance check-in checkout fields

Revision ID: 202605260002
Revises: 202605260001
Create Date: 2026-05-26 00:02:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "202605260002"
down_revision: Union[str, None] = "202605260001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attendance_records",
        sa.Column("employee_schedule_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "attendance_records",
        sa.Column("schedule_template_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "attendance_records",
        sa.Column("scheduled_start_datetime", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "attendance_records",
        sa.Column("scheduled_end_datetime", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "attendance_records",
        sa.Column("is_late", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "attendance_records",
        sa.Column("is_early_departure", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "attendance_records",
        sa.Column("is_unscheduled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "attendance_records",
        sa.Column("recognition_model_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "attendance_records",
        sa.Column("detector_backend", sa.String(length=50), nullable=True),
    )
    op.create_foreign_key(
        "fk_attendance_records_employee_schedule_id",
        "attendance_records",
        "employee_schedules",
        ["employee_schedule_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_attendance_records_schedule_template_id",
        "attendance_records",
        "schedule_templates",
        ["schedule_template_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_attendance_records_schedule_template_id",
        "attendance_records",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_attendance_records_employee_schedule_id",
        "attendance_records",
        type_="foreignkey",
    )
    op.drop_column("attendance_records", "detector_backend")
    op.drop_column("attendance_records", "recognition_model_name")
    op.drop_column("attendance_records", "is_unscheduled")
    op.drop_column("attendance_records", "is_early_departure")
    op.drop_column("attendance_records", "is_late")
    op.drop_column("attendance_records", "scheduled_end_datetime")
    op.drop_column("attendance_records", "scheduled_start_datetime")
    op.drop_column("attendance_records", "schedule_template_id")
    op.drop_column("attendance_records", "employee_schedule_id")
