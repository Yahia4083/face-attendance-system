"""Daily attendance processing use case."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.application.dto.attendance_processing_dto import (
    ProcessDailyAttendanceRequest,
    ProcessDailyAttendanceResult,
)
from app.application.use_cases.exceptions import BadRequestError
from app.config import get_settings
from app.domain.enums.attendance_status import AttendanceStatus
from app.domain.repositories.attendance_record_repository import (
    AttendanceRecordRepositoryInterface,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_schedule_repository import EmployeeScheduleRepositoryInterface
from app.domain.services.clock_service import ClockInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface


def _working_days_from_assignment(assignment) -> list[int]:
    # Converts the stored weekday string into integer weekday values.
    value = assignment.working_days or ""
    return [int(day) for day in value.split(",") if day != ""]


def _scheduled_datetimes(assignment, on_date):
    # Builds scheduled start and end datetimes for daytime or overnight shifts.
    template = assignment.schedule_template
    start_datetime = datetime.combine(on_date, template.start_time)
    end_date = on_date + timedelta(days=1) if template.is_overnight else on_date
    end_datetime = datetime.combine(end_date, template.end_time)
    return start_datetime, end_datetime


class ProcessDailyAttendance:
    """Create ABSENT records and mark MISSING_CHECKOUT for eligible shifts."""

    def __init__(
        self,
        *,
        attendance_repo: AttendanceRecordRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
        clock: ClockInterface,
        settings_provider: SystemSettingsProviderInterface | None = None,
    ) -> None:
        self._attendance_repo = attendance_repo
        self._schedule_repo = schedule_repo
        self._audit_repo = audit_repo
        self._clock = clock
        self._settings_provider = settings_provider

    def execute(self, request: ProcessDailyAttendanceRequest) -> ProcessDailyAttendanceResult:
        # Starts the admin daily attendance-processing workflow for one date.
        settings = get_settings()
        now_local = self._clock.now_in_timezone(settings.APP_TIMEZONE).replace(tzinfo=None)
        absence_delay_minutes = (
            self._settings_provider.get_integer("ATTENDANCE_PROCESSING_DELAY_MINUTES")
            if self._settings_provider is not None
            else settings.ATTENDANCE_PROCESSING_DELAY_MINUTES
        )
        missing_checkout_delay_minutes = (
            self._settings_provider.get_integer("MISSING_CHECKOUT_DELAY_MINUTES")
            if self._settings_provider is not None
            else settings.MISSING_CHECKOUT_DELAY_MINUTES
        )
        absence_delay = timedelta(minutes=absence_delay_minutes)
        missing_checkout_delay = timedelta(minutes=missing_checkout_delay_minutes)

        processed_assignments = 0
        absent_created = 0
        missing_updated = 0
        unchanged = 0
        eligible_seen = False

        assignments = self._schedule_repo.list_active_assignments_for_date(on_date=request.on_date)
        for assignment in assignments:
            # Skips assignments that do not apply to the requested weekday.
            if request.on_date.weekday() not in _working_days_from_assignment(assignment):
                continue

            processed_assignments += 1
            scheduled_start, scheduled_end = _scheduled_datetimes(assignment, request.on_date)
            existing = self._attendance_repo.find_existing_for_shift(
                employee_id=assignment.employee_id,
                schedule_date=request.on_date,
                employee_schedule_id=assignment.id,
                is_unscheduled=False,
            )

            # Uses the absence cutoff when no check-in was recorded for the shift.
            if existing is None:
                if now_local < scheduled_end + absence_delay:
                    unchanged += 1
                    continue
                eligible_seen = True
                record = self._attendance_repo.create_absent_record(
                    employee_id=assignment.employee_id,
                    schedule_date=request.on_date,
                    employee_schedule_id=assignment.id,
                    schedule_template_id=assignment.schedule_template_id,
                    scheduled_start_datetime=scheduled_start,
                    scheduled_end_datetime=scheduled_end,
                    processed_at=now_local,
                    commit=False,
                )
                absent_created += 1
                self._audit_repo.log(
                    actor_user_id=request.actor_user_id,
                    action="CREATE_ABSENT_ATTENDANCE",
                    entity_type="AttendanceRecord",
                    entity_id=record.id,
                    new_values=json.dumps(
                        {
                            "employee_id": assignment.employee_id,
                            "schedule_date": request.on_date.isoformat(),
                            "status": AttendanceStatus.ABSENT.value,
                            "employee_schedule_id": assignment.id,
                        }
                    ),
                    ip_address=request.ip_address,
                )
                continue

            # Gives open check-ins their separate post-shift overtime window.
            current_status = (
                existing.status
                if isinstance(existing.status, AttendanceStatus)
                else AttendanceStatus(existing.status)
            )
            is_open_scheduled_record = (
                existing.check_in_time is not None
                and existing.check_out_time is None
                and existing.scheduled_end_datetime is not None
            )
            applicable_delay = (
                missing_checkout_delay if is_open_scheduled_record else absence_delay
            )
            if now_local < scheduled_end + applicable_delay:
                if now_local >= scheduled_end + absence_delay:
                    eligible_seen = True
                unchanged += 1
                continue
            eligible_seen = True

            should_mark_missing = (
                is_open_scheduled_record
                and current_status != AttendanceStatus.MISSING_CHECKOUT
            )
            if should_mark_missing:
                old_values = {
                    "status": current_status.value,
                    "is_late": bool(existing.is_late),
                    "check_in_at": existing.check_in_time.isoformat()
                    if existing.check_in_time
                    else None,
                    "check_out_at": None,
                }
                updated = self._attendance_repo.mark_missing_checkout(
                    attendance_id=existing.id,
                    processed_at=now_local,
                    commit=False,
                )
                missing_updated += 1
                self._audit_repo.log(
                    actor_user_id=request.actor_user_id,
                    action="MARK_MISSING_CHECKOUT",
                    entity_type="AttendanceRecord",
                    entity_id=existing.id,
                    old_values=json.dumps(old_values),
                    new_values=json.dumps(
                        {
                            "employee_id": updated.employee_id,
                            "schedule_date": updated.attendance_date.isoformat(),
                            "status": AttendanceStatus.MISSING_CHECKOUT.value,
                            "is_late": bool(updated.is_late),
                            "is_missing_checkout": True,
                        }
                    ),
                    ip_address=request.ip_address,
                )
            else:
                unchanged += 1

        if processed_assignments > 0 and not eligible_seen:
            # Returns a business error when no scheduled shift is ready to process.
            raise BadRequestError(
                "No scheduled shifts are eligible for daily processing yet."
            )

        # Records manual runs and automatic runs that changed attendance state.
        if not request.is_automatic or absent_created > 0 or missing_updated > 0:
            self._audit_repo.log(
                actor_user_id=request.actor_user_id,
                action="PROCESS_DAILY_ATTENDANCE",
                entity_type="AttendanceRecord",
                entity_id=None,
                new_values=json.dumps(
                    {
                        "on_date": request.on_date.isoformat(),
                        "trigger": "AUTOMATIC" if request.is_automatic else "ADMIN",
                        "absence_delay_minutes": absence_delay_minutes,
                        "missing_checkout_delay_minutes": missing_checkout_delay_minutes,
                        "processed_assignments": processed_assignments,
                        "absent_records_created": absent_created,
                        "missing_checkout_records_updated": missing_updated,
                        "already_processed_or_unchanged": unchanged,
                    }
                ),
                ip_address=request.ip_address,
            )

        return ProcessDailyAttendanceResult(
            on_date=request.on_date,
            timezone=settings.APP_TIMEZONE,
            processed_assignments=processed_assignments,
            absent_records_created=absent_created,
            missing_checkout_records_updated=missing_updated,
            already_processed_or_unchanged=unchanged,
            message="Daily attendance processing completed successfully",
        )
