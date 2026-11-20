"""Schemas for live mobile-camera attendance endpoints."""

from typing import Optional

from pydantic import BaseModel

from app.presentation.schemas.attendance_schema import AttendanceEventResponse


class LivenessResultResponse(BaseModel):
    passed: bool
    challenge_type: str
    confidence: float
    frames_analyzed: int


class LiveAttendanceEventResponse(AttendanceEventResponse):
    liveness: LivenessResultResponse


class UnifiedLiveAttendanceResponse(BaseModel):
    success: bool
    action: str
    employee_id: int
    employee_number: Optional[str] = None
    employee_name: Optional[str] = None
    attendance_record_id: int
    timestamp: str
    status: str
    is_unscheduled: bool
    working_hours: Optional[float] = None
    message: str
    timezone: str
    recognition_model_name: Optional[str] = None
    liveness: LivenessResultResponse
