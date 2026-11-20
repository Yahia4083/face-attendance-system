"""Live mobile-camera attendance use cases."""

from __future__ import annotations

import json

from app.application.dto.attendance_dto import (
    AttendanceFaceRequest,
    LiveAttendanceEventResult,
    LiveAttendanceFaceRequest,
)
from app.application.use_cases.attendance.attendance_management import CheckInByFace, CheckOutByFace
from app.application.use_cases.exceptions import (
    BadRequestError,
    ConflictError,
)
from app.config import get_settings
from app.domain.repositories.attendance_record_repository import AttendanceRecordRepositoryInterface
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.employee_schedule_repository import EmployeeScheduleRepositoryInterface
from app.domain.services.clock_service import ClockInterface
from app.domain.services.face_recognition_service import FaceRecognitionServiceInterface
from app.domain.services.liveness_service import LivenessServiceInterface, LivenessValidationRequest
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface


class _LiveAttendanceBase:
    def __init__(
        self,
        *,
        attendance_repo: AttendanceRecordRepositoryInterface,
        employee_repo: EmployeeRepositoryInterface,
        schedule_repo: EmployeeScheduleRepositoryInterface,
        recognition_service: FaceRecognitionServiceInterface,
        liveness_service: LivenessServiceInterface,
        audit_repo: AuditRepositoryInterface,
        clock: ClockInterface,
        settings_provider: SystemSettingsProviderInterface | None = None,
    ) -> None:
        self._attendance_repo = attendance_repo
        self._employee_repo = employee_repo
        self._schedule_repo = schedule_repo
        self._recognition_service = recognition_service
        self._liveness_service = liveness_service
        self._audit_repo = audit_repo
        self._clock = clock
        self._settings_provider = settings_provider

    def _validate_liveness(self, request: LiveAttendanceFaceRequest):
        # Runs liveness validation for the submitted live frame sequence.
        result = self._liveness_service.validate(
            LivenessValidationRequest(
                frames=request.frames,
                challenge_type=request.challenge_type,
            )
        )
        if result.passed and result.selected_frame is not None:
            return result

        # Writes a safe audit entry for the failed liveness attempt.
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="LIVENESS_VERIFICATION_FAILED",
            entity_type="LiveAttendance",
            entity_id=None,
            new_values=json.dumps(
                {
                    "challenge_type": result.challenge_type,
                    "frames_analyzed": result.frames_analyzed,
                    "confidence": result.confidence,
                    "failure_reason": result.failure_reason,
                }
            ),
            ip_address=request.ip_address,
        )
        raise BadRequestError(
            result.failure_reason
            or "Liveness verification failed. Please complete the challenge and keep only one face visible."
        )

    def _check_in_use_case(self) -> CheckInByFace:
        return CheckInByFace(
            attendance_repo=self._attendance_repo,
            employee_repo=self._employee_repo,
            schedule_repo=self._schedule_repo,
            recognition_service=self._recognition_service,
            audit_repo=self._audit_repo,
            clock=self._clock,
            settings_provider=self._settings_provider,
        )

    def _check_out_use_case(self) -> CheckOutByFace:
        return CheckOutByFace(
            attendance_repo=self._attendance_repo,
            employee_repo=self._employee_repo,
            schedule_repo=self._schedule_repo,
            recognition_service=self._recognition_service,
            audit_repo=self._audit_repo,
            clock=self._clock,
            settings_provider=self._settings_provider,
        )

    @staticmethod
    def _attendance_request_from_live(
        request: LiveAttendanceFaceRequest,
        selected_frame,
    ) -> AttendanceFaceRequest:
        # Converts the selected liveness frame into a normal attendance request.
        return AttendanceFaceRequest(
            filename=selected_frame.filename or "live_mobile_frame.jpg",
            content=selected_frame.content,
            actor_user_id=request.actor_user_id,
            ip_address=request.ip_address,
            source="LIVE_KIOSK",
        )


class LiveCheckInByFace(_LiveAttendanceBase):
    """Run liveness validation before existing check-in recognition."""

    def execute(self, request: LiveAttendanceFaceRequest) -> LiveAttendanceEventResult:
        liveness = self._validate_liveness(request)
        # Runs the existing face-recognition check-in use case.
        use_case = self._check_in_use_case()
        attendance = use_case.execute(
            self._attendance_request_from_live(request, liveness.selected_frame)
        )
        return LiveAttendanceEventResult(attendance=attendance, liveness=liveness)


class LiveCheckOutByFace(_LiveAttendanceBase):
    """Run liveness validation before existing check-out recognition."""

    def execute(self, request: LiveAttendanceFaceRequest) -> LiveAttendanceEventResult:
        liveness = self._validate_liveness(request)
        # Runs the existing face-recognition check-out use case.
        use_case = self._check_out_use_case()
        attendance = use_case.execute(
            self._attendance_request_from_live(request, liveness.selected_frame)
        )
        return LiveAttendanceEventResult(attendance=attendance, liveness=liveness)


class UnifiedLiveAttendanceByFace(_LiveAttendanceBase):
    """Recognize once and let backend attendance state select check-in or check-out."""

    def execute(self, request: LiveAttendanceFaceRequest) -> LiveAttendanceEventResult:
        liveness = self._validate_liveness(request)
        attendance_request = self._attendance_request_from_live(
            request,
            liveness.selected_frame,
        )
        check_in = self._check_in_use_case()
        employee, recognition = check_in.recognize_active_employee(attendance_request)

        captured_at = self._clock.now_in_timezone(get_settings().APP_TIMEZONE).replace(tzinfo=None)
        check_out = self._check_out_use_case()
        open_record = check_out.find_eligible_open_record(
            employee_id=employee.id,
            captured_at=captured_at,
        )
        if open_record is not None:
            attendance = check_out.execute_recognized(
                attendance_request,
                employee=employee,
            )
            return LiveAttendanceEventResult(attendance=attendance, liveness=liveness)

        business_date = captured_at.date()
        latest_today = self._attendance_repo.find_latest_for_employee_on_date(
            employee_id=employee.id,
            on_date=business_date,
        )
        if (
            latest_today is not None
            and latest_today.check_in_time is not None
            and latest_today.check_out_time is not None
        ):
            raise ConflictError("Attendance already completed for today.")

        try:
            attendance = check_in.execute_recognized(
                attendance_request,
                employee=employee,
                recognition=recognition,
            )
        except ConflictError as error:
            if "already checked in" in str(error).lower():
                raise ConflictError("Attendance already completed for today.") from error
            raise
        return LiveAttendanceEventResult(attendance=attendance, liveness=liveness)
