"""Live mobile-camera attendance API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from app.application.dto.attendance_dto import LiveAttendanceFaceRequest
from app.application.use_cases.attendance.live_attendance import (
    LiveCheckInByFace,
    LiveCheckOutByFace,
    UnifiedLiveAttendanceByFace,
)
from app.application.use_cases.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from app.dependencies import (
    get_attendance_record_repository,
    get_audit_repository,
    get_clock,
    get_employee_repository,
    get_employee_schedule_repository,
    get_face_recognition_service,
    get_liveness_service,
    get_system_settings_provider,
)
from app.domain.repositories.attendance_record_repository import AttendanceRecordRepositoryInterface
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.employee_schedule_repository import EmployeeScheduleRepositoryInterface
from app.domain.services.clock_service import ClockInterface
from app.domain.services.face_recognition_service import FaceRecognitionServiceInterface
from app.domain.services.liveness_service import LivenessFrame, LivenessServiceInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.infrastructure.security.permissions import require_admin
from app.presentation.api.attendance import _event_response
from app.presentation.schemas.live_attendance_schema import (
    LiveAttendanceEventResponse,
    LivenessResultResponse,
    UnifiedLiveAttendanceResponse,
)

router = APIRouter(prefix="/attendance/live", tags=["Live Attendance"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


async def _frames_from_uploads(frames: list[UploadFile]) -> list[LivenessFrame]:
    payloads: list[LivenessFrame] = []
    for index, upload in enumerate(frames, start=1):
        content = await upload.read()
        payloads.append(
            LivenessFrame(
                filename=upload.filename or f"live_frame_{index:03d}.jpg",
                content=content,
            )
        )
        await upload.close()
    return payloads


def _live_response(result, *, message: str) -> LiveAttendanceEventResponse:
    event = _event_response(result.attendance)
    return LiveAttendanceEventResponse(
        **event.model_dump(exclude={"message"}),
        message=message,
        liveness=LivenessResultResponse(
            passed=result.liveness.passed,
            challenge_type=result.liveness.challenge_type,
            confidence=result.liveness.confidence,
            frames_analyzed=result.liveness.frames_analyzed,
        ),
    )


def _unified_live_response(result) -> UnifiedLiveAttendanceResponse:
    event = _event_response(result.attendance)
    is_check_in = event.event_type == "CHECK_IN"
    timestamp = event.check_in_at if is_check_in else event.check_out_at
    if timestamp is None:
        raise RuntimeError("Completed live attendance event is missing its event timestamp")

    return UnifiedLiveAttendanceResponse(
        success=True,
        action=event.event_type,
        employee_id=event.employee_id,
        employee_number=event.employee_number,
        employee_name=event.employee_name,
        attendance_record_id=event.attendance_id,
        timestamp=timestamp,
        status=event.status,
        is_unscheduled=event.is_unscheduled,
        working_hours=getattr(result.attendance.record, "working_hours", None),
        message=(
            "Check-in completed successfully."
            if is_check_in
            else "Check-out completed successfully."
        ),
        timezone=event.timezone,
        recognition_model_name=event.recognition_model_name,
        liveness=LivenessResultResponse(
            passed=result.liveness.passed,
            challenge_type=result.liveness.challenge_type,
            confidence=result.liveness.confidence,
            frames_analyzed=result.liveness.frames_analyzed,
        ),
    )


@router.post("/attendance", response_model=UnifiedLiveAttendanceResponse)
async def unified_live_attendance_by_face(
    request: Request,
    challenge_type: str = Form(...),
    frames: list[UploadFile] = File(...),
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(
        get_employee_schedule_repository,
    ),
    recognition_service: FaceRecognitionServiceInterface = Depends(get_face_recognition_service),
    liveness_service: LivenessServiceInterface = Depends(get_liveness_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = UnifiedLiveAttendanceByFace(
        attendance_repo=attendance_repo,
        employee_repo=employee_repo,
        schedule_repo=schedule_repo,
        recognition_service=recognition_service,
        liveness_service=liveness_service,
        audit_repo=audit_repo,
        clock=clock,
        settings_provider=settings_provider,
    )
    try:
        result = use_case.execute(
            LiveAttendanceFaceRequest(
                frames=await _frames_from_uploads(frames),
                challenge_type=challenge_type,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _unified_live_response(result)


@router.post("/check-in", response_model=LiveAttendanceEventResponse)
async def live_check_in_by_face(
    request: Request,
    challenge_type: str = Form(...),
    frames: list[UploadFile] = File(...),
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(
        get_employee_schedule_repository,
    ),
    recognition_service: FaceRecognitionServiceInterface = Depends(get_face_recognition_service),
    liveness_service: LivenessServiceInterface = Depends(get_liveness_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = LiveCheckInByFace(
        attendance_repo=attendance_repo,
        employee_repo=employee_repo,
        schedule_repo=schedule_repo,
        recognition_service=recognition_service,
        liveness_service=liveness_service,
        audit_repo=audit_repo,
        clock=clock,
        settings_provider=settings_provider,
    )
    try:
        result = use_case.execute(
            LiveAttendanceFaceRequest(
                frames=await _frames_from_uploads(frames),
                challenge_type=challenge_type,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _live_response(result, message="Live attendance check-in completed successfully")


@router.post("/check-out", response_model=LiveAttendanceEventResponse)
async def live_check_out_by_face(
    request: Request,
    challenge_type: str = Form(...),
    frames: list[UploadFile] = File(...),
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(
        get_employee_schedule_repository,
    ),
    recognition_service: FaceRecognitionServiceInterface = Depends(get_face_recognition_service),
    liveness_service: LivenessServiceInterface = Depends(get_liveness_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = LiveCheckOutByFace(
        attendance_repo=attendance_repo,
        employee_repo=employee_repo,
        schedule_repo=schedule_repo,
        recognition_service=recognition_service,
        liveness_service=liveness_service,
        audit_repo=audit_repo,
        clock=clock,
    )
    try:
        result = use_case.execute(
            LiveAttendanceFaceRequest(
                frames=await _frames_from_uploads(frames),
                challenge_type=challenge_type,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _live_response(result, message="Live attendance check-out completed successfully")
