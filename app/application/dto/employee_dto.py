"""Employee-related DTOs for application use cases."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class CreateEmployeeRequest:
    email: str
    password: str
    full_name: str
    employee_number: str
    phone: Optional[str]
    position: Optional[str]
    department_id: int
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class UpdateEmployeeRequest:
    employee_id: int
    email: Optional[str]
    full_name: str
    phone: Optional[str]
    position: Optional[str]
    department_id: int
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class EmployeeListParams:
    is_active: Optional[bool]
    department_id: Optional[int]
    search: Optional[str]
    page: int
    page_size: int


@dataclass(frozen=True)
class EmployeeStateChangeRequest:
    employee_id: int
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class EmployeeListResult:
    items: list[Any]
    total: int
    page: int
    page_size: int
