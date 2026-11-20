"""System setting domain contracts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from app.domain.enums.setting_category import SettingCategory
from app.domain.enums.setting_data_type import SettingDataType
from app.domain.enums.setting_source import SettingSource


@dataclass(frozen=True)
class SystemSettingDefinition:
    """Allowlisted setting metadata and validation constraints."""

    key: str
    display_name: str
    description: str
    category: SettingCategory
    data_type: SettingDataType
    default_value: Any
    editable_by_admin: bool
    future_requests_only: bool = True
    env_key: Optional[str] = None
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None


@dataclass(frozen=True)
class EffectiveSystemSetting:
    """Resolved setting value safe to expose via the settings API."""

    key: str
    display_name: str
    description: str
    category: str
    data_type: str
    value: Any
    default_value: Any
    source: SettingSource
    editable_by_admin: bool
    future_requests_only: bool
    updated_at: Optional[datetime] = None
    updated_by_user_id: Optional[int] = None


@dataclass(frozen=True)
class UpdatedSystemSetting:
    """Result of a successful editable setting update."""

    setting: EffectiveSystemSetting
    previous_value: Any
    previous_source: SettingSource
    reason: str
    database_row_id: Optional[int]
