"""System settings management use cases."""

from __future__ import annotations

import json

from app.application.dto.system_setting_dto import (
    GetSystemSettingDTO,
    ListSystemSettingsDTO,
    UpdateSystemSettingDTO,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface


class ListSystemSettings:
    """Return safe allowlisted effective settings."""

    def __init__(self, settings_provider: SystemSettingsProviderInterface) -> None:
        self._settings_provider = settings_provider

    def execute(self, request: ListSystemSettingsDTO):
        # Lists safe allowlisted effective settings.
        return self._settings_provider.list_effective_settings(
            category=request.category,
            editable_only=request.editable_only,
        )


class GetSystemSetting:
    """Return one safe allowlisted effective setting."""

    def __init__(self, settings_provider: SystemSettingsProviderInterface) -> None:
        self._settings_provider = settings_provider

    def execute(self, request: GetSystemSettingDTO):
        # Loads one safe allowlisted setting by key.
        return self._settings_provider.get_effective_setting(request.key)


class UpdateSystemSetting:
    """Update an editable runtime setting override and audit the change."""

    def __init__(
        self,
        *,
        settings_provider: SystemSettingsProviderInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._settings_provider = settings_provider
        self._audit_repo = audit_repo

    def execute(self, request: UpdateSystemSettingDTO):
        # Updates an editable setting override in the database.
        updated = self._settings_provider.update_setting(
            key=request.key,
            raw_value=request.value,
            reason=request.reason,
            actor_user_id=request.actor_user_id,
        )

        # Writes the system-setting update to the audit log.
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="UPDATE_SYSTEM_SETTING",
            entity_type="SystemSetting",
            entity_id=updated.database_row_id,
            old_values=json.dumps(
                {
                    "key": updated.setting.key,
                    "value": updated.previous_value,
                    "source": updated.previous_source.value,
                }
            ),
            new_values=json.dumps(
                {
                    "key": updated.setting.key,
                    "value": updated.setting.value,
                    "source": updated.setting.source.value,
                    "reason": updated.reason,
                }
            ),
            ip_address=request.ip_address,
        )
        return updated
