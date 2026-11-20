"""Schedule template repository contract."""

from abc import ABC, abstractmethod
from datetime import date, time
from typing import Any, Optional


class ScheduleTemplateRepositoryInterface(ABC):
    """Abstraction for schedule template persistence."""

    @abstractmethod
    def create(
        self,
        *,
        name: str,
        description: Optional[str],
        start_time: time,
        end_time: time,
        is_overnight: bool,
        check_in_grace_minutes: int,
        early_departure_tolerance_minutes: int,
        commit: bool = True,
    ) -> Any:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, template_id: int) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def list(
        self,
        *,
        search: Optional[str],
        is_active: Optional[bool],
        page: int,
        page_size: int,
    ) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def count(self, *, search: Optional[str], is_active: Optional[bool]) -> int:
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        template_id: int,
        *,
        name: str,
        description: Optional[str],
        start_time: time,
        end_time: time,
        is_overnight: bool,
        check_in_grace_minutes: int,
        early_departure_tolerance_minutes: int,
        commit: bool = True,
    ) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def activate(self, template_id: int, *, commit: bool = True) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def deactivate(self, template_id: int, *, commit: bool = True) -> Optional[Any]:
        raise NotImplementedError

    @abstractmethod
    def has_current_or_future_active_assignments(
        self,
        template_id: int,
        *,
        reference_date: date,
    ) -> bool:
        raise NotImplementedError
