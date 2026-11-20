"""Read-only use case for the administrative audit-log page."""

from __future__ import annotations

import re
from datetime import UTC, datetime, time, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.application.dto.audit_log_dto import (
    AuditActorDTO,
    AuditLogItemDTO,
    AuditLogListResult,
    AuditTargetDTO,
    ListAuditLogsRequest,
)
from app.application.use_cases.exceptions import BadRequestError
from app.domain.entities.audit_log import AuditLogRecord
from app.domain.repositories.audit_repository import AuditLogFilters, AuditRepositoryInterface
from app.domain.services.audit_log_sanitizer import parse_and_sanitize_audit_json


def _optional_text(value: Optional[str]) -> Optional[str]:
    normalized = value.strip() if value else ""
    return normalized or None


def _utc_boundary(value, timezone_name: str) -> datetime:
    local_value = datetime.combine(value, time.min, tzinfo=ZoneInfo(timezone_name))
    return local_value.astimezone(UTC).replace(tzinfo=None)


def _humanize_identifier(value: str) -> str:
    expanded = re.sub(r"(?<!^)(?=[A-Z])", " ", value).replace("_", " ")
    return " ".join(expanded.split()).title()


def _metadata_value(payload: Any, *keys: str) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value is not None and not isinstance(value, (dict, list)):
            return str(value)
    return None


def _target_label(
    record: AuditLogRecord,
    previous_values: Any,
    current_values: Any,
) -> str:
    payloads = (current_values, previous_values)
    entity_name = _humanize_identifier(record.entity_type)

    preferred_keys: tuple[str, ...]
    if record.entity_type == "Employee":
        preferred_keys = ("employee_number", "full_name")
    elif record.entity_type in {"Department", "ScheduleTemplate"}:
        preferred_keys = ("name",)
    elif record.entity_type == "SystemSetting":
        preferred_keys = ("key",)
    elif record.entity_type == "User":
        preferred_keys = ("email",)
    else:
        preferred_keys = ()

    for payload in payloads:
        display_value = _metadata_value(payload, *preferred_keys)
        if display_value:
            return f"{entity_name} - {display_value}"

    if record.entity_id is not None:
        return f"{entity_name} #{record.entity_id}"
    return entity_name


def _actor(record: AuditLogRecord) -> AuditActorDTO:
    if record.actor_user_id is None:
        return AuditActorDTO(id=None, name="System", email=None, kind="SYSTEM")
    if not record.actor_email:
        return AuditActorDTO(
            id=record.actor_user_id,
            name="Unknown user",
            email=None,
            kind="UNKNOWN",
        )

    role = (record.actor_role or "").upper()
    fallback_name = "Administrator" if role == "ADMIN" else "User"
    return AuditActorDTO(
        id=record.actor_user_id,
        name=record.actor_name or fallback_name,
        email=record.actor_email,
        kind="USER",
    )


def _performed_by(record: AuditLogRecord, current_values: Any) -> Optional[AuditActorDTO]:
    """Identify the employee who physically completed a live kiosk attendance event."""

    if record.action in {"LIVENESS_VERIFICATION_FAILED", "LIVE_ATTENDANCE_REJECTED"}:
        return AuditActorDTO(
            id=None,
            name="Live kiosk terminal",
            email=None,
            kind="SYSTEM",
        )
    if record.action not in {"ATTENDANCE_CHECK_IN", "ATTENDANCE_CHECK_OUT"}:
        return None
    if _metadata_value(current_values, "source") != "LIVE_KIOSK":
        return None
    if record.subject_name is None and record.subject_user_id is None:
        return None
    return AuditActorDTO(
        id=record.subject_user_id,
        name=record.subject_name or "Recognized employee",
        email=record.subject_email,
        kind="EMPLOYEE",
        employee_number=record.subject_employee_number,
    )


class ListAuditLogs:
    """Return sanitized existing audit history without creating read-audit noise."""

    def __init__(
        self,
        audit_repo: AuditRepositoryInterface,
        *,
        timezone_name: str,
    ) -> None:
        self._audit_repo = audit_repo
        self._timezone_name = timezone_name

    def execute(self, request: ListAuditLogsRequest) -> AuditLogListResult:
        if request.page < 1:
            raise BadRequestError("page must be greater than or equal to 1.")
        if request.page_size < 1 or request.page_size > 100:
            raise BadRequestError("page_size must be between 1 and 100.")
        if request.date_from and request.date_to and request.date_from > request.date_to:
            raise BadRequestError("Start date cannot be later than end date.")

        actor_query = _optional_text(request.actor)
        if actor_query and len(actor_query) > 255:
            raise BadRequestError("Performed by search must be 255 characters or fewer.")

        filters = AuditLogFilters(
            created_from_utc=(
                _utc_boundary(request.date_from, self._timezone_name)
                if request.date_from
                else None
            ),
            created_to_utc_exclusive=(
                _utc_boundary(request.date_to + timedelta(days=1), self._timezone_name)
                if request.date_to
                else None
            ),
            actor_query=actor_query,
            action=_optional_text(request.action),
            entity_type=_optional_text(request.entity_type),
        )

        records = self._audit_repo.list_logs(
            filters=filters,
            page=request.page,
            page_size=request.page_size,
        )
        total = self._audit_repo.count_logs(filters=filters)

        items: list[AuditLogItemDTO] = []
        for record in records:
            previous_values = parse_and_sanitize_audit_json(record.old_values)
            current_values = parse_and_sanitize_audit_json(record.new_values)
            items.append(
                AuditLogItemDTO(
                    id=record.id,
                    action=record.action,
                    actor=_actor(record),
                    performed_by=_performed_by(record, current_values),
                    target=AuditTargetDTO(
                        entity_type=record.entity_type,
                        entity_id=record.entity_id,
                        label=_target_label(record, previous_values, current_values),
                    ),
                    created_at=record.created_at,
                    previous_values=previous_values,
                    current_values=current_values,
                    has_details=previous_values is not None or current_values is not None,
                )
            )

        return AuditLogListResult(
            items=items,
            page=request.page,
            page_size=request.page_size,
            total=total,
            timezone=self._timezone_name,
            available_actions=self._audit_repo.list_actions(),
            available_entity_types=self._audit_repo.list_entity_types(),
        )
