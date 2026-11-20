"""DTOs for attendance use cases."""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.domain.repositories.attendance_record_repository import AttendanceRecordFilters
from app.domain.services.liveness_service import LivenessFrame, LivenessValidationResult


@dataclass(frozen=True)
class AttendanceFaceRequest:
    filename: str
    content: bytes
    actor_user_id: int
    ip_address: Optional[str] = None
    source: str = "FACE_API"


@dataclass(frozen=True)
class AttendanceEventResult:
    record: object
    event_type: str
    message: str
    timezone: str


@dataclass(frozen=True)
class LiveAttendanceFaceRequest:
    frames: list[LivenessFrame]
    challenge_type: str
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class LiveAttendanceEventResult:
    attendance: AttendanceEventResult
    liveness: LivenessValidationResult


@dataclass(frozen=True)
class AttendanceListRequest:
    filters: AttendanceRecordFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class EmployeeAttendanceListRequest:
    employee_id: int
    filters: AttendanceRecordFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class AttendanceListResult:
    items: list[object]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class GetAttendanceRecordRequest:
    attendance_id: int


@dataclass(frozen=True)
class MyAttendanceListRequest:
    user_id: int
    filters: AttendanceRecordFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class CreateAttendanceCorrectionRequest:
    attendance_id: int
    corrected_status: str
    reason: str
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ListAttendanceCorrectionsRequest:
    attendance_id: int
