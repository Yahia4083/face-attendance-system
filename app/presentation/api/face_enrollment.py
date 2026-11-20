"""Face enrollment API routes (admin only)."""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.application.dto.face_enrollment_dto import (
    EnrollEmployeeFaceRequest,
    FaceEmployeeQueryRequest,
    ReEnrollEmployeeFaceRequest,
)
from app.application.use_cases.exceptions import (
    BadRequestError,
    ConflictError,
    FaceEnrollmentValidationError,
    NotFoundError,
)
from app.application.use_cases.face_enrollment.deactivate_face_enrollment import (
    DeactivateFaceEnrollment,
)
from app.application.use_cases.face_enrollment.enroll_employee_face import EnrollEmployeeFace
from app.application.use_cases.face_enrollment.get_face_enrollment_status import (
    GetFaceEnrollmentStatus,
)
from app.application.use_cases.face_enrollment.list_face_embeddings import ListFaceEmbeddings
from app.application.use_cases.face_enrollment.re_enroll_employee_face import (
    ReEnrollEmployeeFace,
)
from app.dependencies import (
    get_audit_repository,
    get_employee_repository,
    get_face_embedding_repository,
    get_face_enrollment_service,
    get_face_similarity_service,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.face_embedding_repository import FaceEmbeddingRepositoryInterface
from app.domain.services.face_processing_service import (
    FaceEnrollmentServiceInterface,
    FaceImageData,
    FaceSimilarityServiceInterface,
)
from app.infrastructure.security.permissions import require_admin
from app.presentation.schemas.face_enrollment_schema import (
    FaceDeactivateEnrollmentResponse,
    FaceEmbeddingMetadataListResponse,
    FaceEmbeddingMetadataResponseItem,
    FaceEnrollmentResponse,
    FaceEnrollmentStatusResponse,
    FaceEnrollmentValidationErrorResponse,
    FaceReEnrollmentResponse,
)
from app.shared.datetime_utils import utc_to_local_isoformat

router = APIRouter(prefix="/employees", tags=["Face Enrollment"])


def _raise_http_error(error: Exception) -> None:
    if isinstance(error, FaceEnrollmentValidationError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "message": str(error),
                "errors": [
                    {
                        "filename": issue.filename,
                        "code": issue.code,
                        "message": issue.message,
                        "position": issue.position,
                    }
                    for issue in error.issues
                ],
            },
        )
    if isinstance(error, BadRequestError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if isinstance(error, ConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    if isinstance(error, NotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    raise error


async def _read_files(files: list[UploadFile] | None) -> list[FaceImageData]:
    if not files:
        return []

    payloads: list[FaceImageData] = []
    for upload in files:
        content = await upload.read()
        payloads.append(
            FaceImageData(
                filename=upload.filename or "",
                content=content,
            )
        )
        await upload.close()
    return payloads


@router.post(
    "/{employee_id}/face/enroll",
    response_model=FaceEnrollmentResponse,
    responses={400: {"model": FaceEnrollmentValidationErrorResponse}},
)
async def enroll_face(
    employee_id: int,
    request: Request,
    files: list[UploadFile] | None = File(default=None),
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    face_embedding_repo: FaceEmbeddingRepositoryInterface = Depends(get_face_embedding_repository),
    face_enrollment_service: FaceEnrollmentServiceInterface = Depends(get_face_enrollment_service),
    face_similarity_service: FaceSimilarityServiceInterface = Depends(get_face_similarity_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = EnrollEmployeeFace(
        employee_repo=employee_repo,
        face_embedding_repo=face_embedding_repo,
        face_enrollment_service=face_enrollment_service,
        face_similarity_service=face_similarity_service,
        audit_repo=audit_repo,
    )
    try:
        result = use_case.execute(
            EnrollEmployeeFaceRequest(
                employee_id=employee_id,
                images=await _read_files(files),
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return FaceEnrollmentResponse(
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        enrolled_images=result.enrolled_images,
        active_embeddings=result.active_embeddings,
        model_name=result.model_name,
        message=result.message,
    )


@router.post(
    "/{employee_id}/face/re-enroll",
    response_model=FaceReEnrollmentResponse,
    responses={400: {"model": FaceEnrollmentValidationErrorResponse}},
)
async def re_enroll_face(
    employee_id: int,
    request: Request,
    files: list[UploadFile] | None = File(default=None),
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    face_embedding_repo: FaceEmbeddingRepositoryInterface = Depends(get_face_embedding_repository),
    face_enrollment_service: FaceEnrollmentServiceInterface = Depends(get_face_enrollment_service),
    face_similarity_service: FaceSimilarityServiceInterface = Depends(get_face_similarity_service),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = ReEnrollEmployeeFace(
        employee_repo=employee_repo,
        face_embedding_repo=face_embedding_repo,
        face_enrollment_service=face_enrollment_service,
        face_similarity_service=face_similarity_service,
        audit_repo=audit_repo,
    )
    try:
        result = use_case.execute(
            ReEnrollEmployeeFaceRequest(
                employee_id=employee_id,
                images=await _read_files(files),
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return FaceReEnrollmentResponse(
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        deactivated_embeddings=result.deactivated_embeddings,
        new_enrolled_images=result.new_enrolled_images,
        active_embeddings=result.active_embeddings,
        model_name=result.model_name,
        message=result.message,
    )


@router.get("/{employee_id}/face/status", response_model=FaceEnrollmentStatusResponse)
def get_face_status(
    employee_id: int,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    face_embedding_repo: FaceEmbeddingRepositoryInterface = Depends(get_face_embedding_repository),
):
    _ = current_admin
    use_case = GetFaceEnrollmentStatus(
        employee_repo=employee_repo,
        face_embedding_repo=face_embedding_repo,
    )
    try:
        result = use_case.execute(FaceEmployeeQueryRequest(employee_id=employee_id))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return FaceEnrollmentStatusResponse(
        employee_id=result.employee_id,
        employee_name=result.employee_name,
        has_face_enrollment=result.has_face_enrollment,
        active_embeddings=result.active_embeddings,
        inactive_embeddings=result.inactive_embeddings,
        latest_enrollment_at=utc_to_local_isoformat(result.latest_enrollment_at),
        active_model_name=result.active_model_name,
    )


@router.get("/{employee_id}/face/embeddings", response_model=FaceEmbeddingMetadataListResponse)
def list_face_embeddings(
    employee_id: int,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    face_embedding_repo: FaceEmbeddingRepositoryInterface = Depends(get_face_embedding_repository),
):
    _ = current_admin
    use_case = ListFaceEmbeddings(
        employee_repo=employee_repo,
        face_embedding_repo=face_embedding_repo,
    )
    try:
        result = use_case.execute(FaceEmployeeQueryRequest(employee_id=employee_id))
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return FaceEmbeddingMetadataListResponse(
        employee_id=result.employee_id,
        items=[
            FaceEmbeddingMetadataResponseItem(
                id=item.id,
                image_path=item.image_path,
                model_name=item.model_name,
                is_active=item.is_active,
                created_at=utc_to_local_isoformat(item.created_at),
            )
            for item in result.items
        ],
    )


@router.patch("/{employee_id}/face/deactivate", response_model=FaceDeactivateEnrollmentResponse)
def deactivate_face_enrollment(
    employee_id: int,
    request: Request,
    current_admin=Depends(require_admin),
    employee_repo: EmployeeRepositoryInterface = Depends(get_employee_repository),
    face_embedding_repo: FaceEmbeddingRepositoryInterface = Depends(get_face_embedding_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
):
    use_case = DeactivateFaceEnrollment(
        employee_repo=employee_repo,
        face_embedding_repo=face_embedding_repo,
        audit_repo=audit_repo,
    )
    try:
        result = use_case.execute(
            FaceEmployeeQueryRequest(
                employee_id=employee_id,
                actor_user_id=current_admin.id,
                ip_address=request.client.host if request.client else None,
            )
        )
    except (BadRequestError, ConflictError, NotFoundError) as error:
        _raise_http_error(error)

    return FaceDeactivateEnrollmentResponse(
        employee_id=result.employee_id,
        deactivated_embeddings=result.deactivated_embeddings,
        message=result.message,
    )
