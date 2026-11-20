"""Reporting repository contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional


@dataclass(frozen=True)
class AttendanceReportFilters:
    """Filter values shared by attendance reports and exports."""

    date_from: Optional[date] = None
    date_to: Optional[date] = None
    on_date: Optional[date] = None
    employee_id: Optional[int] = None
    department_id: Optional[int] = None
    status: Optional[str] = None
    is_late: Optional[bool] = None
    is_early_departure: Optional[bool] = None
    is_unscheduled: Optional[bool] = None
    is_missing_checkout: Optional[bool] = None
    justification_status: Optional[str] = None
    overtime_status: Optional[str] = None


class ReportRepositoryInterface(ABC):
    """Read-only persistence operations for reporting."""

    @abstractmethod
    def list_attendance_records(
        self,
        *,
        filters: AttendanceReportFilters,
        page: int,
        page_size: int,
    ) -> list[Any]:
        """Return paginated attendance records for reports."""
        raise NotImplementedError

    @abstractmethod
    def count_attendance_records(self, *, filters: AttendanceReportFilters) -> int:
        """Return the count of attendance records matching filters."""
        raise NotImplementedError

    @abstractmethod
    def list_attendance_records_for_export(
        self,
        *,
        filters: AttendanceReportFilters,
    ) -> list[Any]:
        """Return all safe attendance records matching export filters."""
        raise NotImplementedError
