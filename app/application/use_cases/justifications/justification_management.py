"""Justification request workflow use cases."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Optional

from app.application.dto.justification_request_dto import (
    CreateJustificationRequestDTO,
    GetJustificationRequestDTO,
    GetMyJustificationRequestDTO,
    JustificationRequestListResult,
    ListJustificationRequestsDTO,
    ListMyJustificationRequestsDTO,
    ReviewJustificationRequestDTO,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.config import get_settings
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.request_status import RequestStatus
from app.domain.repositories.attendance_record_repository import AttendanceRecordRepositoryInterface
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.justification_request_repository import (
    JustificationRequestFilters,
    JustificationRequestRepositoryInterface,
)
from app.domain.services.clock_service import ClockInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface


# Defines the allowed justification request types for new submissions.
VALID_REQUEST_TYPES = {"LATE", "EARLY_DEPARTURE", "MISSING_CHECKOUT"}


def _status_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise BadRequestError("Page must be greater than or equal to 1")
    if page_size < 1 or page_size > 100:
        raise BadRequestError("Page size must be between 1 and 100")


def _normalize_request_type(request_type: str) -> str:
    normalized = request_type.strip().upper()
    if normalized not in VALID_REQUEST_TYPES:
        raise BadRequestError("Invalid justification request type")
    return normalized


def _normalize_reason(reason: str, *, min_length: int, max_length: int) -> str:
    normalized = reason.strip()
    if len(normalized) < min_length or len(normalized) > max_length:
        raise BadRequestError(
            f"Reason must be between {min_length} and {max_length} characters"
        )
    return normalized


def _normalize_note(note: Optional[str]) -> Optional[str]:
    if note is None:
        return None
    normalized = note.strip()
    return normalized or None


def _validate_filters(filters: JustificationRequestFilters) -> None:
    if filters.date_from and filters.date_to and filters.date_to < filters.date_from:
        raise BadRequestError("date_to must be greater than or equal to date_from")
    if filters.request_type is not None:
        _normalize_request_type(filters.request_type)
    if filters.status is not None and filters.status not in {status.value for status in RequestStatus}:
        raise BadRequestError("Invalid justification request status")


def _is_eligible_attendance(record, request_type: str) -> bool:
    # Checks whether the attendance record matches the requested justification type.
    status = record.status if isinstance(record.status, AttendanceStatus) else AttendanceStatus(record.status)
    if bool(getattr(record, "is_unscheduled", False)) or status == AttendanceStatus.UNSCHEDULED:
        return False
    if request_type == "LATE":
        return bool(record.is_late) and record.scheduled_start_datetime is not None
    if request_type == "EARLY_DEPARTURE":
        return bool(record.is_early_departure) and record.scheduled_end_datetime is not None
    if request_type == "MISSING_CHECKOUT":
        return (
            (bool(getattr(record, "is_missing_checkout", False)) or status == AttendanceStatus.MISSING_CHECKOUT)
            and record.scheduled_end_datetime is not None
        )
    return False


def _attendance_month_bounds(attendance_date: date) -> tuple[date, date]:
    month_start = attendance_date.replace(day=1)
    if attendance_date.month == 12:
        next_month = date(attendance_date.year + 1, 1, 1)
    else:
        next_month = date(attendance_date.year, attendance_date.month + 1, 1)
    return month_start, next_month - timedelta(days=1)


def _safe_request_values(request) -> dict:
    return {
        "id": request.id,
        "employee_id": request.employee_id,
        "attendance_record_id": request.attendance_record_id,
        "request_type": request.request_type,
        "status": _status_value(request.status),
    }


class CreateJustificationRequest:
    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        attendance_repo: AttendanceRecordRepositoryInterface,
        justification_repo: JustificationRequestRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        settings_provider: Optional[SystemSettingsProviderInterface] = None,
    ) -> None:
        self._employee_repo = employee_repo
        self._attendance_repo = attendance_repo
        self._justification_repo = justification_repo
        self._audit_repo = audit_repo
        self._settings_provider = settings_provider

    def _monthly_limit(self) -> int:
        # Loads the effective monthly justification limit.
        if self._settings_provider is not None:
            return self._settings_provider.get_integer("JUSTIFICATION_MONTHLY_LIMIT")
        return int(get_settings().JUSTIFICATION_MONTHLY_LIMIT)

    def execute(self, request: CreateJustificationRequestDTO):
        settings = get_settings()
        # Loads the authenticated employee and selected attendance record.
        employee = self._employee_repo.get_by_user_id(request.user_id)
        if employee is None:
            raise NotFoundError("Employee profile not found for current user")

        record = self._attendance_repo.get_by_id(request.attendance_record_id)
        if record is None:
            raise NotFoundError("Attendance record not found")
        if record.employee_id != employee.id:
            raise BadRequestError("Employee cannot submit justification for another employee's attendance record")

        request_type = _normalize_request_type(request.request_type)
        if not _is_eligible_attendance(record, request_type):
            raise BadRequestError("Attendance record is not eligible for this justification request")

        # Checks whether this attendance record already has a justification request.
        if self._justification_repo.exists_for_attendance(attendance_record_id=record.id):
            raise ConflictError("A justification request has already been submitted for this attendance record.")

        # Counts this employee's submitted justifications for the attendance month.
        monthly_limit = self._monthly_limit()
        month_start, month_end = _attendance_month_bounds(record.attendance_date)
        monthly_count = self._justification_repo.count_for_employee_attendance_month(
            employee_id=employee.id,
            month_start=month_start,
            month_end=month_end,
        )
        if monthly_count >= monthly_limit:
            raise ConflictError("You have reached the monthly justification limit.")

        # Normalizes the employee's justification reason.
        reason = _normalize_reason(
            request.reason,
            min_length=settings.JUSTIFICATION_MIN_REASON_LENGTH,
            max_length=settings.JUSTIFICATION_MAX_REASON_LENGTH,
        )

        created = self._justification_repo.create(
            employee_id=employee.id,
            attendance_record_id=record.id,
            request_type=request_type,
            reason=reason,
            commit=False,
        )
        # Writes the justification request creation to the audit log.
        self._audit_repo.log(
            actor_user_id=request.user_id,
            action="CREATE_JUSTIFICATION_REQUEST",
            entity_type="JustificationRequest",
            entity_id=created.id,
            new_values=json.dumps(_safe_request_values(created)),
            ip_address=request.ip_address,
        )
        return created


class ListMyJustificationRequests:
    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        justification_repo: JustificationRequestRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._justification_repo = justification_repo

    def execute(self, request: ListMyJustificationRequestsDTO) -> JustificationRequestListResult:
        _validate_pagination(request.page, request.page_size)
        _validate_filters(request.filters)
        employee = self._employee_repo.get_by_user_id(request.user_id)
        if employee is None:
            raise NotFoundError("Employee profile not found for current user")
        return JustificationRequestListResult(
            items=self._justification_repo.list_for_employee(
                employee.id,
                filters=request.filters,
                page=request.page,
                page_size=request.page_size,
            ),
            page=request.page,
            page_size=request.page_size,
            total=self._justification_repo.count_for_employee(
                employee.id,
                filters=request.filters,
            ),
        )


class GetMyJustificationRequest:
    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        justification_repo: JustificationRequestRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._justification_repo = justification_repo

    def execute(self, request: GetMyJustificationRequestDTO):
        employee = self._employee_repo.get_by_user_id(request.user_id)
        if employee is None:
            raise NotFoundError("Employee profile not found for current user")
        item = self._justification_repo.get_by_id(request.request_id)
        if item is None or item.employee_id != employee.id:
            raise NotFoundError("Justification request not found")
        return item


class ListJustificationRequests:
    def __init__(self, justification_repo: JustificationRequestRepositoryInterface) -> None:
        self._justification_repo = justification_repo

    def execute(self, request: ListJustificationRequestsDTO) -> JustificationRequestListResult:
        _validate_pagination(request.page, request.page_size)
        _validate_filters(request.filters)
        return JustificationRequestListResult(
            items=self._justification_repo.list_all(
                filters=request.filters,
                page=request.page,
                page_size=request.page_size,
            ),
            page=request.page,
            page_size=request.page_size,
            total=self._justification_repo.count_all(filters=request.filters),
        )


class GetJustificationRequest:
    def __init__(self, justification_repo: JustificationRequestRepositoryInterface) -> None:
        self._justification_repo = justification_repo

    def execute(self, request: GetJustificationRequestDTO):
        item = self._justification_repo.get_by_id(request.request_id)
        if item is None:
            raise NotFoundError("Justification request not found")
        return item


class _ReviewJustificationBase:
    action = ""
    message = ""

    def __init__(
        self,
        *,
        justification_repo: JustificationRequestRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        clock: ClockInterface,
    ) -> None:
        self._justification_repo = justification_repo
        self._audit_repo = audit_repo
        self._clock = clock

    def _review(self, request: ReviewJustificationRequestDTO, *, approve: bool):
        settings = get_settings()
        item = self._justification_repo.get_by_id(request.request_id)
        if item is None:
            raise NotFoundError("Justification request not found")
        if item.status != RequestStatus.PENDING:
            raise BadRequestError("Only pending justification requests may be reviewed")

        # Applies the admin review decision to the pending justification request.
        reviewed_at = self._clock.now_in_timezone(settings.APP_TIMEZONE).replace(tzinfo=None)
        old_values = _safe_request_values(item)
        if approve:
            updated = self._justification_repo.approve(
                request_id=item.id,
                reviewer_user_id=request.reviewer_user_id,
                reviewer_note=_normalize_note(request.reviewer_note),
                reviewed_at=reviewed_at,
                commit=False,
            )
        else:
            updated = self._justification_repo.reject(
                request_id=item.id,
                reviewer_user_id=request.reviewer_user_id,
                reviewer_note=_normalize_note(request.reviewer_note),
                reviewed_at=reviewed_at,
                commit=False,
            )

        self._audit_repo.log(
            actor_user_id=request.reviewer_user_id,
            action=self.action,
            entity_type="JustificationRequest",
            entity_id=item.id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_safe_request_values(updated)),
            ip_address=request.ip_address,
        )
        return updated


class ApproveJustificationRequest(_ReviewJustificationBase):
    action = "APPROVE_JUSTIFICATION_REQUEST"

    def execute(self, request: ReviewJustificationRequestDTO):
        return self._review(request, approve=True)


class RejectJustificationRequest(_ReviewJustificationBase):
    action = "REJECT_JUSTIFICATION_REQUEST"

    def execute(self, request: ReviewJustificationRequestDTO):
        return self._review(request, approve=False)
