"""DTOs for overtime request workflows."""

from dataclasses import dataclass
from typing import Optional

from app.domain.repositories.overtime_request_repository import OvertimeRequestFilters


@dataclass(frozen=True)
class CreateOvertimeRequestDTO:
    user_id: int
    attendance_record_id: int
    requested_minutes: int
    reason: str
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ApproveOvertimeRequestDTO:
    request_id: int
    reviewer_user_id: int
    approved_minutes: int
    reviewer_note: Optional[str]
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class RejectOvertimeRequestDTO:
    request_id: int
    reviewer_user_id: int
    reviewer_note: Optional[str]
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ListOvertimeRequestsDTO:
    filters: OvertimeRequestFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class ListMyOvertimeRequestsDTO:
    user_id: int
    filters: OvertimeRequestFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class GetOvertimeRequestDTO:
    request_id: int


@dataclass(frozen=True)
class GetMyOvertimeRequestDTO:
    user_id: int
    request_id: int


@dataclass(frozen=True)
class OvertimeRequestListResult:
    items: list[object]
    page: int
    page_size: int
    total: int
