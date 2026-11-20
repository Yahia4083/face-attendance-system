"""Schemas for justification request endpoints."""

from typing import Optional

from pydantic import BaseModel


class JustificationRequestCreateRequest(BaseModel):
    request_type: str
    reason: str


class JustificationReviewRequest(BaseModel):
    reviewer_note: Optional[str] = None


class JustificationRequestResponse(BaseModel):
    id: int
    attendance_record_id: int
    employee_id: int
    employee_name: Optional[str] = None
    request_type: str
    reason: str
    status: str
    reviewer_user_id: Optional[int] = None
    reviewer_note: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    message: Optional[str] = None


class JustificationRequestListResponse(BaseModel):
    items: list[JustificationRequestResponse]
    page: int
    page_size: int
    total: int
