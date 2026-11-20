"""Dashboard domain data contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class DashboardDepartmentSnapshot:
    """Active department row used by dashboard department summaries."""

    department_id: int
    department_name: str
    active_employee_count: int


@dataclass(frozen=True)
class PendingDashboardRequest:
    """Safe unified pending request row for the admin dashboard queue."""

    request_category: str
    request_id: int
    employee_id: int
    employee_name: Optional[str]
    employee_number: Optional[str]
    attendance_record_id: int
    attendance_status: Optional[str]
    request_type: Optional[str]
    reason: Optional[str]
    requested_minutes: Optional[int]
    eligible_minutes_at_submission: Optional[int]
    status: str
    created_at: Optional[datetime]


@dataclass(frozen=True)
class DashboardActivity:
    """Safe dashboard activity item derived from allowlisted audit actions."""

    activity_type: str
    employee_id: Optional[int]
    employee_name: Optional[str]
    description: str
    occurred_at: Optional[datetime]
    related_entity_type: str
    related_entity_id: Optional[int]
