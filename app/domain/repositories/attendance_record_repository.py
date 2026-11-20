"""Attendance record repository contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from app.domain.enums.attendance_status import AttendanceStatus


@dataclass(frozen=True)
class AttendanceRecordFilters:
    """Filter values for attendance record listing."""

    employee_id: Optional[int] = None
    department_id: Optional[int] = None
    on_date: Optional[date] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    status: Optional[str] = None
    is_late: Optional[bool] = None
    is_early_departure: Optional[bool] = None
    is_unscheduled: Optional[bool] = None
    is_missing_checkout: Optional[bool] = None
    has_checkout: Optional[bool] = None
    justification_status: Optional[str] = None
    overtime_status: Optional[str] = None


class AttendanceRecordRepositoryInterface(ABC):
    """Abstraction for attendance persistence operations."""

    @abstractmethod
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
    ) -> Any:
        """Create a check-in record."""
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, attendance_id: int) -> Optional[Any]:
        """Return an attendance record by ID."""
        raise NotImplementedError

    @abstractmethod
    def find_existing_for_shift(
        self,
        *,
        employee_id: int,
        schedule_date: date,
        employee_schedule_id: Optional[int],
        is_unscheduled: bool,
    ) -> Optional[Any]:
        """Return an existing attendance record for the same effective shift."""
        raise NotImplementedError

    @abstractmethod
    def find_open_for_employee(self, *, employee_id: int) -> Optional[Any]:
        """Return the most recent open attendance record for an employee."""
        raise NotImplementedError

    @abstractmethod
    def find_latest_for_employee_on_date(
        self,
        *,
        employee_id: int,
        on_date: date,
    ) -> Optional[Any]:
        """Return the employee's latest existing attendance record for a business date."""
        raise NotImplementedError

    @abstractmethod
    def close_with_check_out(
        self,
        *,
        attendance_id: int,
        check_out_at: datetime,
        is_early_departure: bool,
        early_departure_minutes: int,
        working_hours: Optional[float],
        commit: bool = True,
    ) -> Optional[Any]:
        """Close an open attendance record with check-out metadata."""
        raise NotImplementedError

    @abstractmethod
    def list_records(
        self,
        *,
        filters: AttendanceRecordFilters,
        page: int,
        page_size: int,
    ) -> list[Any]:
        """Return paginated attendance records."""
        raise NotImplementedError

    @abstractmethod
    def count_records(self, *, filters: AttendanceRecordFilters) -> int:
        """Return count matching attendance filters."""
        raise NotImplementedError

    @abstractmethod
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
    ) -> Any:
        """Create an ABSENT record for a scheduled shift."""
        raise NotImplementedError

    @abstractmethod
    def mark_missing_checkout(
        self,
        *,
        attendance_id: int,
        processed_at: datetime,
        commit: bool = True,
    ) -> Optional[Any]:
        """Mark an open scheduled attendance record as missing checkout."""
        raise NotImplementedError
