"""SQLAlchemy report repository implementation."""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.domain.repositories.report_repository import (
    AttendanceReportFilters,
    ReportRepositoryInterface,
)
from app.infrastructure.database.models.attendance_record import AttendanceRecordModel
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.justification_request import JustificationRequestModel
from app.infrastructure.database.models.overtime_request import OvertimeRequestModel


class SqlReportRepository(ReportRepositoryInterface):
    """Read-only attendance reporting queries."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_attendance_records(
        self,
        *,
        filters: AttendanceReportFilters,
        page: int,
        page_size: int,
    ) -> list[AttendanceRecordModel]:
        return (
            self._apply_filters(self._base_query(), filters)
            .order_by(
                AttendanceRecordModel.attendance_date.desc(),
                AttendanceRecordModel.employee_id.asc(),
                AttendanceRecordModel.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

    def count_attendance_records(self, *, filters: AttendanceReportFilters) -> int:
        return self._apply_filters(self._db.query(AttendanceRecordModel), filters).count()

    def list_attendance_records_for_export(
        self,
        *,
        filters: AttendanceReportFilters,
    ) -> list[AttendanceRecordModel]:
        return (
            self._apply_filters(self._base_query(), filters)
            .order_by(
                AttendanceRecordModel.attendance_date.asc(),
                AttendanceRecordModel.employee_id.asc(),
                AttendanceRecordModel.id.asc(),
            )
            .all()
        )

    def _base_query(self):
        return self._db.query(AttendanceRecordModel).options(
            joinedload(AttendanceRecordModel.employee).joinedload(EmployeeModel.department),
            joinedload(AttendanceRecordModel.schedule_template),
            joinedload(AttendanceRecordModel.justification_requests),
            joinedload(AttendanceRecordModel.overtime_requests),
        )

    @staticmethod
    def _apply_filters(query, filters: AttendanceReportFilters):
        if filters.on_date is not None:
            query = query.filter(AttendanceRecordModel.attendance_date == filters.on_date)
        if filters.date_from is not None:
            query = query.filter(AttendanceRecordModel.attendance_date >= filters.date_from)
        if filters.date_to is not None:
            query = query.filter(AttendanceRecordModel.attendance_date <= filters.date_to)
        if filters.employee_id is not None:
            query = query.filter(AttendanceRecordModel.employee_id == filters.employee_id)
        if filters.department_id is not None:
            query = query.filter(
                AttendanceRecordModel.employee.has(
                    EmployeeModel.department_id == filters.department_id
                )
            )
        if filters.status is not None:
            query = query.filter(AttendanceRecordModel.status == filters.status)
        if filters.is_late is not None:
            query = query.filter(AttendanceRecordModel.is_late == filters.is_late)
        if filters.is_early_departure is not None:
            query = query.filter(
                AttendanceRecordModel.is_early_departure == filters.is_early_departure
            )
        if filters.is_unscheduled is not None:
            query = query.filter(AttendanceRecordModel.is_unscheduled == filters.is_unscheduled)
        if filters.is_missing_checkout is not None:
            query = query.filter(
                AttendanceRecordModel.is_missing_checkout == filters.is_missing_checkout
            )
        if filters.justification_status is not None:
            query = query.filter(
                AttendanceRecordModel.justification_requests.any(
                    JustificationRequestModel.status == filters.justification_status
                )
            )
        if filters.overtime_status is not None:
            query = query.filter(
                AttendanceRecordModel.overtime_requests.any(
                    OvertimeRequestModel.status == filters.overtime_status
                )
            )
        return query
