"""Schedule template API routes (admin only)."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.application.dto.schedule_dto import (
    ScheduleTemplateActionRequest,
    ScheduleTemplateListRequest,
    ScheduleTemplateMutationRequest,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.application.use_cases.schedules.schedule_management import (
    ActivateScheduleTemplate,
    CreateScheduleTemplate,
    DeactivateScheduleTemplate,
    GetScheduleTemplate,
    ListScheduleTemplates,
    UpdateScheduleTemplate,
)
from app.dependencies import get_audit_repository, get_schedule_template_repository
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.schedule_template_repository import (
    ScheduleTemplateRepositoryInterface,
)
from app.infrastructure.security.permissions import require_admin
from app.presentation.schemas.schedule_schema import (
    ScheduleTemplateCreateRequest,
    ScheduleTemplateListResponse,
    ScheduleTemplateResponse,
    ScheduleTemplateUpdateRequest,
)
from app.shared.datetime_utils import utc_to_local_isoformat

router = APIRouter(prefix="/schedule-templates", tags=["Schedule Templates"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


def _template_response(template) -> ScheduleTemplateResponse:
    return ScheduleTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        start_time=template.start_time,
        end_time=template.end_time,
        is_overnight=template.is_overnight,
        check_in_grace_minutes=template.check_in_grace_minutes,
        early_departure_tolerance_minutes=template.early_departure_tolerance_minutes,
        is_active=template.is_active,
        created_at=utc_to_local_isoformat(template.created_at),
        updated_at=utc_to_local_isoformat(template.updated_at),
    )


def _mutation_dto(
    payload: ScheduleTemplateCreateRequest | ScheduleTemplateUpdateRequest,
    *,
    actor_user_id: int,
    ip_address: Optional[str],
) -> ScheduleTemplateMutationRequest:
    return ScheduleTemplateMutationRequest(
        name=payload.name,
        description=payload.description,
        start_time=payload.start_time,
        end_time=payload.end_time,
        is_overnight=payload.is_overnight,
        check_in_grace_minutes=payload.check_in_grace_minutes,
        early_departure_tolerance_minutes=payload.early_departure_tolerance_minutes,
        actor_user_id=actor_user_id,
        ip_address=ip_address,
    )


@router.post("", response_model=ScheduleTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_schedule_template(
    payload: ScheduleTemplateCreateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = CreateScheduleTemplate(template_repo, audit_repo)
    try:
        template = use_case.execute(
            _mutation_dto(
                payload,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _template_response(template)


@router.get("", response_model=ScheduleTemplateListResponse)
def list_schedule_templates(
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = 1,
    page_size: int = 10,
    current_admin=Depends(require_admin),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
):
    _ = current_admin
    use_case = ListScheduleTemplates(template_repo)
    try:
        result = use_case.execute(
            ScheduleTemplateListRequest(
                search=search,
                is_active=is_active,
                page=page,
                page_size=page_size,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return ScheduleTemplateListResponse(
        items=[_template_response(item) for item in result.items],
        page=result.page,
        page_size=result.page_size,
        total=result.total,
    )


@router.get("/{template_id}", response_model=ScheduleTemplateResponse)
def get_schedule_template(
    template_id: int,
    current_admin=Depends(require_admin),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
):
    _ = current_admin
    use_case = GetScheduleTemplate(template_repo)
    try:
        template = use_case.execute(template_id)
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _template_response(template)


@router.put("/{template_id}", response_model=ScheduleTemplateResponse)
def update_schedule_template(
    template_id: int,
    payload: ScheduleTemplateUpdateRequest,
    request: Request,
    current_admin=Depends(require_admin),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = UpdateScheduleTemplate(template_repo, audit_repo)
    try:
        template = use_case.execute(
            template_id,
            _mutation_dto(
                payload,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            ),
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _template_response(template)


@router.patch("/{template_id}/activate", response_model=ScheduleTemplateResponse)
def activate_schedule_template(
    template_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = ActivateScheduleTemplate(template_repo, audit_repo)
    try:
        template = use_case.execute(
            ScheduleTemplateActionRequest(
                template_id=template_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _template_response(template)


@router.patch("/{template_id}/deactivate", response_model=ScheduleTemplateResponse)
def deactivate_schedule_template(
    template_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    template_repo: ScheduleTemplateRepositoryInterface = Depends(get_schedule_template_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = DeactivateScheduleTemplate(template_repo, audit_repo)
    try:
        template = use_case.execute(
            ScheduleTemplateActionRequest(
                template_id=template_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)
    return _template_response(template)
