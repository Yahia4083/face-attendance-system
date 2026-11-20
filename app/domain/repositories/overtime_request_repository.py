"""Overtime request repository contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


@dataclass(frozen=True)
class OvertimeRequestFilters:
    employee_id: Optional[int] = None
    attendance_record_id: Optional[int] = None
    status: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class OvertimeRequestRepositoryInterface(ABC):
    """Abstraction for overtime request persistence."""

    @abstractmethod
    def create(
        self,
        *,
        employee_id: int,
        attendance_record_id: int,
        requested_minutes: int,
        eligible_minutes_at_submission: int,
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
        filters: OvertimeRequestFilters,
        page: int,
        page_size: int,
    ) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def count_for_employee(
        self,
        employee_id: int,
        *,
        filters: OvertimeRequestFilters,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def list_all(
        self,
        *,
        filters: OvertimeRequestFilters,
        page: int,
        page_size: int,
    ) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def count_all(self, *, filters: OvertimeRequestFilters) -> int:
        raise NotImplementedError

    @abstractmethod
    def has_pending_for_attendance(self, *, attendance_record_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def has_approved_for_attendance(self, *, attendance_record_id: int) -> bool:
        raise NotImplementedError

    @abstractmethod
    def approve(
        self,
        *,
        request_id: int,
        approved_minutes: int,
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
