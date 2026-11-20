"""Schemas for system settings endpoints."""

from typing import Any, Optional

from pydantic import BaseModel


class SystemSettingResponse(BaseModel):
    key: str
    display_name: str
    description: str
    category: str
    data_type: str
    value: Any
    default_value: Any
    source: str
    editable_by_admin: bool
    future_requests_only: bool
    updated_at: Optional[str] = None
    updated_by_user_id: Optional[int] = None


class SystemSettingListResponse(BaseModel):
    items: list[SystemSettingResponse]


class SystemSettingUpdateRequest(BaseModel):
    value: Any
    reason: Optional[str] = None


class SystemSettingUpdateResponse(BaseModel):
    key: str
    display_name: str
    category: str
    data_type: str
    previous_value: Any
    value: Any
    source: str
    editable_by_admin: bool
    future_requests_only: bool
    updated_by_user_id: Optional[int] = None
    updated_at: Optional[str] = None
    message: str
