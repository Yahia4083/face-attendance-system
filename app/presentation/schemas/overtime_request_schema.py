"""Schemas for overtime request endpoints."""

from typing import Optional

from pydantic import BaseModel


class OvertimeRequestCreateRequest(BaseModel):
    requested_minutes: int
    reason: str


class OvertimeApproveRequest(BaseModel):
    approved_minutes: int
    reviewer_note: Optional[str] = None


class OvertimeRejectRequest(BaseModel):
    reviewer_note: Optional[str] = None


class OvertimeRequestResponse(BaseModel):
    id: int
    employee_id: int
    employee_name: Optional[str] = None
    attendance_record_id: int
    requested_minutes: int
    eligible_minutes_at_submission: int
    approved_minutes: Optional[int] = None
    reason: Optional[str] = None
    status: str
    reviewer_user_id: Optional[int] = None
    reviewer_note: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    message: Optional[str] = None


class OvertimeRequestListResponse(BaseModel):
    items: list[OvertimeRequestResponse]
    page: int
    page_size: int
    total: int
