"""Pydantic schemas for schedule management endpoints."""

from datetime import date, time
from typing import Optional

from pydantic import BaseModel, Field


class ScheduleTemplateCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    start_time: time
    end_time: time
    is_overnight: bool = False
    check_in_grace_minutes: int = 0
    early_departure_tolerance_minutes: int = 0


class ScheduleTemplateUpdateRequest(ScheduleTemplateCreateRequest):
    pass


class ScheduleTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    start_time: time
    end_time: time
    is_overnight: bool
    check_in_grace_minutes: int
    early_departure_tolerance_minutes: int
    is_active: bool
    created_at: str
    updated_at: str


class ScheduleTemplateListResponse(BaseModel):
    items: list[ScheduleTemplateResponse]
    page: int
    page_size: int
    total: int


class EmployeeScheduleCreateRequest(BaseModel):
    schedule_template_id: int
    effective_from: date
    effective_to: Optional[date] = None
    working_days: list[int] = Field(default_factory=list)


class EmployeeScheduleUpdateRequest(EmployeeScheduleCreateRequest):
    pass


class EmployeeScheduleResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    schedule_template_id: int
    schedule_template_name: Optional[str]
    effective_from: date
    effective_to: Optional[date]
    working_days: list[int]
    is_active: bool
    created_at: str
    updated_at: str


class EmployeeScheduleListItem(BaseModel):
    id: int
    schedule_template_id: int
    schedule_template_name: Optional[str]
    effective_from: date
    effective_to: Optional[date]
    working_days: list[int]
    is_active: bool
    created_at: str
    updated_at: str


class EmployeeScheduleListResponse(BaseModel):
    employee_id: int
    items: list[EmployeeScheduleListItem]
    page: int
    page_size: int
    total: int


class EmployeeScheduleDeactivateResponse(BaseModel):
    id: int
    employee_id: int
    schedule_template_id: int
    is_active: bool
    message: str


class EffectiveScheduleResponse(BaseModel):
    employee_id: int
    employee_name: str
    on_date: date
    has_schedule: bool
    working_day: bool
    assignment_id: Optional[int] = None
    schedule_template_id: Optional[int] = None
    schedule_template_name: Optional[str] = None
    scheduled_start_datetime: Optional[str] = None
    scheduled_end_datetime: Optional[str] = None
    is_overnight: Optional[bool] = None
    check_in_grace_minutes: Optional[int] = None
    early_departure_tolerance_minutes: Optional[int] = None
    timezone: Optional[str] = None
    message: Optional[str] = None
