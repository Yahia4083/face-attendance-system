"""Read models for safe audit-log inspection."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class AuditLogRecord:
    """Represent one stored audit event with safe actor display data."""

    id: int
    actor_user_id: Optional[int]
    actor_email: Optional[str]
    actor_name: Optional[str]
    actor_role: Optional[str]
    action: str
    entity_type: str
    entity_id: Optional[int]
    old_values: Optional[str]
    new_values: Optional[str]
    created_at: datetime
    subject_user_id: Optional[int] = None
    subject_email: Optional[str] = None
    subject_name: Optional[str] = None
    subject_employee_number: Optional[str] = None
