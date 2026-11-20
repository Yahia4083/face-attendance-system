"""DTOs for read-only administrative audit-log access."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional


@dataclass(frozen=True)
class ListAuditLogsRequest:
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    action: Optional[str] = None
    actor: Optional[str] = None
    entity_type: Optional[str] = None
    page: int = 1
    page_size: int = 25


@dataclass(frozen=True)
class AuditActorDTO:
    id: Optional[int]
    name: str
    email: Optional[str]
    kind: str
    employee_number: Optional[str] = None


@dataclass(frozen=True)
class AuditTargetDTO:
    entity_type: str
    entity_id: Optional[int]
    label: str


@dataclass(frozen=True)
class AuditLogItemDTO:
    id: int
    action: str
    actor: AuditActorDTO
    performed_by: Optional[AuditActorDTO]
    target: AuditTargetDTO
    created_at: datetime
    previous_values: Any
    current_values: Any
    has_details: bool


@dataclass(frozen=True)
class AuditLogListResult:
    items: list[AuditLogItemDTO]
    page: int
    page_size: int
    total: int
    timezone: str
    available_actions: list[str]
    available_entity_types: list[str]
