"""DTOs for attendance reporting and export use cases."""

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from app.domain.enums.export_format import ExportFormat
from app.domain.repositories.report_repository import AttendanceReportFilters


@dataclass(frozen=True)
class PaginatedReportRequest:
    filters: AttendanceReportFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class DailyAttendanceReportRequest(PaginatedReportRequest):
    on_date: date


@dataclass(frozen=True)
class MonthlyAttendanceReportRequest:
    year: int
    month: int
    filters: AttendanceReportFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class EmployeeAttendanceSummaryRequest:
    employee_id: int
    date_from: date
    date_to: date


@dataclass(frozen=True)
class DepartmentAttendanceSummaryRequest:
    department_id: int
    date_from: date
    date_to: date
    page: int
    page_size: int


@dataclass(frozen=True)
class MyAttendanceSummaryRequest:
    user_id: int
    date_from: date
    date_to: date


@dataclass(frozen=True)
class ExportAttendanceReportRequest:
    filters: AttendanceReportFilters
    export_format: ExportFormat
    actor_user_id: int
    ip_address: Optional[str] = None
    own_user_id: Optional[int] = None


@dataclass(frozen=True)
class ReportSummary:
    total_records: int = 0
    employee_count: int = 0
    total_attendance_records: int = 0
    scheduled_processed_shift_count: int = 0
    scheduled_attended_shift_count: int = 0
    present_on_time_count: int = 0
    late_count: int = 0
    absent_count: int = 0
    early_departure_count: int = 0
    missing_checkout_count: int = 0
    late_and_missing_checkout_count: int = 0
    unscheduled_attendance_count: int = 0
    justified_absent_count: int = 0
    justified_late_count: int = 0
    justified_early_departure_count: int = 0
    justified_missing_checkout_count: int = 0
    pending_justification_count: int = 0
    approved_justification_count: int = 0
    rejected_justification_count: int = 0
    pending_overtime_request_count: int = 0
    approved_overtime_request_count: int = 0
    rejected_overtime_request_count: int = 0
    approved_overtime_minutes: int = 0
    approved_overtime_hours: float = 0.0
    total_working_hours: Optional[float] = None
    attendance_rate_percentage: Optional[float] = None


@dataclass(frozen=True)
class AttendanceReportRow:
    attendance_id: int
    employee_id: int
    employee_name: Optional[str]
    employee_number: Optional[str]
    department_id: Optional[int]
    department_name: Optional[str]
    schedule_date: date
    schedule_template_name: Optional[str]
    scheduled_start_datetime: Optional[str]
    scheduled_end_datetime: Optional[str]
    check_in_at: Optional[str]
    check_out_at: Optional[str]
    working_hours: Optional[float]
    status: str
    is_late: bool
    late_minutes: int
    is_early_departure: bool
    early_departure_minutes: int
    is_missing_checkout: bool
    is_unscheduled: bool
    latest_justification_status: Optional[str]
    latest_overtime_status: Optional[str]
    approved_overtime_minutes: int
    recognition_model_name: Optional[str]


@dataclass(frozen=True)
class EmployeeAggregateRow:
    employee_id: int
    employee_name: Optional[str]
    employee_number: Optional[str]
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    scheduled_processed_shift_count: int = 0
    scheduled_attended_shift_count: int = 0
    present_on_time_count: int = 0
    absent_count: int = 0
    late_count: int = 0
    early_departure_count: int = 0
    missing_checkout_count: int = 0
    unscheduled_attendance_count: int = 0
    approved_justification_count: int = 0
    approved_overtime_minutes: int = 0
    attendance_rate_percentage: Optional[float] = None


@dataclass(frozen=True)
class DailyAttendanceReportResult:
    report_type: str
    on_date: date
    timezone: str
    filters: dict[str, Any]
    summary: ReportSummary
    items: list[AttendanceReportRow]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


@dataclass(frozen=True)
class MonthlyAttendanceReportResult:
    report_type: str
    year: int
    month: int
    date_from: date
    date_to: date
    timezone: str
    filters: dict[str, Any]
    summary: ReportSummary
    items: list[EmployeeAggregateRow]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


@dataclass(frozen=True)
class EmployeeAttendanceSummaryResult:
    report_type: str
    employee_id: int
    employee_name: Optional[str]
    employee_number: Optional[str]
    department_name: Optional[str]
    date_from: date
    date_to: date
    timezone: str
    summary: ReportSummary
    records: list[AttendanceReportRow]
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


@dataclass(frozen=True)
class DepartmentAttendanceSummaryResult:
    report_type: str
    department_id: int
    department_name: Optional[str]
    date_from: date
    date_to: date
    timezone: str
    summary: ReportSummary
    items: list[EmployeeAggregateRow]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


@dataclass(frozen=True)
class ExportAttendanceReportResult:
    content: bytes
    media_type: str
    filename: str
    row_count: int
