"""
Audit Repository Interface
==========================
Abstract base class defining the contract for audit log persistence.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.domain.entities.audit_log import AuditLogRecord


@dataclass(frozen=True)
class AuditLogFilters:
    """Database-ready filters for the read-only audit-log view."""

    created_from_utc: Optional[datetime] = None
    created_to_utc_exclusive: Optional[datetime] = None
    actor_query: Optional[str] = None
    action: Optional[str] = None
    entity_type: Optional[str] = None


class AuditRepositoryInterface(ABC):
    """Interface for audit-log writes and safe administrative reads."""

    @abstractmethod
    def log(
        self,
        *,
        actor_user_id: Optional[int],
        action: str,
        entity_type: str,
        entity_id: Optional[int] = None,
        old_values: Optional[str] = None,
        new_values: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Persist a single audit log entry."""
        raise NotImplementedError

    @abstractmethod
    def list_logs(
        self,
        *,
        filters: AuditLogFilters,
        page: int,
        page_size: int,
    ) -> list[AuditLogRecord]:
        """Return one filtered page ordered from newest to oldest."""
        raise NotImplementedError

    @abstractmethod
    def count_logs(self, *, filters: AuditLogFilters) -> int:
        """Return the total number of events matching the filters."""
        raise NotImplementedError

    @abstractmethod
    def list_actions(self) -> list[str]:
        """Return action values that already exist in audit history."""
        raise NotImplementedError

    @abstractmethod
    def list_entity_types(self) -> list[str]:
        """Return target types that already exist in audit history."""
        raise NotImplementedError
