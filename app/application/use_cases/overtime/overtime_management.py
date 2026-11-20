"""Overtime request workflow use cases."""

from __future__ import annotations

import json
from typing import Optional

from app.application.dto.overtime_request_dto import (
    ApproveOvertimeRequestDTO,
    CreateOvertimeRequestDTO,
    GetMyOvertimeRequestDTO,
    GetOvertimeRequestDTO,
    ListMyOvertimeRequestsDTO,
    ListOvertimeRequestsDTO,
    OvertimeRequestListResult,
    RejectOvertimeRequestDTO,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.config import get_settings
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.enums.overtime_status import OvertimeStatus
from app.domain.repositories.attendance_record_repository import AttendanceRecordRepositoryInterface
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.overtime_request_repository import (
    OvertimeRequestFilters,
    OvertimeRequestRepositoryInterface,
)
from app.domain.services.clock_service import ClockInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface


def _status_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise BadRequestError("Page must be greater than or equal to 1")
    if page_size < 1 or page_size > 100:
        raise BadRequestError("Page size must be between 1 and 100")


def _validate_filters(filters: OvertimeRequestFilters) -> None:
    if filters.date_from and filters.date_to and filters.date_to < filters.date_from:
        raise BadRequestError("date_to must be greater than or equal to date_from")
    if filters.status is not None and filters.status not in {status.value for status in OvertimeStatus}:
        raise BadRequestError("Invalid overtime request status")


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


def _eligible_overtime_minutes(record) -> int:
    # Calculates eligible overtime minutes for a scheduled attendance record.
    if record.scheduled_end_datetime is None:
        raise BadRequestError("Attendance record is not eligible for overtime")
    if record.check_out_time is None:
        raise BadRequestError("Attendance record has no check-out time")
    status = record.status if isinstance(record.status, AttendanceStatus) else AttendanceStatus(record.status)
    if status == AttendanceStatus.ABSENT:
        raise BadRequestError("Absent attendance records are not eligible for overtime")
    if bool(record.is_unscheduled):
        raise BadRequestError("Unscheduled attendance records are not eligible for overtime")
    delta_minutes = int((record.check_out_time - record.scheduled_end_datetime).total_seconds() // 60)
    if delta_minutes <= 0:
        raise BadRequestError("Attendance record does not contain eligible overtime")
    return delta_minutes


def _safe_request_values(request) -> dict:
    return {
        "id": request.id,
        "employee_id": request.employee_id,
        "attendance_record_id": request.attendance_record_id,
        "requested_minutes": request.overtime_minutes,
        "eligible_minutes_at_submission": request.eligible_minutes_at_submission,
        "approved_minutes": request.approved_minutes,
        "status": _status_value(request.status),
    }


class CreateOvertimeRequest:
    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        attendance_repo: AttendanceRecordRepositoryInterface,
        overtime_repo: OvertimeRequestRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        settings_provider: Optional[SystemSettingsProviderInterface] = None,
    ) -> None:
        self._employee_repo = employee_repo
        self._attendance_repo = attendance_repo
        self._overtime_repo = overtime_repo
        self._audit_repo = audit_repo
        self._settings_provider = settings_provider

    def execute(self, request: CreateOvertimeRequestDTO):
        settings = get_settings()
        # Loads the authenticated employee and selected attendance record.
        employee = self._employee_repo.get_by_user_id(request.user_id)
        if employee is None:
            raise NotFoundError("Employee profile not found for current user")
        record = self._attendance_repo.get_by_id(request.attendance_record_id)
        if record is None:
            raise NotFoundError("Attendance record not found")
        if record.employee_id != employee.id:
            raise BadRequestError("Employee cannot request overtime for another employee's attendance record")

        eligible_minutes = _eligible_overtime_minutes(record)
        # Loads the effective overtime minimum-minute policy.
        overtime_minimum = (
            self._settings_provider.get_integer("OVERTIME_MINIMUM_MINUTES")
            if self._settings_provider is not None
            else settings.OVERTIME_MINIMUM_MINUTES
        )
        if eligible_minutes < overtime_minimum:
            raise BadRequestError("Eligible overtime is below the configured minimum minutes")
        if request.requested_minutes <= 0:
            raise BadRequestError("Requested overtime minutes must be greater than zero")
        if request.requested_minutes > eligible_minutes:
            raise BadRequestError("Requested overtime minutes exceed eligible overtime")
        # Normalizes the overtime request reason.
        reason = _normalize_reason(
            request.reason,
            min_length=settings.OVERTIME_MIN_REASON_LENGTH,
            max_length=settings.OVERTIME_MAX_REASON_LENGTH,
        )
        # Checks for existing pending or approved overtime requests.
        if self._overtime_repo.has_pending_for_attendance(attendance_record_id=record.id):
            raise ConflictError("A pending overtime request already exists for this attendance record.")
        if self._overtime_repo.has_approved_for_attendance(attendance_record_id=record.id):
            raise ConflictError("An approved overtime request already exists for this attendance record.")

        created = self._overtime_repo.create(
            employee_id=employee.id,
            attendance_record_id=record.id,
            requested_minutes=request.requested_minutes,
            eligible_minutes_at_submission=eligible_minutes,
            reason=reason,
            commit=False,
        )
        # Writes the overtime request creation to the audit log.
        self._audit_repo.log(
            actor_user_id=request.user_id,
            action="CREATE_OVERTIME_REQUEST",
            entity_type="OvertimeRequest",
            entity_id=created.id,
            new_values=json.dumps(_safe_request_values(created)),
            ip_address=request.ip_address,
        )
        return created


class ListMyOvertimeRequests:
    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        overtime_repo: OvertimeRequestRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._overtime_repo = overtime_repo

    def execute(self, request: ListMyOvertimeRequestsDTO) -> OvertimeRequestListResult:
        _validate_pagination(request.page, request.page_size)
        _validate_filters(request.filters)
        employee = self._employee_repo.get_by_user_id(request.user_id)
        if employee is None:
            raise NotFoundError("Employee profile not found for current user")
        return OvertimeRequestListResult(
            items=self._overtime_repo.list_for_employee(
                employee.id,
                filters=request.filters,
                page=request.page,
                page_size=request.page_size,
            ),
            page=request.page,
            page_size=request.page_size,
            total=self._overtime_repo.count_for_employee(employee.id, filters=request.filters),
        )


class GetMyOvertimeRequest:
    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        overtime_repo: OvertimeRequestRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._overtime_repo = overtime_repo

    def execute(self, request: GetMyOvertimeRequestDTO):
        employee = self._employee_repo.get_by_user_id(request.user_id)
        if employee is None:
            raise NotFoundError("Employee profile not found for current user")
        item = self._overtime_repo.get_by_id(request.request_id)
        if item is None or item.employee_id != employee.id:
            raise NotFoundError("Overtime request not found")
        return item


class ListOvertimeRequests:
    def __init__(self, overtime_repo: OvertimeRequestRepositoryInterface) -> None:
        self._overtime_repo = overtime_repo

    def execute(self, request: ListOvertimeRequestsDTO) -> OvertimeRequestListResult:
        _validate_pagination(request.page, request.page_size)
        _validate_filters(request.filters)
        return OvertimeRequestListResult(
            items=self._overtime_repo.list_all(
                filters=request.filters,
                page=request.page,
                page_size=request.page_size,
            ),
            page=request.page,
            page_size=request.page_size,
            total=self._overtime_repo.count_all(filters=request.filters),
        )


class GetOvertimeRequest:
    def __init__(self, overtime_repo: OvertimeRequestRepositoryInterface) -> None:
        self._overtime_repo = overtime_repo

    def execute(self, request: GetOvertimeRequestDTO):
        item = self._overtime_repo.get_by_id(request.request_id)
        if item is None:
            raise NotFoundError("Overtime request not found")
        return item


class ApproveOvertimeRequest:
    def __init__(
        self,
        *,
        overtime_repo: OvertimeRequestRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        clock: ClockInterface,
    ) -> None:
        self._overtime_repo = overtime_repo
        self._audit_repo = audit_repo
        self._clock = clock

    def execute(self, request: ApproveOvertimeRequestDTO):
        settings = get_settings()
        item = self._overtime_repo.get_by_id(request.request_id)
        if item is None:
            raise NotFoundError("Overtime request not found")
        if item.status != OvertimeStatus.PENDING:
            raise BadRequestError("Only pending overtime requests may be reviewed")
        if request.approved_minutes <= 0:
            raise BadRequestError("Approved overtime minutes must be greater than zero")
        if request.approved_minutes > item.overtime_minutes:
            raise BadRequestError("Approved overtime minutes must not exceed requested minutes")
        if request.approved_minutes > item.eligible_minutes_at_submission:
            raise BadRequestError("Approved overtime minutes must not exceed eligible overtime")

        # Approves a pending overtime request with approved minutes.
        old_values = _safe_request_values(item)
        reviewed_at = self._clock.now_in_timezone(settings.APP_TIMEZONE).replace(tzinfo=None)
        updated = self._overtime_repo.approve(
            request_id=item.id,
            approved_minutes=request.approved_minutes,
            reviewer_user_id=request.reviewer_user_id,
            reviewer_note=_normalize_note(request.reviewer_note),
            reviewed_at=reviewed_at,
            commit=False,
        )
        self._audit_repo.log(
            actor_user_id=request.reviewer_user_id,
            action="APPROVE_OVERTIME_REQUEST",
            entity_type="OvertimeRequest",
            entity_id=item.id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_safe_request_values(updated)),
            ip_address=request.ip_address,
        )
        return updated


class RejectOvertimeRequest:
    def __init__(
        self,
        *,
        overtime_repo: OvertimeRequestRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        clock: ClockInterface,
    ) -> None:
        self._overtime_repo = overtime_repo
        self._audit_repo = audit_repo
        self._clock = clock

    def execute(self, request: RejectOvertimeRequestDTO):
        settings = get_settings()
        item = self._overtime_repo.get_by_id(request.request_id)
        if item is None:
            raise NotFoundError("Overtime request not found")
        if item.status != OvertimeStatus.PENDING:
            raise BadRequestError("Only pending overtime requests may be reviewed")

        # Rejects a pending overtime request.
        old_values = _safe_request_values(item)
        reviewed_at = self._clock.now_in_timezone(settings.APP_TIMEZONE).replace(tzinfo=None)
        updated = self._overtime_repo.reject(
            request_id=item.id,
            reviewer_user_id=request.reviewer_user_id,
            reviewer_note=_normalize_note(request.reviewer_note),
            reviewed_at=reviewed_at,
            commit=False,
        )
        self._audit_repo.log(
            actor_user_id=request.reviewer_user_id,
            action="REJECT_OVERTIME_REQUEST",
            entity_type="OvertimeRequest",
            entity_id=item.id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(_safe_request_values(updated)),
            ip_address=request.ip_address,
        )
        return updated
