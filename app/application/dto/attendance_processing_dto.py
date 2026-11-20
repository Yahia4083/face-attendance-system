"""DTOs for daily attendance processing."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ProcessDailyAttendanceRequest:
    on_date: date
    actor_user_id: int | None
    ip_address: str | None = None
    is_automatic: bool = False


@dataclass(frozen=True)
class ProcessDailyAttendanceResult:
    on_date: date
    timezone: str
    processed_assignments: int
    absent_records_created: int
    missing_checkout_records_updated: int
    already_processed_or_unchanged: int
    message: str
