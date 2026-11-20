"""SQLAlchemy attendance record repository implementation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.repositories.attendance_record_repository import (
    AttendanceRecordFilters,
    AttendanceRecordRepositoryInterface,
)
from app.infrastructure.database.models.attendance_record import AttendanceRecordModel
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.justification_request import JustificationRequestModel
from app.infrastructure.database.models.overtime_request import OvertimeRequestModel


class SqlAttendanceRecordRepository(AttendanceRecordRepositoryInterface):
    """Attendance record repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_check_in(
        self,
        *,
        employee_id: int,
        schedule_date: date,
        check_in_at: datetime,
        status: AttendanceStatus,
        employee_schedule_id: Optional[int],
        schedule_template_id: Optional[int],
        scheduled_start_datetime: Optional[datetime],
        scheduled_end_datetime: Optional[datetime],
        is_late: bool,
        is_unscheduled: bool,
        late_minutes: int,
        recognition_model_name: str,
        detector_backend: str,
        commit: bool = True,
    ) -> AttendanceRecordModel:
        record = AttendanceRecordModel(
            employee_id=employee_id,
            employee_schedule_id=employee_schedule_id,
            schedule_template_id=schedule_template_id,
            attendance_date=schedule_date,
            scheduled_start_datetime=scheduled_start_datetime,
            scheduled_end_datetime=scheduled_end_datetime,
            check_in_time=check_in_at,
            status=status,
            is_late=is_late,
            is_early_departure=False,
            is_unscheduled=is_unscheduled,
            is_missing_checkout=False,
            late_minutes=late_minutes,
            early_departure_minutes=0,
            recognition_model_name=recognition_model_name,
            detector_backend=detector_backend,
        )
        try:
            self._db.add(record)
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return self.get_by_id(record.id) or record

    def get_by_id(self, attendance_id: int) -> Optional[AttendanceRecordModel]:
        return (
            self._base_query()
            .filter(AttendanceRecordModel.id == attendance_id)
            .first()
        )

    def find_existing_for_shift(
        self,
        *,
        employee_id: int,
        schedule_date: date,
        employee_schedule_id: Optional[int],
        is_unscheduled: bool,
    ) -> Optional[AttendanceRecordModel]:
        query = self._base_query().filter(
            AttendanceRecordModel.employee_id == employee_id,
            AttendanceRecordModel.attendance_date == schedule_date,
        )
        if is_unscheduled:
            query = query.filter(
                AttendanceRecordModel.is_unscheduled.is_(True),
                AttendanceRecordModel.check_out_time.is_(None),
            )
        else:
            query = query.filter(
                AttendanceRecordModel.employee_schedule_id == employee_schedule_id,
                AttendanceRecordModel.is_unscheduled.is_(False),
            )
        return query.order_by(AttendanceRecordModel.id.desc()).first()

    def find_open_for_employee(self, *, employee_id: int) -> Optional[AttendanceRecordModel]:
        return (
            self._base_query()
            .filter(
                AttendanceRecordModel.employee_id == employee_id,
                AttendanceRecordModel.check_in_time.is_not(None),
                AttendanceRecordModel.check_out_time.is_(None),
                AttendanceRecordModel.is_missing_checkout.is_(False),
            )
            .order_by(
                AttendanceRecordModel.check_in_time.desc(),
                AttendanceRecordModel.id.desc(),
            )
            .first()
        )

    def find_latest_for_employee_on_date(
        self,
        *,
        employee_id: int,
        on_date: date,
    ) -> Optional[AttendanceRecordModel]:
        return (
            self._base_query()
            .filter(
                AttendanceRecordModel.employee_id == employee_id,
                AttendanceRecordModel.attendance_date == on_date,
            )
            .order_by(AttendanceRecordModel.id.desc())
            .first()
        )

    def close_with_check_out(
        self,
        *,
        attendance_id: int,
        check_out_at: datetime,
        is_early_departure: bool,
        early_departure_minutes: int,
        working_hours: Optional[float],
        commit: bool = True,
    ) -> Optional[AttendanceRecordModel]:
        record = self.get_by_id(attendance_id)
        if record is None:
            return None
        record.check_out_time = check_out_at
        record.is_early_departure = is_early_departure
        record.early_departure_minutes = early_departure_minutes
        record.working_hours = working_hours
        try:
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return self.get_by_id(attendance_id)

    def list_records(
        self,
        *,
        filters: AttendanceRecordFilters,
        page: int,
        page_size: int,
    ) -> list[AttendanceRecordModel]:
        return (
            self._apply_filters(self._base_query(), filters)
            .order_by(
                AttendanceRecordModel.attendance_date.desc(),
                AttendanceRecordModel.check_in_time.desc(),
                AttendanceRecordModel.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

    def count_records(self, *, filters: AttendanceRecordFilters) -> int:
        return self._apply_filters(self._db.query(AttendanceRecordModel), filters).count()

    def create_absent_record(
        self,
        *,
        employee_id: int,
        schedule_date: date,
        employee_schedule_id: int,
        schedule_template_id: int,
        scheduled_start_datetime: datetime,
        scheduled_end_datetime: datetime,
        processed_at: datetime,
        commit: bool = True,
    ) -> AttendanceRecordModel:
        record = AttendanceRecordModel(
            employee_id=employee_id,
            employee_schedule_id=employee_schedule_id,
            schedule_template_id=schedule_template_id,
            attendance_date=schedule_date,
            scheduled_start_datetime=scheduled_start_datetime,
            scheduled_end_datetime=scheduled_end_datetime,
            check_in_time=None,
            check_out_time=None,
            status=AttendanceStatus.ABSENT,
            is_late=False,
            is_early_departure=False,
            is_unscheduled=False,
            is_missing_checkout=False,
            late_minutes=0,
            early_departure_minutes=0,
            recognition_model_name=None,
            detector_backend=None,
            processed_at=processed_at,
        )
        try:
            self._db.add(record)
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return self.get_by_id(record.id) or record

    def mark_missing_checkout(
        self,
        *,
        attendance_id: int,
        processed_at: datetime,
        commit: bool = True,
    ) -> Optional[AttendanceRecordModel]:
        record = self.get_by_id(attendance_id)
        if record is None:
            return None
        record.status = AttendanceStatus.MISSING_CHECKOUT
        record.is_missing_checkout = True
        record.processed_at = processed_at
        try:
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return self.get_by_id(attendance_id)

    def _base_query(self):
        return self._db.query(AttendanceRecordModel).options(
            joinedload(AttendanceRecordModel.employee),
            joinedload(AttendanceRecordModel.schedule_template),
            joinedload(AttendanceRecordModel.employee_schedule),
            joinedload(AttendanceRecordModel.justification_requests),
            joinedload(AttendanceRecordModel.overtime_requests),
            joinedload(AttendanceRecordModel.corrections),
        )

    @staticmethod
    def _apply_filters(query, filters: AttendanceRecordFilters):
        if filters.employee_id is not None:
            query = query.filter(AttendanceRecordModel.employee_id == filters.employee_id)
        if filters.department_id is not None:
            query = query.filter(
                AttendanceRecordModel.employee.has(
                    EmployeeModel.department_id == filters.department_id
                )
            )
        if filters.on_date is not None:
            query = query.filter(AttendanceRecordModel.attendance_date == filters.on_date)
        if filters.date_from is not None:
            query = query.filter(AttendanceRecordModel.attendance_date >= filters.date_from)
        if filters.date_to is not None:
            query = query.filter(AttendanceRecordModel.attendance_date <= filters.date_to)
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
        if filters.has_checkout is not None:
            if filters.has_checkout:
                query = query.filter(AttendanceRecordModel.check_out_time.is_not(None))
            else:
                query = query.filter(AttendanceRecordModel.check_out_time.is_(None))
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
