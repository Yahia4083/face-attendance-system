"""Clock service contract."""

from abc import ABC, abstractmethod
from datetime import datetime


class ClockInterface(ABC):
    """Abstraction for deterministic time-dependent use cases."""

    @abstractmethod
    def now_utc(self) -> datetime:
        """Return the current UTC datetime."""
        raise NotImplementedError

    @abstractmethod
    def now_in_timezone(self, timezone_name: str) -> datetime:
        """Return the current datetime in the requested timezone."""
        raise NotImplementedError
