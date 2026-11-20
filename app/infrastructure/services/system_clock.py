"""System clock implementation."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.domain.services.clock_service import ClockInterface


class SystemClock(ClockInterface):
    """Clock implementation backed by the operating system time."""

    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def now_in_timezone(self, timezone_name: str) -> datetime:
        return self.now_utc().astimezone(ZoneInfo(timezone_name))
