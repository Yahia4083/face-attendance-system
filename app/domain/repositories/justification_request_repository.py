"""Justification request repository contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


@dataclass(frozen=True)
class JustificationRequestFilters:
    employee_id: Optional[int] = None
    attendance_record_id: Optional[int] = None
    request_type: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class JustificationRequestRepositoryInterface(ABC):
    """Abstraction for justification request persistence."""

    @abstractmethod
    def create(
        self,
        *,
        employee_id: int,
        attendance_record_id: int,
        request_type: str,
        reason: str,
        commit: bool = True,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, request_id: int) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def list_for_employee(
        self,
        employee_id: int,
        *,
        filters: JustificationRequestFilters,
        page: int,
        page_size: int,
    ) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def count_for_employee(
        self,
        employee_id: int,
        *,
        filters: JustificationRequestFilters,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_all(
        self,
        *,
        filters: JustificationRequestFilters,
        page: int,
        page_size: int,
    ) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def count_all(self, *, filters: JustificationRequestFilters) -> int:
        raise NotImplementedError

    @abstractmethod
    def has_pending_for_attendance_and_type(
        self,
        *,
        attendance_record_id: int,
        request_type: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def has_approved_for_attendance_and_type(
        self,
        *,
        attendance_record_id: int,
        request_type: str,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def exists_for_attendance(self, *, attendance_record_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def count_for_employee_attendance_month(
        self,
        *,
        employee_id: int,
        month_start: date,
        month_end: date,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def approve(
        self,
        *,
        request_id: int,
        reviewer_user_id: int,
        reviewer_note: Optional[str],
        reviewed_at: datetime,
        commit: bool = True,
    ) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def reject(
        self,
        *,
        request_id: int,
        reviewer_user_id: int,
        reviewer_note: Optional[str],
        reviewed_at: datetime,
        commit: bool = True,
    ) -> Optional[Any]:
        raise NotImplementedError
