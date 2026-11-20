"""Department-related DTOs for application use cases."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CreateDepartmentRequest:
    name: str
    description: Optional[str]
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class UpdateDepartmentRequest:
    department_id: int
    name: str
    description: Optional[str]
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class DepartmentListParams:
    is_active: Optional[bool]
    search: Optional[str]
    page: int
    page_size: int


@dataclass(frozen=True)
class DepartmentStateChangeRequest:
    department_id: int
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class DepartmentListResult:
    items: list[Any]
    total: int
    page: int
    page_size: int
