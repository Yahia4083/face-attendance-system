"""Runtime system settings provider contract."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from app.domain.entities.system_setting import EffectiveSystemSetting, UpdatedSystemSetting


class SystemSettingsProviderInterface(ABC):
    """Resolve and update allowlisted runtime policy settings."""

    @abstractmethod
    def list_effective_settings(
        self,
        *,
        category: Optional[str] = None,
        editable_only: Optional[bool] = None,
    ) -> list[EffectiveSystemSetting]:
        raise NotImplementedError

    @abstractmethod
    def get_effective_setting(self, key: str) -> EffectiveSystemSetting:
        raise NotImplementedError

    @abstractmethod
    def get_boolean(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_integer(self, key: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_string(self, key: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def update_setting(
        self,
        *,
        key: str,
        raw_value: Any,
        reason: Optional[str],
        actor_user_id: int,
    ) -> UpdatedSystemSetting:
        raise NotImplementedError
