"""Schemas for admin dashboard endpoints."""

from datetime import date
from typing import Optional

from pydantic import BaseModel


class DashboardAttendanceSummaryResponse(BaseModel):
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


class DashboardRequestSummaryResponse(BaseModel):
    pending_justification_count: int = 0
    pending_overtime_request_count: int = 0
    total_pending_request_count: int = 0


class DashboardOvertimeSummaryResponse(BaseModel):
    approved_overtime_request_count: int = 0
    approved_overtime_minutes: int = 0
    approved_overtime_hours: float = 0.0


class DashboardWorkforceSummaryResponse(BaseModel):
    active_employee_count: int = 0
    active_department_count: int = 0


class DashboardSummaryResponse(BaseModel):
    dashboard_type: str
    organization_name: str
    on_date: date
    timezone: str
    generated_at: str
    attendance: DashboardAttendanceSummaryResponse
    requests: DashboardRequestSummaryResponse
    overtime: DashboardOvertimeSummaryResponse
    employees: DashboardWorkforceSummaryResponse
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


class DashboardAttendanceTableSummaryResponse(BaseModel):
    total_records: int = 0
    late_count: int = 0
    absent_count: int = 0
    missing_checkout_count: int = 0
    unscheduled_attendance_count: int = 0


class DashboardAttendanceItemResponse(BaseModel):
    attendance_id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_number: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    schedule_date: date
    schedule_template_name: Optional[str] = None
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None
    status: str
    is_late: bool
    is_early_departure: bool
    is_missing_checkout: bool
    is_unscheduled: bool
    latest_justification_status: Optional[str] = None
    latest_overtime_status: Optional[str] = None


class DashboardAttendanceTableResponse(BaseModel):
    on_date: date
    timezone: str
    summary: DashboardAttendanceTableSummaryResponse
    items: list[DashboardAttendanceItemResponse]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


class DashboardPendingRequestItemResponse(BaseModel):
    request_category: str
    request_id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_number: Optional[str] = None
    attendance_record_id: int
    attendance_status: Optional[str] = None
    request_type: Optional[str] = None
    reason: Optional[str] = None
    requested_minutes: Optional[int] = None
    eligible_minutes_at_submission: Optional[int] = None
    status: str
    created_at: Optional[str] = None


class DashboardPendingRequestsResponse(BaseModel):
    summary: DashboardRequestSummaryResponse
    items: list[DashboardPendingRequestItemResponse]
    page: int
    page_size: int
    total: int


class DashboardDepartmentSummaryItemResponse(BaseModel):
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
    attendance_rate_percentage: Optional[float] = None


class DashboardDepartmentSummaryResponse(BaseModel):
    on_date: date
    timezone: str
    items: list[DashboardDepartmentSummaryItemResponse]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


class DashboardTrendItemResponse(BaseModel):
    date: date
    scheduled_processed_shift_count: int
    scheduled_attended_shift_count: int
    present_on_time_count: int
    late_count: int
    absent_count: int
    missing_checkout_count: int
    unscheduled_attendance_count: int
    attendance_rate_percentage: Optional[float] = None


class DashboardAttendanceTrendResponse(BaseModel):
    trend_type: str
    date_from: date
    date_to: date
    days: int
    timezone: str
    items: list[DashboardTrendItemResponse]
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


class DashboardRecentActivityItemResponse(BaseModel):
    activity_type: str
    employee_id: Optional[int] = None
    employee_name: Optional[str] = None
    description: str
    occurred_at: Optional[str] = None
    related_entity_type: str
    related_entity_id: Optional[int] = None


class DashboardRecentActivityResponse(BaseModel):
    items: list[DashboardRecentActivityItemResponse]
