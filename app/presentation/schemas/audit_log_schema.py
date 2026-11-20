"""Safe response schemas for administrative audit-log inspection."""

from typing import Any, Optional

from pydantic import BaseModel


class AuditActorResponse(BaseModel):
    id: Optional[int] = None
    name: str
    email: Optional[str] = None
    kind: str
    employee_number: Optional[str] = None


class AuditTargetResponse(BaseModel):
    entity_type: str
    entity_id: Optional[int] = None
    label: str


class AuditLogItemResponse(BaseModel):
    id: int
    action: str
    actor: AuditActorResponse
    performed_by: Optional[AuditActorResponse] = None
    target: AuditTargetResponse
    created_at: str
    previous_values: Any = None
    current_values: Any = None
    has_details: bool


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItemResponse]
    page: int
    page_size: int
    total: int
    timezone: str
    available_actions: list[str]
    available_entity_types: list[str]
