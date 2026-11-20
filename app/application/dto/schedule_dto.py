"""DTOs for schedule management use cases."""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional


@dataclass(frozen=True)
class ScheduleTemplateMutationRequest:
    name: str
    description: Optional[str]
    start_time: time
    end_time: time
    is_overnight: bool
    check_in_grace_minutes: int
    early_departure_tolerance_minutes: int
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ScheduleTemplateListRequest:
    search: Optional[str]
    is_active: Optional[bool]
    page: int
    page_size: int


@dataclass(frozen=True)
class ScheduleTemplateActionRequest:
    template_id: int
    actor_user_id: Optional[int] = None
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class EmployeeScheduleMutationRequest:
    employee_id: int
    schedule_template_id: int
    effective_from: date
    effective_to: Optional[date]
    working_days: list[int]
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class EmployeeScheduleListRequest:
    employee_id: int
    is_active: Optional[bool]
    page: int
    page_size: int


@dataclass(frozen=True)
class EmployeeScheduleActionRequest:
    employee_id: int
    assignment_id: int
    actor_user_id: Optional[int] = None
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class EffectiveScheduleRequest:
    employee_id: int
    on_date: date


@dataclass(frozen=True)
class ScheduleTemplateListResult:
    items: list[object]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class EmployeeScheduleListResult:
    employee_id: int
    items: list[object]
    page: int
    page_size: int
    total: int


@dataclass(frozen=True)
class EffectiveScheduleResult:
    employee_id: int
    employee_name: str
    on_date: date
    has_schedule: bool
    working_day: bool
    assignment_id: Optional[int] = None
    schedule_template_id: Optional[int] = None
    schedule_template_name: Optional[str] = None
    scheduled_start_datetime: Optional[datetime] = None
    scheduled_end_datetime: Optional[datetime] = None
    is_overnight: Optional[bool] = None
    check_in_grace_minutes: Optional[int] = None
    early_departure_tolerance_minutes: Optional[int] = None
    timezone: Optional[str] = None
    message: Optional[str] = None
