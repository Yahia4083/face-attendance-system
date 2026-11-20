"""Justification request API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.dto.justification_request_dto import (
    CreateJustificationRequestDTO,
    GetJustificationRequestDTO,
    GetMyJustificationRequestDTO,
    ListJustificationRequestsDTO,
    ListMyJustificationRequestsDTO,
    ReviewJustificationRequestDTO,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.application.use_cases.justifications.justification_management import (
    ApproveJustificationRequest,
    CreateJustificationRequest,
    GetJustificationRequest,
    GetMyJustificationRequest,
    ListJustificationRequests,
    ListMyJustificationRequests,
    RejectJustificationRequest,
)
from app.dependencies import (
    get_attendance_record_repository,
    get_audit_repository,
    get_clock,
    get_employee_repository,
    get_justification_request_repository,
    get_system_settings_provider,
)
from app.domain.repositories.attendance_record_repository import AttendanceRecordRepositoryInterface
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.justification_request_repository import (
    JustificationRequestFilters,
    JustificationRequestRepositoryInterface,
)
from app.domain.services.clock_service import ClockInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.infrastructure.security.permissions import require_admin, require_employee
from app.presentation.schemas.justification_request_schema import (
    JustificationRequestCreateRequest,
    JustificationRequestListResponse,
    JustificationRequestResponse,
    JustificationReviewRequest,
)
from app.shared.datetime_utils import local_isoformat, utc_to_local_isoformat

router = APIRouter(tags=["Justification Requests"])


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


def _response(item, *, message: Optional[str] = None) -> JustificationRequestResponse:
    employee = getattr(item, "employee", None)
    return JustificationRequestResponse(
        id=item.id,
        attendance_record_id=item.attendance_record_id,
        employee_id=item.employee_id,
        employee_name=employee.full_name if employee else None,
        request_type=item.request_type,
        reason=item.explanation,
        status=_status_value(item.status),
        reviewer_user_id=item.reviewed_by,
        reviewer_note=item.admin_comment,
        reviewed_at=local_isoformat(item.reviewed_at),
        created_at=utc_to_local_isoformat(item.created_at),
        updated_at=utc_to_local_isoformat(getattr(item, "updated_at", None)),
        message=message,
    )


def _filters(
    *,
    employee_id: Optional[int] = None,
    attendance_record_id: Optional[int] = None,
    request_type: Optional[str] = None,
    status_value: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> JustificationRequestFilters:
    return JustificationRequestFilters(
        employee_id=employee_id,
        attendance_record_id=attendance_record_id,
        request_type=request_type,
        status=status_value,
        date_from=date_from,
        date_to=date_to,
    )


@router.post(
    "/me/attendance/{attendance_id}/justification-requests",
    response_model=JustificationRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_my_justification_request(
    attendance_id: int,
    payload: JustificationRequestCreateRequest,
    request: Request,
    current_employee=Depends(require_employee),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    attendance_repo: AttendanceRecordRepositoryInterface = Depends(
        get_attendance_record_repository,
    ),
    justification_repo: JustificationRequestRepositoryInterface = Depends(
        get_justification_request_repository,
    ),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    settings_provider: SystemSettingsProviderInterface = Depends(get_system_settings_provider),
):
    use_case = CreateJustificationRequest(
        employee_repo=employee_repo,
        attendance_repo=attendance_repo,
        justification_repo=justification_repo,
        audit_repo=audit_repo,
        settings_provider=settings_provider,
    )
    try:
        item = use_case.execute(
            CreateJustificationRequestDTO(
                user_id=current_employee.id,
                attendance_record_id=attendance_id,
                request_type=payload.request_type,
                reason=payload.reason,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item, message="Justification request submitted successfully")


@router.get("/me/justification-requests", response_model=JustificationRequestListResponse)
def list_my_justification_requests(
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 10,
    current_employee=Depends(require_employee),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    justification_repo: JustificationRequestRepositoryInterface = Depends(
        get_justification_request_repository,
    ),
):
    use_case = ListMyJustificationRequests(
        employee_repo=employee_repo,
        justification_repo=justification_repo,
    )
    try:
        result = use_case.execute(
            ListMyJustificationRequestsDTO(
                user_id=current_employee.id,
                filters=_filters(status_value=status, date_from=date_from, date_to=date_to),
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return JustificationRequestListResponse(
        items=[_response(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/me/justification-requests/{request_id}", response_model=JustificationRequestResponse)
def get_my_justification_request(
    request_id: int,
    current_employee=Depends(require_employee),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    justification_repo: JustificationRequestRepositoryInterface = Depends(
        get_justification_request_repository,
    ),
):
    use_case = GetMyJustificationRequest(
        employee_repo=employee_repo,
        justification_repo=justification_repo,
    )
    try:
        item = use_case.execute(
            GetMyJustificationRequestDTO(user_id=current_employee.id, request_id=request_id)
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item)


@router.get("/justification-requests", response_model=JustificationRequestListResponse)
def list_justification_requests(
    employee_id: Optional[int] = None,
    attendance_record_id: Optional[int] = None,
    request_type: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    justification_repo: JustificationRequestRepositoryInterface = Depends(
        get_justification_request_repository,
    ),
):
    use_case = ListJustificationRequests(justification_repo)
    try:
        result = use_case.execute(
            ListJustificationRequestsDTO(
                filters=_filters(
                    employee_id=employee_id,
                    attendance_record_id=attendance_record_id,
                    request_type=request_type,
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
    return JustificationRequestListResponse(
        items=[_response(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/justification-requests/{request_id}", response_model=JustificationRequestResponse)
def get_justification_request(
    request_id: int,
    current_admin=Depends(require_admin),
    justification_repo: JustificationRequestRepositoryInterface = Depends(
        get_justification_request_repository,
    ),
):
    use_case = GetJustificationRequest(justification_repo)
    try:
        item = use_case.execute(GetJustificationRequestDTO(request_id=request_id))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item)


@router.patch(
    "/justification-requests/{request_id}/approve",
    response_model=JustificationRequestResponse,
)
def approve_justification_request(
    request_id: int,
    payload: JustificationReviewRequest,
    request: Request,
    current_admin=Depends(require_admin),
    justification_repo: JustificationRequestRepositoryInterface = Depends(
        get_justification_request_repository,
    ),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = ApproveJustificationRequest(
        justification_repo=justification_repo,
        audit_repo=audit_repo,
        clock=clock,
    )
    try:
        item = use_case.execute(
            ReviewJustificationRequestDTO(
                request_id=request_id,
                reviewer_user_id=current_admin.id,
                reviewer_note=payload.reviewer_note,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item, message="Justification request approved successfully")


@router.patch(
    "/justification-requests/{request_id}/reject",
    response_model=JustificationRequestResponse,
)
def reject_justification_request(
    request_id: int,
    payload: JustificationReviewRequest,
    request: Request,
    current_admin=Depends(require_admin),
    justification_repo: JustificationRequestRepositoryInterface = Depends(
        get_justification_request_repository,
    ),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
    clock: ClockInterface = Depends(get_clock),
):
    use_case = RejectJustificationRequest(
        justification_repo=justification_repo,
        audit_repo=audit_repo,
        clock=clock,
    )
    try:
        item = use_case.execute(
            ReviewJustificationRequestDTO(
                request_id=request_id,
                reviewer_user_id=current_admin.id,
                reviewer_note=payload.reviewer_note,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _response(item, message="Justification request rejected successfully")
