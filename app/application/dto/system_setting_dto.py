"""DTOs for system settings use cases."""

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ListSystemSettingsDTO:
    category: Optional[str] = None
    editable_only: Optional[bool] = None


@dataclass(frozen=True)
class GetSystemSettingDTO:
    key: str


@dataclass(frozen=True)
class UpdateSystemSettingDTO:
    key: str
    value: Any
    reason: Optional[str]
    actor_user_id: int
    ip_address: Optional[str] = None
