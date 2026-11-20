"""Employee schedule assignment API routes."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.dto.schedule_dto import (
    EffectiveScheduleRequest,
    EmployeeScheduleActionRequest,
    EmployeeScheduleListRequest,
    EmployeeScheduleMutationRequest,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.application.use_cases.schedules.schedule_management import (
    ActivateEmployeeSchedule,
    AssignEmployeeSchedule,
    DeactivateEmployeeSchedule,
    GetEffectiveEmployeeSchedule,
    GetEmployeeSchedule,
    ListEmployeeSchedules,
    UpdateEmployeeSchedule,
)
from app.dependencies import (
    get_audit_repository,
    get_employee_repository,
    get_employee_schedule_repository,
    get_schedule_template_repository,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.employee_schedule_repository import EmployeeScheduleRepositoryInterface
from app.domain.repositories.schedule_template_repository import (
    ScheduleTemplateRepositoryInterface,
)
from app.infrastructure.security.permissions import require_admin, require_employee
from app.presentation.schemas.schedule_schema import (
    EffectiveScheduleResponse,
    EmployeeScheduleCreateRequest,
    EmployeeScheduleDeactivateResponse,
    EmployeeScheduleListItem,
    EmployeeScheduleListResponse,
    EmployeeScheduleResponse,
    EmployeeScheduleUpdateRequest,
)
from app.shared.datetime_utils import local_isoformat, utc_to_local_isoformat

router = APIRouter(tags=["Employee Schedules"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


def _working_days(assignment) -> list[int]:
    return [int(day) for day in (assignment.working_days or "").split(",") if day != ""]


def _assignment_response(assignment, *, employee_name: Optional[str] = None) -> EmployeeScheduleResponse:
    template = assignment.schedule_template
    return EmployeeScheduleResponse(
        id=assignment.id,
        employee_id=assignment.employee_id,
        employee_name=employee_name,
        schedule_template_id=assignment.schedule_template_id,
        schedule_template_name=template.name if template else None,
        effective_from=assignment.effective_start_date,
        effective_to=assignment.effective_end_date,
        working_days=_working_days(assignment),
        is_active=assignment.is_active,
        created_at=utc_to_local_isoformat(assignment.created_at),
        updated_at=utc_to_local_isoformat(assignment.updated_at),
    )


def _assignment_list_item(assignment) -> EmployeeScheduleListItem:
    template = assignment.schedule_template
    return EmployeeScheduleListItem(
        id=assignment.id,
        schedule_template_id=assignment.schedule_template_id,
        schedule_template_name=template.name if template else None,
        effective_from=assignment.effective_start_date,
        effective_to=assignment.effective_end_date,
        working_days=_working_days(assignment),
        is_active=assignment.is_active,
        created_at=utc_to_local_isoformat(assignment.created_at),
        updated_at=utc_to_local_isoformat(assignment.updated_at),
    )


def _mutation_dto(
    employee_id: int,
    payload: EmployeeScheduleCreateRequest | EmployeeScheduleUpdateRequest,
    *,
    actor_user_id: int,
    ip_address: Optional[str],
) -> EmployeeScheduleMutationRequest:
    return EmployeeScheduleMutationRequest(
        employee_id=employee_id,
        schedule_template_id=payload.schedule_template_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        working_days=payload.working_days,
        actor_user_id=actor_user_id,
        ip_address=ip_address,
    )


def _effective_response(result) -> EffectiveScheduleResponse:
    return EffectiveScheduleResponse(
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        on_date=result.on_date,
        has_schedule=result.has_schedule,
        assignment_id=result.assignment_id,
        schedule_template_id=result.schedule_template_id,
        schedule_template_name=result.schedule_template_name,
        working_day=result.working_day,
        scheduled_start_datetime=local_isoformat(result.scheduled_start_datetime),
        scheduled_end_datetime=local_isoformat(result.scheduled_end_datetime),
        is_overnight=result.is_overnight,
        check_in_grace_minutes=result.check_in_grace_minutes,
        early_departure_tolerance_minutes=result.early_departure_tolerance_minutes,
        timezone=result.timezone,
        message=result.message,
    )


@router.post(
    "/employees/{employee_id}/schedules",
    response_model=EmployeeScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_employee_schedule(
    employee_id: int,
    payload: EmployeeScheduleCreateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(get_employee_schedule_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = AssignEmployeeSchedule(employee_repo, template_repo, schedule_repo, audit_repo)
    try:
        assignment = use_case.execute(
            _mutation_dto(
                employee_id,
                payload,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    employee = employee_repo.get_by_id(employee_id)
    return _assignment_response(
        assignment,
        employee_name=employee.full_name if employee else None,
    )


@router.get("/employees/{employee_id}/schedules", response_model=EmployeeScheduleListResponse)
def list_employee_schedules(
    employee_id: int,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(get_employee_schedule_repository),
):
    _ = current_admin
    use_case = ListEmployeeSchedules(employee_repo, schedule_repo)
    try:
        result = use_case.execute(
            EmployeeScheduleListRequest(
                employee_id=employee_id,
                is_active=is_active,
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return EmployeeScheduleListResponse(
        employee_id=result.employee_id,
        items=[_assignment_list_item(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get(
    "/employees/{employee_id}/schedules/effective",
    response_model=EffectiveScheduleResponse,
)
def get_effective_employee_schedule(
    employee_id: int,
    on_date: date,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(get_employee_schedule_repository),
):
    _ = current_admin
    use_case = GetEffectiveEmployeeSchedule(employee_repo, schedule_repo)
    try:
        result = use_case.execute(EffectiveScheduleRequest(employee_id=employee_id, on_date=on_date))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _effective_response(result)


@router.get(
    "/employees/{employee_id}/schedules/{assignment_id}",
    response_model=EmployeeScheduleResponse,
)
def get_employee_schedule(
    employee_id: int,
    assignment_id: int,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(get_employee_schedule_repository),
):
    _ = current_admin
    use_case = GetEmployeeSchedule(employee_repo, schedule_repo)
    try:
        assignment = use_case.execute(
            EmployeeScheduleActionRequest(employee_id=employee_id, assignment_id=assignment_id)
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    employee = employee_repo.get_by_id(employee_id)
    return _assignment_response(
        assignment,
        employee_name=employee.full_name if employee else None,
    )


@router.put(
    "/employees/{employee_id}/schedules/{assignment_id}",
    response_model=EmployeeScheduleResponse,
)
def update_employee_schedule(
    employee_id: int,
    assignment_id: int,
    payload: EmployeeScheduleUpdateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(get_employee_schedule_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = UpdateEmployeeSchedule(employee_repo, template_repo, schedule_repo, audit_repo)
    try:
        assignment = use_case.execute(
            assignment_id,
            _mutation_dto(
                employee_id,
                payload,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            ),
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    employee = employee_repo.get_by_id(employee_id)
    return _assignment_response(
        assignment,
        employee_name=employee.full_name if employee else None,
    )


@router.patch(
    "/employees/{employee_id}/schedules/{assignment_id}/activate",
    response_model=EmployeeScheduleResponse,
)
def activate_employee_schedule(
    employee_id: int,
    assignment_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(get_employee_schedule_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = ActivateEmployeeSchedule(employee_repo, template_repo, schedule_repo, audit_repo)
    try:
        assignment = use_case.execute(
            EmployeeScheduleActionRequest(
                employee_id=employee_id,
                assignment_id=assignment_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    employee = employee_repo.get_by_id(employee_id)
    return _assignment_response(
        assignment,
        employee_name=employee.full_name if employee else None,
    )


@router.patch(
    "/employees/{employee_id}/schedules/{assignment_id}/deactivate",
    response_model=EmployeeScheduleDeactivateResponse,
)
def deactivate_employee_schedule(
    employee_id: int,
    assignment_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(get_employee_schedule_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = DeactivateEmployeeSchedule(employee_repo, schedule_repo, audit_repo)
    try:
        assignment = use_case.execute(
            EmployeeScheduleActionRequest(
                employee_id=employee_id,
                assignment_id=assignment_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return EmployeeScheduleDeactivateResponse(
        id=assignment.id,
        employee_id=assignment.employee_id,
        schedule_template_id=assignment.schedule_template_id,
        is_active=assignment.is_active,
        message="Employee schedule assignment deactivated successfully",
    )


@router.get("/me/schedules/effective", response_model=EffectiveScheduleResponse)
def get_my_effective_schedule(
    on_date: date,
    current_employee_user=Depends(require_employee),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    schedule_repo: EmployeeScheduleRepositoryInterface = Depends(get_employee_schedule_repository),
):
    employee = employee_repo.get_by_user_id(current_employee_user.id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee profile not found for current user",
        )
    use_case = GetEffectiveEmployeeSchedule(employee_repo, schedule_repo)
    try:
        result = use_case.execute(EffectiveScheduleRequest(employee_id=employee.id, on_date=on_date))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _effective_response(result)
