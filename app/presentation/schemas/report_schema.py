"""Schemas for reporting endpoints."""

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel


class ReportSummaryResponse(BaseModel):
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


class AttendanceReportItemResponse(BaseModel):
    attendance_id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_number: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    schedule_date: date
    schedule_template_name: Optional[str] = None
    scheduled_start_datetime: Optional[str] = None
    scheduled_end_datetime: Optional[str] = None
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None
    working_hours: Optional[float] = None
    status: str
    is_late: bool
    late_minutes: int
    is_early_departure: bool
    early_departure_minutes: int
    is_missing_checkout: bool
    is_unscheduled: bool
    latest_justification_status: Optional[str] = None
    latest_overtime_status: Optional[str] = None
    approved_overtime_minutes: int
    recognition_model_name: Optional[str] = None


class EmployeeAggregateReportItemResponse(BaseModel):
    employee_id: int
    employee_name: Optional[str] = None
    employee_number: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    scheduled_processed_shift_count: int
    scheduled_attended_shift_count: int
    present_on_time_count: int = 0
    absent_count: int
    late_count: int
    early_departure_count: int
    missing_checkout_count: int
    unscheduled_attendance_count: int
    approved_justification_count: int
    approved_overtime_minutes: int
    attendance_rate_percentage: Optional[float] = None


class DailyAttendanceReportResponse(BaseModel):
    report_type: str
    on_date: date
    timezone: str
    filters: dict[str, Any]
    summary: ReportSummaryResponse
    items: list[AttendanceReportItemResponse]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


class MonthlyAttendanceReportResponse(BaseModel):
    report_type: str
    year: int
    month: int
    date_from: date
    date_to: date
    timezone: str
    filters: dict[str, Any]
    summary: ReportSummaryResponse
    items: list[EmployeeAggregateReportItemResponse]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


class EmployeeAttendanceSummaryReportResponse(BaseModel):
    report_type: str
    employee_id: int
    employee_name: Optional[str] = None
    employee_number: Optional[str] = None
    department_name: Optional[str] = None
    date_from: date
    date_to: date
    timezone: str
    summary: ReportSummaryResponse
    records: list[AttendanceReportItemResponse]
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool


class DepartmentAttendanceSummaryReportResponse(BaseModel):
    report_type: str
    department_id: int
    department_name: Optional[str] = None
    date_from: date
    date_to: date
    timezone: str
    summary: ReportSummaryResponse
    items: list[EmployeeAggregateReportItemResponse]
    page: int
    page_size: int
    total: int
    data_basis: str
    requires_daily_processing_for_complete_absence_metrics: bool
