"""Attendance API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.application.dto.attendance_dto import (
    AttendanceFaceRequest,
    AttendanceListRequest,
    CreateAttendanceCorrectionRequest,
    EmployeeAttendanceListRequest,
    GetAttendanceRecordRequest,
    ListAttendanceCorrectionsRequest,
    MyAttendanceListRequest,
)
from app.application.dto.attendance_processing_dto import (
    ProcessDailyAttendanceRequest as ProcessDailyAttendanceDTO,
)
from app.application.use_cases.attendance.attendance_management import (
    CheckInByFace,
    CheckOutByFace,
    CreateAttendanceCorrection,
    GetAttendanceRecord,
    ListAttendanceCorrections,
    ListAttendanceRecords,
    ListEmployeeAttendance,
    ListMyAttendance,
)
from app.application.use_cases.attendance.process_daily_attendance import ProcessDailyAttendance
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.dependencies import (
    get_attendance_correction_repository,
    get_attendance_record_repository,
    get_audit_repository,
    get_clock,
    get_employee_repository,
    get_employee_schedule_repository,
    get_face_recognition_service,
    get_system_settings_provider,
)
from app.config import get_settings
from app.domain.repositories.attendance_correction_repository import (
    AttendanceCorrectionRepositoryInterface,
)
from app.domain.repositories.attendance_record_repository import (
    AttendanceRecordFilters,
    AttendanceRecordRepositoryInterface,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.employee_schedule_repository import EmployeeScheduleRepositoryInterface
from app.domain.services.clock_service import ClockInterface
from app.domain.services.face_recognition_service import FaceRecognitionServiceInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.infrastructure.security.permissions import require_admin, require_employee
from app.presentation.schemas.attendance_schema import (
    AttendanceCorrectionCreateRequest,
    AttendanceCorrectionListResponse,
    AttendanceCorrectionResponse,
    AttendanceEventResponse,
    AttendanceRecordListResponse,
    AttendanceRecordResponse,
)
from app.presentation.schemas.attendance_processing_schema import (
    ProcessDailyAttendanceRequest,
    ProcessDailyAttendanceResponse,
)
from app.shared.datetime_utils import local_isoformat, utc_to_local_isoformat

router = APIRouter(tags=["Attendance"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


def _status_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _latest_status(items) -> Optional[str]:
    if not items:
        return None
    latest = max(items, key=lambda item: (getattr(item, "created_at", None), getattr(item, "id", 0)))
    return _status_value(latest.status)


def _has_pending(items) -> bool:
    return any(_status_value(item.status) == "PENDING" for item in items or [])


def _latest_correction(corrections):
    if not corrections:
        return None
    return max(corrections, key=lambda item: (getattr(item, "corrected_at", None), getattr(item, "id", 0)))


def _correction_response(correction, *, message: Optional[str] = None) -> AttendanceCorrectionResponse:
    timezone_name = get_settings().APP_TIMEZONE
    return AttendanceCorrectionResponse(
        id=correction.id,
        attendance_record_id=correction.attendance_record_id,
        original_status=correction.original_status,
        corrected_status=correction.corrected_status,
        reason=correction.reason,
        corrected_by_user_id=correction.corrected_by_user_id,
        corrected_at=local_isoformat(correction.corrected_at, timezone_name),
        created_at=local_isoformat(correction.created_at, timezone_name),
        message=message,
    )


def _record_response(record) -> AttendanceRecordResponse:
    timezone_name = get_settings().APP_TIMEZONE
    employee = getattr(record, "employee", None)
    template = getattr(record, "schedule_template", None)
    justifications = list(getattr(record, "justification_requests", []) or [])
    overtime_requests = list(getattr(record, "overtime_requests", []) or [])
    corrections = list(getattr(record, "corrections", []) or [])
    latest_correction = _latest_correction(corrections)
    factual_status = _status_value(record.status)
    effective_status = (
        latest_correction.corrected_status if latest_correction is not None else factual_status
    )
    return AttendanceRecordResponse(
        id=record.id,
        employee_id=record.employee_id,
        employee_name=employee.full_name if employee else None,
        employee_number=employee.employee_number if employee else None,
        employee_schedule_id=record.employee_schedule_id,
        schedule_template_id=record.schedule_template_id,
        schedule_template_name=template.name if template else None,
        schedule_date=record.attendance_date,
        scheduled_start_datetime=local_isoformat(record.scheduled_start_datetime, timezone_name),
        scheduled_end_datetime=local_isoformat(record.scheduled_end_datetime, timezone_name),
        check_in_at=local_isoformat(record.check_in_time, timezone_name),
        check_out_at=local_isoformat(record.check_out_time, timezone_name),
        working_hours=record.working_hours,
        status=factual_status,
        is_late=bool(record.is_late),
        is_early_departure=bool(record.is_early_departure),
        is_unscheduled=bool(record.is_unscheduled),
        is_missing_checkout=bool(getattr(record, "is_missing_checkout", False)),
        late_minutes=record.late_minutes,
        early_departure_minutes=record.early_departure_minutes,
        has_pending_justification=_has_pending(justifications),
        latest_justification_status=_latest_status(justifications),
        has_pending_overtime_request=_has_pending(overtime_requests),
        latest_overtime_status=_latest_status(overtime_requests),
        recognition_model_name=record.recognition_model_name,
        original_status=factual_status,
        effective_status=effective_status,
        has_admin_correction=latest_correction is not None,
        latest_correction=_correction_response(latest_correction)
        if latest_correction is not None
        else None,
        created_at=utc_to_local_isoformat(record.created_at, timezone_name),
        updated_at=utc_to_local_isoformat(record.updated_at, timezone_name),
    )


def _event_response(result) -> AttendanceEventResponse:
    timezone_name = result.timezone
    record = result.record
    employee = getattr(record, "employee", None)
    return AttendanceEventResponse(
        attendance_id=record.id,
        event_type=result.event_type,
        employee_id=record.employee_id,
        employee_name=employee.full_name if employee else None,
        employee_number=employee.employee_number if employee else None,
        schedule_date=record.attendance_date,
        check_in_at=local_isoformat(record.check_in_time, timezone_name),
        check_out_at=local_isoformat(record.check_out_time, timezone_name),
        scheduled_start_datetime=local_isoformat(record.scheduled_start_datetime, timezone_name),
        scheduled_end_datetime=local_isoformat(record.scheduled_end_datetime, timezone_name),
        status=_status_value(record.status),
        is_late=bool(record.is_late),
        is_early_departure=bool(record.is_early_departure),
        is_unscheduled=bool(record.is_unscheduled),
        timezone=result.timezone,
        recognition_model_name=record.recognition_model_name,
        message=result.message,
    )


def _filters(
    *,
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    on_date: Optional[date] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status_value: Optional[str] = None,
    is_late: Optional[bool] = None,
    is_early_departure: Optional[bool] = None,
    is_unscheduled: Optional[bool] = None,
    is_missing_checkout: Optional[bool] = None,
    has_checkout: Optional[bool] = None,
    justification_status: Optional[str] = None,
    overtime_status: Optional[str] = None,
) -> AttendanceRecordFilters:
    return AttendanceRecordFilters(
        employee_id=employee_id,
        department_id=department_id,
        on_date=on_date,
        date_from=date_from,
        date_to=date_to,
        status=status_value,
        is_late=is_late,
        is_early_departure=is_early_departure,
        is_unscheduled=is_unscheduled,
        is_missing_checkout=is_missing_checkout,
        has_checkout=has_checkout,
        justification_status=justification_status,
        overtime_status=overtime_status,
    )


async def _face_request_from_upload(
    *,
    file: UploadFile,
    actor_user_id: int,
    ip_address: Optional[str],
) -> AttendanceFaceRequest:
    return AttendanceFaceRequest(
        filename=file.filename or "uploaded_image.jpg",
        content=await file.read(),
        actor_user_id=actor_user_id,
        ip_address=ip_address,
    )


@router.post("/attendance/check-in", response_model=AttendanceEventResponse)
async def check_in_by_face(
    request: Request,
    file: UploadFile = File(...),
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(
        get_employee_schedule_repository,
    ),
    recognition_service: FaceRecognitionServiceInterface = Depends(get_face_recognition_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = CheckInByFace(
        attendance_repo=attendance_repo,
        employee_repo=employee_repo,
        schedule_repo=schedule_repo,
        recognition_service=recognition_service,
        audit_repo=audit_repo,
        clock=clock,
        settings_provider=settings_provider,
    )
    try:
        result = use_case.execute(
            await _face_request_from_upload(
                file=file,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _event_response(result)


@router.post(
    "/attendance/records/{attendance_id}/corrections",
    response_model=AttendanceCorrectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_attendance_correction(
    attendance_id: int,
    payload: AttendanceCorrectionCreateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    correction_repo: AttendanceCorrectionRepositoryInterface = Depends(
        get_attendance_correction_repository,
    ),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = CreateAttendanceCorrection(
        attendance_repo=attendance_repo,
        correction_repo=correction_repo,
        audit_repo=audit_repo,
        clock=clock,
    )
    try:
        correction = use_case.execute(
            CreateAttendanceCorrectionRequest(
                attendance_id=attendance_id,
                corrected_status=payload.corrected_status,
                reason=payload.reason,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _correction_response(correction, message="Attendance correction recorded successfully")


@router.get(
    "/attendance/records/{attendance_id}/corrections",
    response_model=AttendanceCorrectionListResponse,
)
def list_attendance_corrections(
    attendance_id: int,
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    correction_repo: AttendanceCorrectionRepositoryInterface = Depends(
        get_attendance_correction_repository,
    ),
):
    use_case = ListAttendanceCorrections(
        attendance_repo=attendance_repo,
        correction_repo=correction_repo,
    )
    try:
        items = use_case.execute(ListAttendanceCorrectionsRequest(attendance_id=attendance_id))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return AttendanceCorrectionListResponse(
        items=[_correction_response(item) for item in items],
        total=len(items),
    )


@router.post("/attendance/check-out", response_model=AttendanceEventResponse)
async def check_out_by_face(
    request: Request,
    file: UploadFile = File(...),
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(
        get_employee_schedule_repository,
    ),
    recognition_service: FaceRecognitionServiceInterface = Depends(get_face_recognition_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = CheckOutByFace(
        attendance_repo=attendance_repo,
        employee_repo=employee_repo,
        schedule_repo=schedule_repo,
        recognition_service=recognition_service,
        audit_repo=audit_repo,
        clock=clock,
    )
    try:
        result = use_case.execute(
            await _face_request_from_upload(
                file=file,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _event_response(result)


@router.post("/attendance/process-daily", response_model=ProcessDailyAttendanceResponse)
def process_daily_attendance(
    payload: ProcessDailyAttendanceRequest,
    request: Request,
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(
        get_employee_schedule_repository,
    ),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = ProcessDailyAttendance(
        attendance_repo=attendance_repo,
        schedule_repo=schedule_repo,
        audit_repo=audit_repo,
        clock=clock,
        settings_provider=settings_provider,
    )
    try:
        result = use_case.execute(
            ProcessDailyAttendanceDTO(
                on_date=payload.on_date,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return ProcessDailyAttendanceResponse(
        on_date=result.on_date,
        timezone=result.timezone,
        processed_assignments=result.processed_assignments,
        absent_records_created=result.absent_records_created,
        missing_checkout_records_updated=result.missing_checkout_records_updated,
        already_processed_or_unchanged=result.already_processed_or_unchanged,
        message=result.message,
    )


@router.get("/attendance/records", response_model=AttendanceRecordListResponse)
def list_attendance_records(
    employee_id: Optional[int] = None,
    department_id: Optional[int] = None,
    on_date: Optional[date] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    is_late: Optional[bool] = None,
    is_early_departure: Optional[bool] = None,
    is_unscheduled: Optional[bool] = None,
    is_missing_checkout: Optional[bool] = None,
    has_checkout: Optional[bool] = None,
    justification_status: Optional[str] = None,
    overtime_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
):
    use_case = ListAttendanceRecords(attendance_repo)
    try:
        result = use_case.execute(
            AttendanceListRequest(
                filters=_filters(
                    employee_id=employee_id,
                    department_id=department_id,
                    on_date=on_date,
                    date_from=date_from,
                    date_to=date_to,
                    status_value=status,
                    is_late=is_late,
                    is_early_departure=is_early_departure,
                    is_unscheduled=is_unscheduled,
                    is_missing_checkout=is_missing_checkout,
                    has_checkout=has_checkout,
                    justification_status=justification_status,
                    overtime_status=overtime_status,
                ),
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return AttendanceRecordListResponse(
        items=[_record_response(record) for record in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/attendance/records/{attendance_id}", response_model=AttendanceRecordResponse)
def get_attendance_record(
    attendance_id: int,
    current_admin=Depends(require_admin),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
):
    use_case = GetAttendanceRecord(attendance_repo)
    try:
        record = use_case.execute(GetAttendanceRecordRequest(attendance_id=attendance_id))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _record_response(record)


@router.get("/employees/{employee_id}/attendance", response_model=AttendanceRecordListResponse)
def list_employee_attendance(
    employee_id: int,
    on_date: Optional[date] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    is_late: Optional[bool] = None,
    is_early_departure: Optional[bool] = None,
    is_unscheduled: Optional[bool] = None,
    is_missing_checkout: Optional[bool] = None,
    has_checkout: Optional[bool] = None,
    justification_status: Optional[str] = None,
    overtime_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
):
    use_case = ListEmployeeAttendance(
        employee_repo=employee_repo,
        attendance_repo=attendance_repo,
    )
    try:
        result = use_case.execute(
            EmployeeAttendanceListRequest(
                employee_id=employee_id,
                filters=_filters(
                    on_date=on_date,
                    date_from=date_from,
                    date_to=date_to,
                    status_value=status,
                    is_late=is_late,
                    is_early_departure=is_early_departure,
                    is_unscheduled=is_unscheduled,
                    is_missing_checkout=is_missing_checkout,
                    has_checkout=has_checkout,
                    justification_status=justification_status,
                    overtime_status=overtime_status,
                ),
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return AttendanceRecordListResponse(
        items=[_record_response(record) for record in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/me/attendance", response_model=AttendanceRecordListResponse)
def list_my_attendance(
    on_date: Optional[date] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    is_late: Optional[bool] = None,
    is_early_departure: Optional[bool] = None,
    is_unscheduled: Optional[bool] = None,
    is_missing_checkout: Optional[bool] = None,
    has_checkout: Optional[bool] = None,
    justification_status: Optional[str] = None,
    overtime_status: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
    current_employee=Depends(require_employee),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
):
    use_case = ListMyAttendance(
        employee_repo=employee_repo,
        attendance_repo=attendance_repo,
    )
    try:
        result = use_case.execute(
            MyAttendanceListRequest(
                user_id=current_employee.id,
                filters=_filters(
                    on_date=on_date,
                    date_from=date_from,
                    date_to=date_to,
                    status_value=status,
                    is_late=is_late,
                    is_early_departure=is_early_departure,
                    is_unscheduled=is_unscheduled,
                    is_missing_checkout=is_missing_checkout,
                    has_checkout=has_checkout,
                    justification_status=justification_status,
                    overtime_status=overtime_status,
                ),
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return AttendanceRecordListResponse(
        items=[_record_response(record) for record in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )
