"""Runtime system settings provider implementation."""

from __future__ import annotations

import json
from typing import Any, Optional

from app.application.use_cases.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.config import get_settings
from app.domain.entities.system_setting import (
    EffectiveSystemSetting,
    SystemSettingDefinition,
    UpdatedSystemSetting,
)
from app.domain.enums.setting_category import SettingCategory
from app.domain.enums.setting_data_type import SettingDataType
from app.domain.enums.setting_source import SettingSource
from app.domain.repositories.system_setting_repository import SystemSettingRepositoryInterface
from app.domain.services.clock_service import ClockInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.domain.services.system_settings_registry import SYSTEM_SETTING_DEFINITIONS


class RuntimeSystemSettingsProvider(SystemSettingsProviderInterface):
    """Resolve safe runtime policies from DB overrides, env settings, and defaults."""

    def __init__(
        self,
        *,
        settings_repo: SystemSettingRepositoryInterface,
        clock: ClockInterface,
    ) -> None:
        self._settings_repo = settings_repo
        self._clock = clock

    def list_effective_settings(
        self,
        *,
        category: Optional[str] = None,
        editable_only: Optional[bool] = None,
    ) -> list[EffectiveSystemSetting]:
        normalized_category = None
        if category is not None:
            normalized_category = category.strip().upper()
            if normalized_category not in {item.value for item in SettingCategory}:
                raise BadRequestError("Invalid system setting category")

        items = []
        for definition in SYSTEM_SETTING_DEFINITIONS.values():
            if normalized_category and definition.category.value != normalized_category:
                continue
            if editable_only is not None and definition.editable_by_admin != editable_only:
                continue
            items.append(self.get_effective_setting(definition.key))
        return sorted(items, key=lambda item: (item.category, item.key))

    def get_effective_setting(self, key: str) -> EffectiveSystemSetting:
        definition = self._definition(key)
        row = self._settings_repo.get_override_by_key(definition.key)
        if row is not None:
            try:
                value = self._coerce_value(definition, self._decode_stored_value(row.value))
            except BadRequestError:
                value = None
            else:
                return self._setting_from_definition(
                    definition,
                    value=value,
                    source=SettingSource.DATABASE,
                    updated_at=row.updated_at,
                    updated_by_user_id=row.updated_by,
                )

        settings = get_settings()
        if definition.env_key and hasattr(settings, definition.env_key):
            value = self._coerce_value(definition, getattr(settings, definition.env_key))
            return self._setting_from_definition(
                definition,
                value=value,
                source=SettingSource.ENV_DEFAULT,
                updated_at=None,
                updated_by_user_id=None,
            )

        return self._setting_from_definition(
            definition,
            value=definition.default_value,
            source=SettingSource.APPLICATION_DEFAULT,
            updated_at=None,
            updated_by_user_id=None,
        )

    def get_boolean(self, key: str) -> bool:
        setting = self.get_effective_setting(key)
        if setting.data_type != SettingDataType.BOOLEAN.value:
            raise BadRequestError(f"{setting.key} is not a boolean setting")
        return bool(setting.value)

    def get_integer(self, key: str) -> int:
        setting = self.get_effective_setting(key)
        if setting.data_type != SettingDataType.INTEGER.value:
            raise BadRequestError(f"{setting.key} is not an integer setting")
        return int(setting.value)

    def get_string(self, key: str) -> str:
        setting = self.get_effective_setting(key)
        if setting.data_type != SettingDataType.STRING.value:
            raise BadRequestError(f"{setting.key} is not a string setting")
        return str(setting.value)

    def update_setting(
        self,
        *,
        key: str,
        raw_value: Any,
        reason: Optional[str],
        actor_user_id: int,
    ) -> UpdatedSystemSetting:
        definition = self._definition(key)
        if not definition.editable_by_admin:
            raise ForbiddenError("This system setting is read-only and cannot be modified through the API.")

        normalized_reason = self._normalize_reason(reason)
        previous = self.get_effective_setting(definition.key)
        value = self._coerce_value(definition, raw_value)
        updated_at = self._clock.now_in_timezone(get_settings().APP_TIMEZONE).replace(tzinfo=None)
        row = self._settings_repo.upsert_override(
            key=definition.key,
            value=json.dumps(value),
            description=definition.description,
            actor_user_id=actor_user_id,
            updated_at=updated_at,
            commit=False,
        )
        current = self._setting_from_definition(
            definition,
            value=value,
            source=SettingSource.DATABASE,
            updated_at=updated_at,
            updated_by_user_id=actor_user_id,
        )
        return UpdatedSystemSetting(
            setting=current,
            previous_value=previous.value,
            previous_source=previous.source,
            reason=normalized_reason,
            database_row_id=getattr(row, "id", None),
        )

    @staticmethod
    def _definition(key: str) -> SystemSettingDefinition:
        normalized_key = key.strip().upper()
        definition = SYSTEM_SETTING_DEFINITIONS.get(normalized_key)
        if definition is None:
            raise NotFoundError("System setting not found.")
        return definition

    @staticmethod
    def _decode_stored_value(value: str) -> Any:
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value

    @staticmethod
    def _normalize_reason(reason: Optional[str]) -> str:
        normalized = reason.strip() if isinstance(reason, str) else ""
        if not normalized:
            return "Updated from System Settings page."
        if len(normalized) < 5 or len(normalized) > 500:
            raise BadRequestError("Update reason must be between 5 and 500 characters.")
        return normalized

    def _coerce_value(self, definition: SystemSettingDefinition, raw_value: Any) -> Any:
        if definition.data_type == SettingDataType.BOOLEAN:
            if isinstance(raw_value, bool):
                return raw_value
            raise BadRequestError(f"{definition.key} must be a boolean value.")

        if definition.data_type == SettingDataType.INTEGER:
            if isinstance(raw_value, bool) or not isinstance(raw_value, int):
                raise BadRequestError(f"{definition.key} must be an integer value.")
            if definition.min_value is not None and raw_value < definition.min_value:
                raise BadRequestError(
                    f"{definition.key} must be between {definition.min_value} and {definition.max_value}."
                )
            if definition.max_value is not None and raw_value > definition.max_value:
                raise BadRequestError(
                    f"{definition.key} must be between {definition.min_value} and {definition.max_value}."
                )
            return raw_value

        if definition.data_type == SettingDataType.STRING:
            if not isinstance(raw_value, str):
                raise BadRequestError(f"{definition.key} must be a string value.")
            normalized = raw_value.strip()
            if definition.min_length is not None and len(normalized) < definition.min_length:
                raise BadRequestError(
                    f"{definition.key} must be between {definition.min_length} and "
                    f"{definition.max_length} characters."
                )
            if definition.max_length is not None and len(normalized) > definition.max_length:
                raise BadRequestError(
                    f"{definition.key} must be between {definition.min_length} and "
                    f"{definition.max_length} characters."
                )
            return normalized

        raise BadRequestError(f"Unsupported data type for {definition.key}.")

    @staticmethod
    def _setting_from_definition(
        definition: SystemSettingDefinition,
        *,
        value: Any,
        source: SettingSource,
        updated_at,
        updated_by_user_id: Optional[int],
    ) -> EffectiveSystemSetting:
        return EffectiveSystemSetting(
            key=definition.key,
            display_name=definition.display_name,
            description=definition.description,
            category=definition.category.value,
            data_type=definition.data_type.value,
            value=value,
            default_value=definition.default_value,
            source=source,
            editable_by_admin=definition.editable_by_admin,
            future_requests_only=definition.future_requests_only,
            updated_at=updated_at,
            updated_by_user_id=updated_by_user_id,
        )
