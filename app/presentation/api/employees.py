"""Employee management API routes (admin only)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.application.dto.employee_dto import (
    CreateEmployeeRequest as CreateEmployeeRequestDTO,
    EmployeeListParams,
    EmployeeStateChangeRequest,
    UpdateEmployeeRequest as UpdateEmployeeRequestDTO,
)
from app.application.dto.auth_dto import (
    ResetEmployeePasswordRequest as ResetEmployeePasswordRequestDTO,
)
from app.application.use_cases.auth.password_management import ResetEmployeePassword
from app.application.use_cases.employees.activate_employee import ActivateEmployee
from app.application.use_cases.employees.create_employee import CreateEmployee
from app.application.use_cases.employees.deactivate_employee import DeactivateEmployee
from app.application.use_cases.employees.get_employee import GetEmployee, GetEmployeeByNumber
from app.application.use_cases.employees.list_employees import ListEmployees
from app.application.use_cases.employees.update_employee import UpdateEmployee
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.dependencies import (
    get_audit_repository,
    get_department_repository,
    get_employee_repository,
    get_user_repository,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.user_repository import UserRepositoryInterface
from app.infrastructure.security.permissions import require_admin
from app.presentation.schemas.employee_schema import (
    EmployeeCreateRequest,
    EmployeeListResponse,
    EmployeePasswordResetRequest,
    EmployeePasswordResetResponse,
    EmployeeResponse,
    EmployeeUpdateRequest,
)
from app.shared.datetime_utils import utc_to_local_isoformat

router = APIRouter(prefix="/employees", tags=["Employees"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


def _to_response(employee) -> EmployeeResponse:
    return EmployeeResponse(
        id=employee.id,
        user_id=employee.user_id,
        email=employee.user.email,
        department_id=employee.department_id,
        department_name=employee.department.name,
        full_name=employee.full_name,
        employee_number=employee.employee_number,
        phone=employee.phone,
        position=employee.position,
        is_active=employee.is_active,
        created_at=utc_to_local_isoformat(employee.created_at),
        updated_at=utc_to_local_isoformat(employee.updated_at),
    )


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: EmployeeCreateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = CreateEmployee(
        employee_repo=employee_repo,
        user_repo=user_repo,
        department_repo=department_repo,
        audit_repo=audit_repo,
    )
    try:
        employee = use_case.execute(
            CreateEmployeeRequestDTO(
                email=body.email,
                password=body.password,
                full_name=body.full_name,
                employee_number=body.employee_number,
                phone=body.phone,
                position=body.position,
                department_id=body.department_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return _to_response(employee)


@router.get("", response_model=EmployeeListResponse)
def list_employees(
    is_active: bool | None = Query(default=None),
    department_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
):
    _ = current_admin
    use_case = ListEmployees(employee_repo=employee_repo)
    result = use_case.execute(
        EmployeeListParams(
            is_active=is_active,
            department_id=department_id,
            search=search,
            page=page,
            page_size=page_size,
        )
    )
    return EmployeeListResponse(
        items=[_to_response(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/lookup/by-number", response_model=EmployeeResponse)
def get_employee_by_number(
    employee_number: str = Query(min_length=1, max_length=50),
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
):
    """Return a safe exact employee match for administrative lookup."""
    _ = current_admin
    use_case = GetEmployeeByNumber(employee_repo=employee_repo)
    try:
        employee = use_case.execute(employee_number)
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(employee)


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(
    employee_id: int,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
):
    _ = current_admin
    use_case = GetEmployee(employee_repo=employee_repo)
    try:
        employee = use_case.execute(employee_id)
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(employee)


@router.put("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: int,
    body: EmployeeUpdateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = UpdateEmployee(
        employee_repo=employee_repo,
        user_repo=user_repo,
        department_repo=department_repo,
        audit_repo=audit_repo,
    )
    try:
        employee = use_case.execute(
            UpdateEmployeeRequestDTO(
                employee_id=employee_id,
                email=body.email,
                full_name=body.full_name,
                phone=body.phone,
                position=body.position,
                department_id=body.department_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(employee)


@router.patch(
    "/{employee_id}/account/password",
    response_model=EmployeePasswordResetResponse,
)
def reset_employee_password(
    employee_id: int,
    body: EmployeePasswordResetRequest,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    """Reset an employee password without reading or returning the old one."""
    use_case = ResetEmployeePassword(
        employee_repo=employee_repo,
        user_repo=user_repo,
        audit_repo=audit_repo,
    )
    try:
        updated_user = use_case.execute(
            ResetEmployeePasswordRequestDTO(
                employee_id=employee_id,
                new_password=body.new_password,
                confirm_password=body.confirm_password,
                require_password_change=body.require_password_change,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return EmployeePasswordResetResponse(
        employee_id=employee_id,
        user_id=updated_user.id,
        require_password_change=bool(updated_user.must_change_password),
        message="Employee password was reset successfully.",
    )


@router.patch("/{employee_id}/activate", response_model=EmployeeResponse)
def activate_employee(
    employee_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = ActivateEmployee(employee_repo=employee_repo, audit_repo=audit_repo)
    try:
        employee = use_case.execute(
            EmployeeStateChangeRequest(
                employee_id=employee_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(employee)


@router.patch("/{employee_id}/deactivate", response_model=EmployeeResponse)
def deactivate_employee(
    employee_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = DeactivateEmployee(employee_repo=employee_repo, audit_repo=audit_repo)
    try:
        employee = use_case.execute(
            EmployeeStateChangeRequest(
                employee_id=employee_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(employee)
