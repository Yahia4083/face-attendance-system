"""Dashboard repository contracts."""

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.entities.dashboard import (
    DashboardActivity,
    DashboardDepartmentSnapshot,
    PendingDashboardRequest,
)


class DashboardRepositoryInterface(ABC):
    """Read-only dashboard-specific persistence operations."""

    @abstractmethod
    def count_active_employees(self) -> int:
        """Return the number of active employees."""
        raise NotImplementedError

    @abstractmethod
    def count_active_departments(self) -> int:
        """Return the number of active departments."""
        raise NotImplementedError

    @abstractmethod
    def list_active_department_snapshots(self) -> list[DashboardDepartmentSnapshot]:
        """Return active departments with active employee counts."""
        raise NotImplementedError

    @abstractmethod
    def count_pending_justification_requests(self, *, employee_id: Optional[int] = None) -> int:
        """Return the current pending justification request count."""
        raise NotImplementedError

    @abstractmethod
    def count_pending_overtime_requests(self, *, employee_id: Optional[int] = None) -> int:
        """Return the current pending overtime request count."""
        raise NotImplementedError

    @abstractmethod
    def list_pending_justification_requests(
        self,
        *,
        employee_id: Optional[int] = None,
    ) -> list[PendingDashboardRequest]:
        """Return safe pending justification request rows."""
        raise NotImplementedError

    @abstractmethod
    def list_pending_overtime_requests(
        self,
        *,
        employee_id: Optional[int] = None,
    ) -> list[PendingDashboardRequest]:
        """Return safe pending overtime request rows."""
        raise NotImplementedError

    @abstractmethod
    def list_recent_activities(self, *, limit: int) -> list[DashboardActivity]:
        """Return safe recent activity items for the dashboard."""
        raise NotImplementedError
