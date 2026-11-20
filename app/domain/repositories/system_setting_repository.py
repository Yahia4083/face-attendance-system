"""System setting repository contract."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional


class SystemSettingRepositoryInterface(ABC):
    """Persistence operations for safe system setting overrides."""

    @abstractmethod
    def get_override_by_key(self, key: str) -> Optional[Any]:
        """Return a stored override row by setting key."""
        raise NotImplementedError

    @abstractmethod
    def list_overrides(self) -> list[Any]:
        """Return all stored override rows."""
        raise NotImplementedError

    @abstractmethod
    def upsert_override(
        self,
        *,
        key: str,
        value: str,
        description: Optional[str],
        actor_user_id: int,
        updated_at: datetime,
        commit: bool = True,
    ) -> Any:
        """Create or update a stored setting override."""
        raise NotImplementedError
