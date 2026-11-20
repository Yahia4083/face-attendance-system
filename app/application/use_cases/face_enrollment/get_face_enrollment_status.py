"""Use case for retrieving face enrollment status."""

from app.application.dto.face_enrollment_dto import (
    FaceEmployeeQueryRequest,
    FaceEnrollmentStatusResult,
)
from app.application.use_cases.exceptions import NotFoundError
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.face_embedding_repository import FaceEmbeddingRepositoryInterface


class GetFaceEnrollmentStatus:
    """Return active/inactive face enrollment status for an employee."""

    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        face_embedding_repo: FaceEmbeddingRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._face_embedding_repo = face_embedding_repo

    def execute(self, request: FaceEmployeeQueryRequest) -> FaceEnrollmentStatusResult:
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")

        active_embeddings = self._face_embedding_repo.count_active_by_employee_id(request.employee_id)
        inactive_embeddings = self._face_embedding_repo.count_inactive_by_employee_id(
            request.employee_id
        )
        latest = self._face_embedding_repo.get_latest_by_employee_id(request.employee_id)
        active_model_names = self._face_embedding_repo.get_active_model_names_by_employee_id(
            request.employee_id
        )

        return FaceEnrollmentStatusResult(
            employee_id=request.employee_id,
            employee_name=employee.full_name,
            has_face_enrollment=active_embeddings > 0,
            active_embeddings=active_embeddings,
            inactive_embeddings=inactive_embeddings,
            latest_enrollment_at=latest.created_at if latest else None,
            active_model_name=", ".join(active_model_names) if active_model_names else None,
        )
