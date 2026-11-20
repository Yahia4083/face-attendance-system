"""Department management API routes (admin only)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.application.dto.department_dto import (
    CreateDepartmentRequest as CreateDepartmentRequestDTO,
    DepartmentListParams,
    DepartmentStateChangeRequest,
    UpdateDepartmentRequest as UpdateDepartmentRequestDTO,
)
from app.application.use_cases.departments.activate_department import ActivateDepartment
from app.application.use_cases.departments.create_department import CreateDepartment
from app.application.use_cases.departments.deactivate_department import DeactivateDepartment
from app.application.use_cases.departments.get_department import GetDepartment
from app.application.use_cases.departments.list_departments import ListDepartments
from app.application.use_cases.departments.update_department import UpdateDepartment
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.dependencies import get_audit_repository, get_department_repository
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.infrastructure.security.permissions import require_admin
from app.presentation.schemas.department_schema import (
    DepartmentCreateRequest,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdateRequest,
)
from app.shared.datetime_utils import utc_to_local_isoformat

router = APIRouter(prefix="/departments", tags=["Departments"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


def _to_response(department) -> DepartmentResponse:
    return DepartmentResponse(
        id=department.id,
        name=department.name,
        description=department.description,
        is_active=department.is_active,
        created_at=utc_to_local_isoformat(department.created_at),
        updated_at=utc_to_local_isoformat(department.updated_at),
    )


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    body: DepartmentCreateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = CreateDepartment(department_repo=department_repo, audit_repo=audit_repo)
    try:
        department = use_case.execute(
            CreateDepartmentRequestDTO(
                name=body.name,
                description=body.description,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return _to_response(department)


@router.get("", response_model=DepartmentListResponse)
def list_departments(
    is_active: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_admin=Depends(require_admin),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
):
    _ = current_admin
    use_case = ListDepartments(department_repo=department_repo)
    result = use_case.execute(
        DepartmentListParams(
            is_active=is_active,
            search=search,
            page=page,
            page_size=page_size,
        )
    )
    return DepartmentListResponse(
        items=[_to_response(item) for item in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{department_id}", response_model=DepartmentResponse)
def get_department(
    department_id: int,
    current_admin=Depends(require_admin),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
):
    _ = current_admin
    use_case = GetDepartment(department_repo=department_repo)
    try:
        department = use_case.execute(department_id)
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(department)


@router.put("/{department_id}", response_model=DepartmentResponse)
def update_department(
    department_id: int,
    body: DepartmentUpdateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = UpdateDepartment(department_repo=department_repo, audit_repo=audit_repo)
    try:
        department = use_case.execute(
            UpdateDepartmentRequestDTO(
                department_id=department_id,
                name=body.name,
                description=body.description,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(department)


@router.patch("/{department_id}/activate", response_model=DepartmentResponse)
def activate_department(
    department_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = ActivateDepartment(department_repo=department_repo, audit_repo=audit_repo)
    try:
        department = use_case.execute(
            DepartmentStateChangeRequest(
                department_id=department_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(department)


@router.patch("/{department_id}/deactivate", response_model=DepartmentResponse)
def deactivate_department(
    department_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    department_repo: DepartmentRepositoryInterface = Depends(get_department_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = DeactivateDepartment(department_repo=department_repo, audit_repo=audit_repo)
    try:
        department = use_case.execute(
            DepartmentStateChangeRequest(
                department_id=department_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _to_response(department)
