"""Overtime request API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.dto.overtime_request_dto import (
    ApproveOvertimeRequestDTO,
    CreateOvertimeRequestDTO,
    GetMyOvertimeRequestDTO,
    GetOvertimeRequestDTO,
    ListMyOvertimeRequestsDTO,
    ListOvertimeRequestsDTO,
    RejectOvertimeRequestDTO,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.application.use_cases.overtime.overtime_management import (
    ApproveOvertimeRequest,
    CreateOvertimeRequest,
    GetMyOvertimeRequest,
    GetOvertimeRequest,
    ListMyOvertimeRequests,
    ListOvertimeRequests,
    RejectOvertimeRequest,
)
from app.dependencies import (
    get_attendance_record_repository,
    get_audit_repository,
    get_clock,
    get_employee_repository,
    get_overtime_request_repository,
    get_system_settings_provider,
)
from app.domain.repositories.attendance_record_repository import AttendanceRecordRepositoryInterface
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.overtime_request_repository import (
    OvertimeRequestFilters,
    OvertimeRequestRepositoryInterface,
)
from app.domain.services.clock_service import ClockInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.infrastructure.security.permissions import require_admin, require_employee
from app.presentation.schemas.overtime_request_schema import (
    OvertimeApproveRequest,
    OvertimeRejectRequest,
    OvertimeRequestCreateRequest,
    OvertimeRequestListResponse,
    OvertimeRequestResponse,
)
from app.shared.datetime_utils import local_isoformat, utc_to_local_isoformat

router = APIRouter(tags=["Overtime Requests"])


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


def _response(item, *, message: Optional[str] = None) -> OvertimeRequestResponse:
    employee = getattr(item, "employee", None)
    return OvertimeRequestResponse(
        id=item.id,
        employee_id=item.employee_id,
        employee_name=employee.full_name if employee else None,
        attendance_record_id=item.attendance_record_id,
        requested_minutes=item.overtime_minutes,
        eligible_minutes_at_submission=item.eligible_minutes_at_submission,
        approved_minutes=item.approved_minutes,
        reason=item.reason,
        status=_status_value(item.status),
        reviewer_user_id=item.reviewed_by,
        reviewer_note=item.reviewer_note,
        reviewed_at=local_isoformat(item.reviewed_at),
        created_at=utc_to_local_isoformat(item.created_at),
        updated_at=utc_to_local_isoformat(getattr(item, "updated_at", None)),
        message=message,
    )


def _filters(
    *,
    employee_id: Optional[int] = None,
    attendance_record_id: Optional[int] = None,
    status_value: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> OvertimeRequestFilters:
    return OvertimeRequestFilters(
        employee_id=employee_id,
        attendance_record_id=attendance_record_id,
        status=status_value,
        date_from=date_from,
        date_to=date_to,
    )


@router.post(
    "/me/attendance/{attendance_id}/overtime-requests",
    response_model=OvertimeRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_my_overtime_request(
    attendance_id: int,
    payload: OvertimeRequestCreateRequest,
    request: Request,
    current_employee=Depends(require_employee),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    overtime_repo: OvertimeRequestRepositoryInterface = Depends(get_overtime_request_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = CreateOvertimeRequest(
        employee_repo=employee_repo,
        attendance_repo=attendance_repo,
        overtime_repo=overtime_repo,
        audit_repo=audit_repo,
        settings_provider=settings_provider,
    )
    try:
        item = use_case.execute(
            CreateOvertimeRequestDTO(
                user_id=current_employee.id,
                attendance_record_id=attendance_id,
                requested_minutes=payload.requested_minutes,
                reason=payload.reason,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item, message="Overtime request submitted successfully")


@router.get("/me/overtime-requests", response_model=OvertimeRequestListResponse)
def list_my_overtime_requests(
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 10,
    current_employee=Depends(require_employee),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    overtime_repo: OvertimeRequestRepositoryInterface = Depends(get_overtime_request_repository),
):
    use_case = ListMyOvertimeRequests(employee_repo=employee_repo, overtime_repo=overtime_repo)
    try:
        result = use_case.execute(
            ListMyOvertimeRequestsDTO(
                user_id=current_employee.id,
                filters=_filters(status_value=status, date_from=date_from, date_to=date_to),
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return OvertimeRequestListResponse(
        items=[_response(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/me/overtime-requests/{request_id}", response_model=OvertimeRequestResponse)
def get_my_overtime_request(
    request_id: int,
    current_employee=Depends(require_employee),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    overtime_repo: OvertimeRequestRepositoryInterface = Depends(get_overtime_request_repository),
):
    use_case = GetMyOvertimeRequest(employee_repo=employee_repo, overtime_repo=overtime_repo)
    try:
        item = use_case.execute(
            GetMyOvertimeRequestDTO(user_id=current_employee.id, request_id=request_id)
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item)


@router.get("/overtime-requests", response_model=OvertimeRequestListResponse)
def list_overtime_requests(
    employee_id: Optional[int] = None,
    attendance_record_id: Optional[int] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    overtime_repo: OvertimeRequestRepositoryInterface = Depends(get_overtime_request_repository),
):
    use_case = ListOvertimeRequests(overtime_repo)
    try:
        result = use_case.execute(
            ListOvertimeRequestsDTO(
                filters=_filters(
                    employee_id=employee_id,
                    attendance_record_id=attendance_record_id,
                    status_value=status,
                    date_from=date_from,
                    date_to=date_to,
                ),
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return OvertimeRequestListResponse(
        items=[_response(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/overtime-requests/{request_id}", response_model=OvertimeRequestResponse)
def get_overtime_request(
    request_id: int,
    current_admin=Depends(require_admin),
    overtime_repo: OvertimeRequestRepositoryInterface = Depends(get_overtime_request_repository),
):
    use_case = GetOvertimeRequest(overtime_repo)
    try:
        item = use_case.execute(GetOvertimeRequestDTO(request_id=request_id))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item)


@router.patch("/overtime-requests/{request_id}/approve", response_model=OvertimeRequestResponse)
def approve_overtime_request(
    request_id: int,
    payload: OvertimeApproveRequest,
    request: Request,
    current_admin=Depends(require_admin),
    overtime_repo: OvertimeRequestRepositoryInterface = Depends(get_overtime_request_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = ApproveOvertimeRequest(
        overtime_repo=overtime_repo,
        audit_repo=audit_repo,
        clock=clock,
    )
    try:
        item = use_case.execute(
            ApproveOvertimeRequestDTO(
                request_id=request_id,
                reviewer_user_id=current_admin.id,
                approved_minutes=payload.approved_minutes,
                reviewer_note=payload.reviewer_note,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item, message="Overtime request approved successfully")


@router.patch("/overtime-requests/{request_id}/reject", response_model=OvertimeRequestResponse)
def reject_overtime_request(
    request_id: int,
    payload: OvertimeRejectRequest,
    request: Request,
    current_admin=Depends(require_admin),
    overtime_repo: OvertimeRequestRepositoryInterface = Depends(get_overtime_request_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = RejectOvertimeRequest(
        overtime_repo=overtime_repo,
        audit_repo=audit_repo,
        clock=clock,
    )
    try:
        item = use_case.execute(
            RejectOvertimeRequestDTO(
                request_id=request_id,
                reviewer_user_id=current_admin.id,
                reviewer_note=payload.reviewer_note,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item, message="Overtime request rejected successfully")
