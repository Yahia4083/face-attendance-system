"""DTOs for admin dashboard use cases."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.application.dto.report_dto import AttendanceReportRow, ReportSummary


@dataclass(frozen=True)
class DashboardSummaryRequest:
    on_date: Optional[date] = None


@dataclass(frozen=True)
class DashboardAttendanceTableRequest:
    on_date: Optional[date]
    department_id: Optional[int]
    employee_id: Optional[int]
    status: Optional[str]
    page: int
    page_size: int


@dataclass(frozen=True)
class DashboardPendingRequestsRequest:
    request_type: Optional[str]
    employee_id: Optional[int]
    page: int
    page_size: int


@dataclass(frozen=True)
class DashboardDepartmentSummaryRequest:
    on_date: Optional[date]
    page: int
    page_size: int


@dataclass(frozen=True)
class DashboardAttendanceTrendRequest:
    days: int
    end_date: Optional[date]


@dataclass(frozen=True)
class DashboardRecentActivityRequest:
    limit: int


@dataclass(frozen=True)
class DashboardAttendanceSummary:
    total_records: int = 0
    scheduled_processed_shift_count: int = 0
    scheduled_attended_shift_count: int = 0
    present_on_time_count: int = 0
    late_count: int = 0
    absent_count: int = 0
    early_departure_count: int = 0
    missing_checkout_count: int = 0
    unscheduled_attendance_count: int = 0
    open_check_in_count: int = 0
    attendance_rate_percentage: Optional[float] = None


@dataclass(frozen=True)
class DashboardRequestSummary:
    pending_justification_count: int = 0
    pending_overtime_request_count: int = 0
    total_pending_request_count: int = 0


@dataclass(frozen=True)
class DashboardOvertimeSummary:
    approved_overtime_request_count: int = 0
    approved_overtime_minutes: int = 0
    approved_overtime_hours: float = 0.0


@dataclass(frozen=True)
class DashboardWorkforceSummary:
    active_employee_count: int = 0
    active_department_count: int = 0


@dataclass(frozen=True)
class DashboardSummaryResult:
    dashboard_type: str
    organization_name: str
    on_date: date
    timezone: str
    generated_at: str
    attendance: DashboardAttendanceSummary
    requests: DashboardRequestSummary
    overtime: DashboardOvertimeSummary
    employees: DashboardWorkforceSummary
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


@dataclass(frozen=True)
class DashboardAttendanceTableSummary:
    total_records: int = 0
    late_count: int = 0
    absent_count: int = 0
    missing_checkout_count: int = 0
    unscheduled_attendance_count: int = 0


@dataclass(frozen=True)
class DashboardAttendanceItem:
    attendance_id: int
    employee_id: int
    employee_name: Optional[str]
    employee_number: Optional[str]
    department_id: Optional[int]
    department_name: Optional[str]
    schedule_date: date
    schedule_template_name: Optional[str]
    check_in_at: Optional[str]
    check_out_at: Optional[str]
    status: str
    is_late: bool
    is_early_departure: bool
    is_missing_checkout: bool
    is_unscheduled: bool
    latest_justification_status: Optional[str]
    latest_overtime_status: Optional[str]


@dataclass(frozen=True)
class DashboardAttendanceTableResult:
    on_date: date
    timezone: str
    summary: DashboardAttendanceTableSummary
    items: list[DashboardAttendanceItem]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


@dataclass(frozen=True)
class DashboardPendingRequestItem:
    request_category: str
    request_id: int
    employee_id: int
    employee_name: Optional[str]
    employee_number: Optional[str]
    attendance_record_id: int
    attendance_status: Optional[str]
    request_type: Optional[str]
    reason: Optional[str]
    requested_minutes: Optional[int]
    eligible_minutes_at_submission: Optional[int]
    status: str
    created_at: Optional[str]


@dataclass(frozen=True)
class DashboardPendingRequestsResult:
    summary: DashboardRequestSummary
    items: list[DashboardPendingRequestItem]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class DashboardDepartmentSummaryItem:
    department_id: int
    department_name: str
    active_employee_count: int
    total_records: int
    scheduled_processed_shift_count: int
    scheduled_attended_shift_count: int
    present_on_time_count: int
    late_count: int
    absent_count: int
    early_departure_count: int
    missing_checkout_count: int
    unscheduled_attendance_count: int
    attendance_rate_percentage: Optional[float]


@dataclass(frozen=True)
class DashboardDepartmentSummaryResult:
    on_date: date
    timezone: str
    items: list[DashboardDepartmentSummaryItem]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


@dataclass(frozen=True)
class DashboardTrendItem:
    date: date
    scheduled_processed_shift_count: int
    scheduled_attended_shift_count: int
    present_on_time_count: int
    late_count: int
    absent_count: int
    missing_checkout_count: int
    unscheduled_attendance_count: int
    attendance_rate_percentage: Optional[float]


@dataclass(frozen=True)
class DashboardAttendanceTrendResult:
    trend_type: str
    date_from: date
    date_to: date
    days: int
    timezone: str
    items: list[DashboardTrendItem]
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


@dataclass(frozen=True)
class DashboardRecentActivityItem:
    activity_type: str
    employee_id: Optional[int]
    employee_name: Optional[str]
    description: str
    occurred_at: Optional[str]
    related_entity_type: str
    related_entity_id: Optional[int]


@dataclass(frozen=True)
class DashboardRecentActivityResult:
    items: list[DashboardRecentActivityItem]


def dashboard_attendance_from_report_summary(
    summary: ReportSummary,
    *,
    open_check_in_count: int = 0,
) -> DashboardAttendanceSummary:
    """Adapt Phase 10 report metrics into dashboard card metrics."""
    return DashboardAttendanceSummary(
        total_records=summary.total_records,
        scheduled_processed_shift_count=summary.scheduled_processed_shift_count,
        scheduled_attended_shift_count=summary.scheduled_attended_shift_count,
        present_on_time_count=summary.present_on_time_count,
        late_count=summary.late_count,
        absent_count=summary.absent_count,
        early_departure_count=summary.early_departure_count,
        missing_checkout_count=summary.missing_checkout_count,
        unscheduled_attendance_count=summary.unscheduled_attendance_count,
        open_check_in_count=open_check_in_count,
        attendance_rate_percentage=summary.attendance_rate_percentage,
    )


def dashboard_table_item_from_report_row(row: AttendanceReportRow) -> DashboardAttendanceItem:
    """Return the dashboard-safe subset of an attendance report row."""
    return DashboardAttendanceItem(
        attendance_id=row.attendance_id,
        employee_id=row.employee_id,
        employee_name=row.employee_name,
        employee_number=row.employee_number,
        department_id=row.department_id,
        department_name=row.department_name,
        schedule_date=row.schedule_date,
        schedule_template_name=row.schedule_template_name,
        check_in_at=row.check_in_at,
        check_out_at=row.check_out_at,
        status=row.status,
        is_late=row.is_late,
        is_early_departure=row.is_early_departure,
        is_missing_checkout=row.is_missing_checkout,
        is_unscheduled=row.is_unscheduled,
        latest_justification_status=row.latest_justification_status,
        latest_overtime_status=row.latest_overtime_status,
    )
