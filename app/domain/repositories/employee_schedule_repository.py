"""Employee schedule assignment repository contract."""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Optional


class EmployeeScheduleRepositoryInterface(ABC):
    """Abstraction for employee schedule assignment persistence."""

    @abstractmethod
    def create(
        self,
        *,
        employee_id: int,
        schedule_template_id: int,
        effective_from: date,
        effective_to: Optional[date],
        working_days: list[int],
        commit: bool = True,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, assignment_id: int) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def get_by_employee_and_id(self, employee_id: int, assignment_id: int) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def list_by_employee_id(
        self,
        employee_id: int,
        *,
        is_active: Optional[bool],
        page: int,
        page_size: int,
    ) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def count_by_employee_id(self, employee_id: int, *, is_active: Optional[bool]) -> int:
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        assignment_id: int,
        *,
        schedule_template_id: int,
        effective_from: date,
        effective_to: Optional[date],
        working_days: list[int],
        commit: bool = True,
    ) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def activate(self, assignment_id: int, *, commit: bool = True) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def deactivate(self, assignment_id: int, *, commit: bool = True) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def has_overlap(
        self,
        *,
        employee_id: int,
        effective_from: date,
        effective_to: Optional[date],
        exclude_assignment_id: Optional[int] = None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_effective_schedule(self, *, employee_id: int, on_date: date) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def list_active_assignments_for_date(self, *, on_date: date) -> list[Any]:
        raise NotImplementedError
