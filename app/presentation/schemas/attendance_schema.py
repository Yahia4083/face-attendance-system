"""Pydantic schemas for attendance endpoints."""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class AttendanceEventResponse(BaseModel):
    attendance_id: int
    event_type: str
    employee_id: int
    employee_name: Optional[str] = None
    employee_number: Optional[str] = None
    schedule_date: date
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None
    scheduled_start_datetime: Optional[str] = None
    scheduled_end_datetime: Optional[str] = None
    status: str
    is_late: bool
    is_early_departure: bool
    is_unscheduled: bool
    timezone: str
    recognition_model_name: Optional[str] = None
    message: str


class AttendanceCorrectionResponse(BaseModel):
    id: int
    attendance_record_id: int
    original_status: str
    corrected_status: str
    reason: str
    corrected_by_user_id: int
    corrected_at: str
    created_at: str
    message: Optional[str] = None


class AttendanceCorrectionListResponse(BaseModel):
    items: list[AttendanceCorrectionResponse]
    total: int


class AttendanceCorrectionCreateRequest(BaseModel):
    corrected_status: str
    reason: str = Field(min_length=10, max_length=1000)


class AttendanceRecordResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    employee_number: Optional[str] = None
    employee_schedule_id: Optional[int] = None
    schedule_template_id: Optional[int] = None
    schedule_template_name: Optional[str] = None
    schedule_date: date
    scheduled_start_datetime: Optional[str] = None
    scheduled_end_datetime: Optional[str] = None
    check_in_at: Optional[str] = None
    check_out_at: Optional[str] = None
    working_hours: Optional[float] = None
    status: str
    is_late: bool
    is_early_departure: bool
    is_unscheduled: bool
    is_missing_checkout: bool = False
    late_minutes: int
    early_departure_minutes: int
    has_pending_justification: bool = False
    latest_justification_status: Optional[str] = None
    has_pending_overtime_request: bool = False
    latest_overtime_status: Optional[str] = None
    recognition_model_name: Optional[str] = None
    original_status: str
    effective_status: str
    has_admin_correction: bool = False
    latest_correction: Optional[AttendanceCorrectionResponse] = None
    created_at: str
    updated_at: str


class AttendanceRecordListResponse(BaseModel):
    items: list[AttendanceRecordResponse]
    page: int
    page_size: int
    total: int
