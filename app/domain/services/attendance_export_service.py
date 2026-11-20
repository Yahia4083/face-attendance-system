"""Attendance export service contracts."""

from abc import ABC, abstractmethod
from typing import Any


class AttendanceExportServiceInterface(ABC):
    """Create downloadable attendance report files from safe report data."""

    @abstractmethod
    def build_csv(
        self,
        *,
        rows: list[Any],
        summary: Any,
        metadata: dict[str, Any],
    ) -> bytes:
        """Return CSV bytes."""
        raise NotImplementedError

    @abstractmethod
    def build_xlsx(
        self,
        *,
        rows: list[Any],
        summary: Any,
        metadata: dict[str, Any],
    ) -> bytes:
        """Return XLSX bytes."""
        raise NotImplementedError
