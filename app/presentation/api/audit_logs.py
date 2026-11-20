"""ADMIN-only, read-only audit-log API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.dto.audit_log_dto import ListAuditLogsRequest
from app.application.use_cases.audit_logs.list_audit_logs import ListAuditLogs
from app.application.use_cases.exceptions import BadRequestError
from app.config import get_settings
from app.dependencies import get_audit_repository
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.infrastructure.security.permissions import require_admin
from app.presentation.schemas.audit_log_schema import (
    AuditActorResponse,
    AuditLogItemResponse,
    AuditLogListResponse,
    AuditTargetResponse,
)
from app.shared.datetime_utils import utc_to_local_isoformat


router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    action: Optional[str] = None,
    actor: Optional[str] = None,
    entity_type: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
    current_admin=Depends(require_admin),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    """Return existing audit history without modifying it or logging the read."""

    timezone_name = get_settings().APP_TIMEZONE
    try:
        result = ListAuditLogs(audit_repo, timezone_name=timezone_name).execute(
            ListAuditLogsRequest(
                date_from=date_from,
                date_to=date_to,
                action=action,
                actor=actor,
                entity_type=entity_type,
                page=page,
                page_size=page_size,
            )
        )
    except BadRequestError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))

    return AuditLogListResponse(
        items=[
            AuditLogItemResponse(
                id=item.id,
                action=item.action,
                actor=AuditActorResponse(**item.actor.__dict__),
                performed_by=(
                    AuditActorResponse(**item.performed_by.__dict__)
                    if item.performed_by is not None
                    else None
                ),
                target=AuditTargetResponse(**item.target.__dict__),
                created_at=utc_to_local_isoformat(item.created_at, timezone_name),
                previous_values=item.previous_values,
                current_values=item.current_values,
                has_details=item.has_details,
            )
            for item in result.items
        ],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        timezone=result.timezone,
        available_actions=result.available_actions,
        available_entity_types=result.available_entity_types,
    )
