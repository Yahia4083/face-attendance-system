"""Use case for listing face embedding metadata."""

from app.application.dto.face_enrollment_dto import (
    FaceEmbeddingMetadata,
    FaceEmployeeQueryRequest,
    ListFaceEmbeddingsResult,
)
from app.application.use_cases.exceptions import NotFoundError
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.face_embedding_repository import FaceEmbeddingRepositoryInterface


class ListFaceEmbeddings:
    """List all embedding metadata for an employee."""

    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        face_embedding_repo: FaceEmbeddingRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._face_embedding_repo = face_embedding_repo

    def execute(self, request: FaceEmployeeQueryRequest) -> ListFaceEmbeddingsResult:
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")

        records = self._face_embedding_repo.get_all_by_employee_id(request.employee_id)

        return ListFaceEmbeddingsResult(
            employee_id=request.employee_id,
            items=[
                FaceEmbeddingMetadata(
                    id=item.id,
                    image_path=item.image_path,
                    model_name=item.model_name,
                    is_active=item.is_active,
                    created_at=item.created_at,
                )
                for item in records
            ],
        )

