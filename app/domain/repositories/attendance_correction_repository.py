"""Attendance correction repository contract."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class AttendanceCorrectionRepositoryInterface(ABC):
    """Persistence operations for administrative attendance corrections."""

    @abstractmethod
    def create(
        self,
        *,
        attendance_record_id: int,
        original_status: str,
        corrected_status: str,
        reason: str,
        corrected_by_user_id: int,
        corrected_at: datetime,
        commit: bool = True,
    ) -> Any:
        """Create an administrative correction record."""
        raise NotImplementedError

    @abstractmethod
    def list_for_attendance(self, attendance_record_id: int) -> list[Any]:
        """Return correction history for one attendance record."""
        raise NotImplementedError
