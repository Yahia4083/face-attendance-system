"""Face-recognition attendance use cases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
from typing import Optional

from app.application.dto.attendance_dto import (
    AttendanceEventResult,
    AttendanceFaceRequest,
    AttendanceListRequest,
    AttendanceListResult,
    CreateAttendanceCorrectionRequest,
    EmployeeAttendanceListRequest,
    GetAttendanceRecordRequest,
    ListAttendanceCorrectionsRequest,
    MyAttendanceListRequest,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.config import get_settings
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.repositories.attendance_record_repository import (
    AttendanceRecordFilters,
    AttendanceRecordRepositoryInterface,
)
from app.domain.repositories.attendance_correction_repository import (
    AttendanceCorrectionRepositoryInterface,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.employee_schedule_repository import EmployeeScheduleRepositoryInterface
from app.domain.services.clock_service import ClockInterface
from app.domain.services.face_recognition_service import (
    FaceRecognitionResult,
    FaceRecognitionServiceInterface,
)
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface


@dataclass(frozen=True)
class _ResolvedSchedule:
    assignment_id: int
    schedule_template_id: int
    schedule_template_name: str
    schedule_date: date
    scheduled_start_datetime: datetime
    scheduled_end_datetime: datetime
    check_in_grace_minutes: int
    early_departure_tolerance_minutes: int
    is_overnight: bool


def _status_to_value(status: object) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _working_days_from_assignment(assignment) -> list[int]:
    value = assignment.working_days or ""
    return [int(day) for day in value.split(",") if day != ""]


def _serialize_record(record) -> dict:
    # Builds a safe attendance snapshot for audit log entries.
    employee = getattr(record, "employee", None)
    template = getattr(record, "schedule_template", None)
    return {
        "id": record.id,
        "employee_id": record.employee_id,
        "employee_name": employee.full_name if employee else None,
        "employee_number": employee.employee_number if employee else None,
        "employee_schedule_id": record.employee_schedule_id,
        "schedule_template_id": record.schedule_template_id,
        "schedule_template_name": template.name if template else None,
        "schedule_date": record.attendance_date.isoformat(),
        "scheduled_start_datetime": record.scheduled_start_datetime.isoformat()
        if record.scheduled_start_datetime
        else None,
        "scheduled_end_datetime": record.scheduled_end_datetime.isoformat()
        if record.scheduled_end_datetime
        else None,
        "check_in_at": record.check_in_time.isoformat() if record.check_in_time else None,
        "check_out_at": record.check_out_time.isoformat() if record.check_out_time else None,
        "status": _status_to_value(record.status),
        "is_late": bool(record.is_late),
        "is_early_departure": bool(record.is_early_departure),
        "is_unscheduled": bool(record.is_unscheduled),
        "is_missing_checkout": bool(getattr(record, "is_missing_checkout", False)),
        "recognition_model_name": record.recognition_model_name,
        "detector_backend": record.detector_backend,
    }


def _validate_pagination(page: int, page_size: int) -> None:
    if page < 1:
        raise BadRequestError("Page must be greater than or equal to 1")
    if page_size < 1 or page_size > 100:
        raise BadRequestError("Page size must be between 1 and 100")


def _validate_filters(filters: AttendanceRecordFilters) -> None:
    if filters.date_from and filters.date_to and filters.date_to < filters.date_from:
        raise BadRequestError("date_to must be greater than or equal to date_from")
    if filters.status and filters.status not in {status.value for status in AttendanceStatus}:
        raise BadRequestError("Invalid attendance status")


def _normalize_correction_reason(reason: str) -> str:
    normalized = reason.strip() if isinstance(reason, str) else ""
    if len(normalized) < 10 or len(normalized) > 1000:
        raise BadRequestError("Correction reason must be between 10 and 1000 characters")
    return normalized


def _normalize_correction_status(status: str) -> str:
    normalized = status.strip().upper() if isinstance(status, str) else ""
    if normalized not in {item.value for item in AttendanceStatus}:
        raise BadRequestError("Invalid corrected attendance status")
    return normalized


class _AttendanceBase:
    def __init__(
        self,
        *,
        attendance_repo: AttendanceRecordRepositoryInterface,
        employee_repo: EmployeeRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
        recognition_service: FaceRecognitionServiceInterface,
        audit_repo: AuditRepositoryInterface,
        clock: ClockInterface,
        settings_provider: Optional[SystemSettingsProviderInterface] = None,
    ) -> None:
        self._attendance_repo = attendance_repo
        self._employee_repo = employee_repo
        self._schedule_repo = schedule_repo
        self._recognition_service = recognition_service
        self._audit_repo = audit_repo
        self._clock = clock
        self._settings_provider = settings_provider

    @staticmethod
    def _local_naive(local_datetime: datetime) -> datetime:
        return local_datetime.replace(tzinfo=None)

    def _allow_unscheduled_attendance(self) -> bool:
        if self._settings_provider is not None:
            return self._settings_provider.get_boolean("ALLOW_UNSCHEDULED_ATTENDANCE")
        return bool(get_settings().ALLOW_UNSCHEDULED_ATTENDANCE)

    def _early_check_in_window_minutes(self) -> int:
        if self._settings_provider is not None:
            return self._settings_provider.get_integer(
                "ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES"
            )
        return int(get_settings().ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES)

    def _missing_checkout_delay_minutes(self) -> int:
        if self._settings_provider is not None:
            return self._settings_provider.get_integer("MISSING_CHECKOUT_DELAY_MINUTES")
        return int(get_settings().MISSING_CHECKOUT_DELAY_MINUTES)

    def _is_checkout_record_eligible(self, record: object, *, captured_at: datetime) -> bool:
        """Allow checkout only while the employee's current attendance session is still valid."""

        if bool(getattr(record, "is_missing_checkout", False)):
            return False
        check_in_at = getattr(record, "check_in_time", None)
        if check_in_at is None or captured_at < check_in_at:
            return False

        scheduled_end = getattr(record, "scheduled_end_datetime", None)
        if scheduled_end is not None:
            deadline = scheduled_end + timedelta(minutes=self._missing_checkout_delay_minutes())
            return captured_at <= deadline

        # Unscheduled attendance has no shift end, so it may only remain open for one day.
        return captured_at <= check_in_at + timedelta(days=1)

    def _matches_check_in_window(
        self,
        schedule: _ResolvedSchedule,
        captured_at: datetime,
    ) -> bool:
        # Determines whether this capture belongs to the resolved scheduled shift.
        earliest_check_in = schedule.scheduled_start_datetime - timedelta(
            minutes=self._early_check_in_window_minutes(),
        )
        return earliest_check_in <= captured_at <= schedule.scheduled_end_datetime

    def recognize_active_employee(
        self,
        request: AttendanceFaceRequest,
    ) -> tuple[object, FaceRecognitionResult]:
        # Recognizes the active employee from the submitted face image.
        try:
            result = self._recognition_service.recognize(
                image_bytes=request.content,
                original_filename=request.filename,
            )
        except ValueError as error:
            raise BadRequestError(str(error)) from error
        except RuntimeError as error:
            raise BadRequestError("Face recognition failed to process the uploaded image") from error

        if not result.matched:
            if result.failure_reason == "ambiguous":
                raise ConflictError(
                    "Face recognition result is ambiguous. Please capture a clearer image."
                )
            raise NotFoundError("No enrolled employee matched the provided face.")

        employee = self._employee_repo.get_by_id(result.employee_id)
        if employee is None:
            raise NotFoundError("Recognized employee does not exist")
        linked_user = getattr(employee, "user", None)
        if not employee.is_active or (linked_user is not None and not linked_user.is_active):
            raise BadRequestError("Recognized employee is inactive")
        return employee, result

    def _resolve_schedule_for_check_in(
        self,
        *,
        employee_id: int,
        captured_at: datetime,
    ) -> Optional[_ResolvedSchedule]:
        # Resolves the check-in schedule for overnight or same-day shifts.
        current_date = captured_at.date()
        previous_date = current_date - timedelta(days=1)

        previous = self._resolve_schedule_for_date(
            employee_id=employee_id,
            schedule_date=previous_date,
        )
        if (
            previous is not None
            and previous.is_overnight
            and self._matches_check_in_window(previous, captured_at)
        ):
            return previous

        current = self._resolve_schedule_for_date(
            employee_id=employee_id,
            schedule_date=current_date,
        )
        if current is not None and self._matches_check_in_window(current, captured_at):
            return current
        return None

    def _resolve_schedule_for_date(
        self,
        *,
        employee_id: int,
        schedule_date: date,
    ) -> Optional[_ResolvedSchedule]:
        # Resolves the employee schedule for one attendance date.
        assignment = self._schedule_repo.get_effective_schedule(
            employee_id=employee_id,
            on_date=schedule_date,
        )
        if assignment is None or schedule_date.weekday() not in _working_days_from_assignment(assignment):
            return None

        template = assignment.schedule_template
        start_datetime = datetime.combine(schedule_date, template.start_time)
        end_date = schedule_date + timedelta(days=1) if template.is_overnight else schedule_date
        end_datetime = datetime.combine(end_date, template.end_time)

        return _ResolvedSchedule(
            assignment_id=assignment.id,
            schedule_template_id=template.id,
            schedule_template_name=template.name,
            schedule_date=schedule_date,
            scheduled_start_datetime=start_datetime,
            scheduled_end_datetime=end_datetime,
            check_in_grace_minutes=template.check_in_grace_minutes,
            early_departure_tolerance_minutes=template.early_departure_tolerance_minutes,
            is_overnight=template.is_overnight,
        )


class CheckInByFace(_AttendanceBase):
    """Recognize an employee and create a check-in attendance record."""

    def execute(self, request: AttendanceFaceRequest) -> AttendanceEventResult:
        employee, recognition = self.recognize_active_employee(request)
        return self.execute_recognized(
            request,
            employee=employee,
            recognition=recognition,
        )

    def execute_recognized(
        self,
        request: AttendanceFaceRequest,
        *,
        employee: object,
        recognition: FaceRecognitionResult,
    ) -> AttendanceEventResult:
        """Create check-in after a trusted caller has already recognized the employee."""

        # Captures the current business-local check-in timestamp.
        settings = get_settings()
        captured_at = self._local_naive(self._clock.now_in_timezone(settings.APP_TIMEZONE))
        resolved_schedule = self._resolve_schedule_for_check_in(
            employee_id=employee.id,
            captured_at=captured_at,
        )

        if resolved_schedule is None and not self._allow_unscheduled_attendance():
            raise ConflictError(
                "No effective schedule matches the attendance time for the recognized employee."
            )

        if resolved_schedule is None:
            # Builds an UNSCHEDULED check-in record with no schedule fields.
            schedule_date = captured_at.date()
            status = AttendanceStatus.UNSCHEDULED
            is_late = False
            is_unscheduled = True
            late_minutes = 0
            employee_schedule_id = None
            schedule_template_id = None
            scheduled_start_datetime = None
            scheduled_end_datetime = None
            duplicate = self._attendance_repo.find_existing_for_shift(
                employee_id=employee.id,
                schedule_date=schedule_date,
                employee_schedule_id=None,
                is_unscheduled=True,
            )
        else:
            # Calculates scheduled check-in status and late minutes.
            schedule_date = resolved_schedule.schedule_date
            allowed_check_in = resolved_schedule.scheduled_start_datetime + timedelta(
                minutes=resolved_schedule.check_in_grace_minutes,
            )
            is_late = captured_at > allowed_check_in
            status = AttendanceStatus.LATE if is_late else AttendanceStatus.PRESENT
            is_unscheduled = False
            late_minutes = (
                max(
                    0,
                    int(
                        (
                            captured_at - resolved_schedule.scheduled_start_datetime
                        ).total_seconds()
                        // 60
                    ),
                )
                if is_late
                else 0
            )
            employee_schedule_id = resolved_schedule.assignment_id
            schedule_template_id = resolved_schedule.schedule_template_id
            scheduled_start_datetime = resolved_schedule.scheduled_start_datetime
            scheduled_end_datetime = resolved_schedule.scheduled_end_datetime
            duplicate = self._attendance_repo.find_existing_for_shift(
                employee_id=employee.id,
                schedule_date=schedule_date,
                employee_schedule_id=employee_schedule_id,
                is_unscheduled=False,
            )

        if duplicate is not None:
            raise ConflictError("Employee has already checked in for this scheduled shift.")

        # Persists the factual recognition-generated check-in record.
        record = self._attendance_repo.create_check_in(
            employee_id=employee.id,
            schedule_date=schedule_date,
            check_in_at=captured_at,
            status=status,
            employee_schedule_id=employee_schedule_id,
            schedule_template_id=schedule_template_id,
            scheduled_start_datetime=scheduled_start_datetime,
            scheduled_end_datetime=scheduled_end_datetime,
            is_late=is_late,
            is_unscheduled=is_unscheduled,
            late_minutes=late_minutes,
            recognition_model_name=recognition.matched_model_name or "",
            detector_backend="mtcnn",
            commit=False,
        )

        # Writes the check-in action to the audit log.
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="ATTENDANCE_CHECK_IN",
            entity_type="AttendanceRecord",
            entity_id=record.id,
            new_values=json.dumps(
                {
                    "employee_id": employee.id,
                    "schedule_date": schedule_date.isoformat(),
                    "status": status.value,
                    "is_late": is_late,
                    "is_unscheduled": is_unscheduled,
                    "recognition_model_name": recognition.matched_model_name,
                    "detector_backend": "mtcnn",
                    "source": request.source,
                }
            ),
            ip_address=request.ip_address,
        )

        if is_unscheduled:
            message = "Unscheduled check-in recorded successfully"
        elif is_late:
            message = "Late check-in recorded successfully"
        else:
            message = "Check-in recorded successfully"

        return AttendanceEventResult(
            record=record,
            event_type="CHECK_IN",
            message=message,
            timezone=settings.APP_TIMEZONE,
        )


class CheckOutByFace(_AttendanceBase):
    """Recognize an employee and close the matching open attendance record."""

    def execute(self, request: AttendanceFaceRequest) -> AttendanceEventResult:
        employee, _recognition = self.recognize_active_employee(request)
        return self.execute_recognized(request, employee=employee)

    def execute_recognized(
        self,
        request: AttendanceFaceRequest,
        *,
        employee: object,
    ) -> AttendanceEventResult:
        """Close attendance after a trusted caller has already recognized the employee."""

        # Recognizes the employee and loads the open attendance record.
        settings = get_settings()
        captured_at = self._local_naive(self._clock.now_in_timezone(settings.APP_TIMEZONE))

        open_record = self.find_eligible_open_record(
            employee_id=employee.id,
            captured_at=captured_at,
        )
        if open_record is None:
            raise ConflictError("No open attendance record found for check-out.")

        old_values = _serialize_record(open_record)
        is_early_departure = False
        early_departure_minutes = 0
        if not open_record.is_unscheduled and open_record.scheduled_end_datetime is not None:
            # Calculates early-departure facts for scheduled records.
            tolerance = 0
            if open_record.schedule_template is not None:
                tolerance = open_record.schedule_template.early_departure_tolerance_minutes
            earliest_allowed_checkout = open_record.scheduled_end_datetime - timedelta(
                minutes=tolerance,
            )
            is_early_departure = captured_at < earliest_allowed_checkout
            if is_early_departure:
                early_departure_minutes = max(
                    0,
                    int((open_record.scheduled_end_datetime - captured_at).total_seconds() // 60),
                )

        working_hours = None
        if open_record.check_in_time is not None:
            # Calculates working hours from check-in to check-out.
            working_hours = round(
                max(0.0, (captured_at - open_record.check_in_time).total_seconds() / 3600),
                2,
            )

        updated = self._attendance_repo.close_with_check_out(
            attendance_id=open_record.id,
            check_out_at=captured_at,
            is_early_departure=is_early_departure,
            early_departure_minutes=early_departure_minutes,
            working_hours=working_hours,
            commit=False,
        )
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="ATTENDANCE_CHECK_OUT",
            entity_type="AttendanceRecord",
            entity_id=open_record.id,
            old_values=json.dumps(old_values),
            new_values=json.dumps(
                {
                    "employee_id": employee.id,
                    "schedule_date": updated.attendance_date.isoformat(),
                    "check_out_at": captured_at.isoformat(),
                    "status": _status_to_value(updated.status),
                    "is_early_departure": is_early_departure,
                    "source": request.source,
                }
            ),
            ip_address=request.ip_address,
        )

        return AttendanceEventResult(
            record=updated,
            event_type="CHECK_OUT",
            message="Check-out recorded successfully",
            timezone=settings.APP_TIMEZONE,
        )

    def find_eligible_open_record(self, *, employee_id: int, captured_at: datetime) -> object | None:
        """Return the current checkout target without selecting stale attendance history."""

        record = self._attendance_repo.find_open_for_employee(employee_id=employee_id)
        if record is None or not self._is_checkout_record_eligible(record, captured_at=captured_at):
            return None
        return record


class ListAttendanceRecords:
    def __init__(self, attendance_repo: AttendanceRecordRepositoryInterface) -> None:
        self._attendance_repo = attendance_repo

    def execute(self, request: AttendanceListRequest) -> AttendanceListResult:
        # Lists admin attendance records with filters and pagination.
        _validate_pagination(request.page, request.page_size)
        _validate_filters(request.filters)
        return AttendanceListResult(
            items=self._attendance_repo.list_records(
                filters=request.filters,
                page=request.page,
                page_size=request.page_size,
            ),
            page=request.page,
            page_size=request.page_size,
            total=self._attendance_repo.count_records(filters=request.filters),
        )


class GetAttendanceRecord:
    def __init__(self, attendance_repo: AttendanceRecordRepositoryInterface) -> None:
        self._attendance_repo = attendance_repo

    def execute(self, request: GetAttendanceRecordRequest):
        record = self._attendance_repo.get_by_id(request.attendance_id)
        if record is None:
            raise NotFoundError("Attendance record not found")
        return record


class ListEmployeeAttendance:
    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        attendance_repo: AttendanceRecordRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._attendance_repo = attendance_repo

    def execute(self, request: EmployeeAttendanceListRequest) -> AttendanceListResult:
        _validate_pagination(request.page, request.page_size)
        _validate_filters(request.filters)
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        filters = AttendanceRecordFilters(
            employee_id=request.employee_id,
            on_date=request.filters.on_date,
            date_from=request.filters.date_from,
            date_to=request.filters.date_to,
            status=request.filters.status,
            is_late=request.filters.is_late,
            is_early_departure=request.filters.is_early_departure,
            is_unscheduled=request.filters.is_unscheduled,
            is_missing_checkout=request.filters.is_missing_checkout,
            has_checkout=request.filters.has_checkout,
            justification_status=request.filters.justification_status,
            overtime_status=request.filters.overtime_status,
        )
        return AttendanceListResult(
            items=self._attendance_repo.list_records(
                filters=filters,
                page=request.page,
                page_size=request.page_size,
            ),
            page=request.page,
            page_size=request.page_size,
            total=self._attendance_repo.count_records(filters=filters),
        )


class ListMyAttendance:
    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        attendance_repo: AttendanceRecordRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._attendance_repo = attendance_repo

    def execute(self, request: MyAttendanceListRequest) -> AttendanceListResult:
        # Lists attendance records for the authenticated employee.
        employee = self._employee_repo.get_by_user_id(request.user_id)
        if employee is None:
            raise NotFoundError("Employee profile not found for current user")
        return ListEmployeeAttendance(
            employee_repo=self._employee_repo,
            attendance_repo=self._attendance_repo,
        ).execute(
            EmployeeAttendanceListRequest(
                employee_id=employee.id,
                filters=request.filters,
                page=request.page,
                page_size=request.page_size,
            )
        )


class CreateAttendanceCorrection:
    """Create an administrative correction without rewriting factual attendance."""

    def __init__(
        self,
        *,
        attendance_repo: AttendanceRecordRepositoryInterface,
        correction_repo: AttendanceCorrectionRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        clock: ClockInterface,
    ) -> None:
        self._attendance_repo = attendance_repo
        self._correction_repo = correction_repo
        self._audit_repo = audit_repo
        self._clock = clock

    def execute(self, request: CreateAttendanceCorrectionRequest):
        # Creates an administrative correction overlay for one attendance record.
        settings = get_settings()
        record = self._attendance_repo.get_by_id(request.attendance_id)
        if record is None:
            raise NotFoundError("Attendance record not found")

        corrected_status = _normalize_correction_status(request.corrected_status)
        reason = _normalize_correction_reason(request.reason)
        original_status = _status_to_value(record.status)
        corrected_at = self._clock.now_in_timezone(settings.APP_TIMEZONE).replace(tzinfo=None)

        correction = self._correction_repo.create(
            attendance_record_id=record.id,
            original_status=original_status,
            corrected_status=corrected_status,
            reason=reason,
            corrected_by_user_id=request.actor_user_id,
            corrected_at=corrected_at,
            commit=False,
        )
        # Writes the attendance correction to the audit log.
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="CREATE_ATTENDANCE_CORRECTION",
            entity_type="AttendanceCorrection",
            entity_id=correction.id,
            old_values=json.dumps(
                {
                    "attendance_record_id": record.id,
                    "employee_id": record.employee_id,
                    "original_status": original_status,
                    "check_in_at": record.check_in_time.isoformat() if record.check_in_time else None,
                    "check_out_at": record.check_out_time.isoformat() if record.check_out_time else None,
                }
            ),
            new_values=json.dumps(
                {
                    "attendance_record_id": record.id,
                    "employee_id": record.employee_id,
                    "corrected_status": corrected_status,
                    "reason": reason,
                    "corrected_by_user_id": request.actor_user_id,
                    "corrected_at": corrected_at.isoformat(),
                }
            ),
            ip_address=request.ip_address,
        )
        return correction


class ListAttendanceCorrections:
    """Return correction history for an attendance record."""

    def __init__(
        self,
        *,
        attendance_repo: AttendanceRecordRepositoryInterface,
        correction_repo: AttendanceCorrectionRepositoryInterface,
    ) -> None:
        self._attendance_repo = attendance_repo
        self._correction_repo = correction_repo

    def execute(self, request: ListAttendanceCorrectionsRequest):
        record = self._attendance_repo.get_by_id(request.attendance_id)
        if record is None:
            raise NotFoundError("Attendance record not found")
        return self._correction_repo.list_for_attendance(request.attendance_id)
