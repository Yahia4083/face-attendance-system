"""System settings API routes."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.dto.system_setting_dto import (
    GetSystemSettingDTO,
    ListSystemSettingsDTO,
    UpdateSystemSettingDTO,
)
from app.application.use_cases.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.application.use_cases.settings.system_setting_management import (
    GetSystemSetting,
    ListSystemSettings,
    UpdateSystemSetting,
)
from app.config import get_settings
from app.dependencies import get_audit_repository, get_system_settings_provider
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.infrastructure.security.permissions import require_admin
from app.presentation.schemas.system_setting_schema import (
    SystemSettingListResponse,
    SystemSettingResponse,
    SystemSettingUpdateRequest,
    SystemSettingUpdateResponse,
)
from app.shared.datetime_utils import local_isoformat

router = APIRouter(tags=["System Settings"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ForbiddenError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


def _setting_response(setting) -> SystemSettingResponse:
    timezone_name = get_settings().APP_TIMEZONE
    return SystemSettingResponse(
        key=setting.key,
        display_name=setting.display_name,
        description=setting.description,
        category=setting.category,
        data_type=setting.data_type,
        value=setting.value,
        default_value=setting.default_value,
        source=setting.source.value if hasattr(setting.source, "value") else str(setting.source),
        editable_by_admin=setting.editable_by_admin,
        future_requests_only=setting.future_requests_only,
        updated_at=local_isoformat(setting.updated_at, timezone_name),
        updated_by_user_id=setting.updated_by_user_id,
    )


@router.get("/system-settings", response_model=SystemSettingListResponse)
def list_system_settings(
    category: Optional[str] = None,
    editable_only: Optional[bool] = None,
    current_admin=Depends(require_admin),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = ListSystemSettings(settings_provider)
    try:
        items = use_case.execute(
            ListSystemSettingsDTO(category=category, editable_only=editable_only)
        )
    except (BadRequestError, ConflictError, ForbiddenError, NotFoundError) as error:
        _raise_http_error(error)
    return SystemSettingListResponse(items=[_setting_response(item) for item in items])


@router.get("/system-settings/{key}", response_model=SystemSettingResponse)
def get_system_setting(
    key: str,
    current_admin=Depends(require_admin),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = GetSystemSetting(settings_provider)
    try:
        item = use_case.execute(GetSystemSettingDTO(key=key))
    except (BadRequestError, ConflictError, ForbiddenError, NotFoundError) as error:
        _raise_http_error(error)
    return _setting_response(item)


@router.put("/system-settings/{key}", response_model=SystemSettingUpdateResponse)
def update_system_setting(
    key: str,
    payload: SystemSettingUpdateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = UpdateSystemSetting(
        settings_provider=settings_provider,
        audit_repo=audit_repo,
    )
    try:
        result = use_case.execute(
            UpdateSystemSettingDTO(
                key=key,
                value=payload.value,
                reason=payload.reason,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, ForbiddenError, NotFoundError) as error:
        _raise_http_error(error)

    setting = result.setting
    return SystemSettingUpdateResponse(
        key=setting.key,
        display_name=setting.display_name,
        category=setting.category,
        data_type=setting.data_type,
        previous_value=result.previous_value,
        value=setting.value,
        source=setting.source.value if hasattr(setting.source, "value") else str(setting.source),
        editable_by_admin=setting.editable_by_admin,
        future_requests_only=setting.future_requests_only,
        updated_by_user_id=setting.updated_by_user_id,
        updated_at=local_isoformat(setting.updated_at, get_settings().APP_TIMEZONE),
        message="System setting updated successfully",
    )
