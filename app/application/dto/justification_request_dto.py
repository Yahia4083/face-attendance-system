"""DTOs for justification request workflows."""

from dataclasses import dataclass
from typing import Optional

from app.domain.repositories.justification_request_repository import JustificationRequestFilters


@dataclass(frozen=True)
class CreateJustificationRequestDTO:
    user_id: int
    attendance_record_id: int
    request_type: str
    reason: str
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ReviewJustificationRequestDTO:
    request_id: int
    reviewer_user_id: int
    reviewer_note: Optional[str]
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ListJustificationRequestsDTO:
    filters: JustificationRequestFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class ListMyJustificationRequestsDTO:
    user_id: int
    filters: JustificationRequestFilters
    page: int
    page_size: int


@dataclass(frozen=True)
class GetJustificationRequestDTO:
    request_id: int


@dataclass(frozen=True)
class GetMyJustificationRequestDTO:
    user_id: int
    request_id: int


@dataclass(frozen=True)
class JustificationRequestListResult:
    items: list[object]
    page: int
    page_size: int
    total: int
