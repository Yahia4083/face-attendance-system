"""Use case for deactivating face enrollment."""

import json

from app.application.dto.face_enrollment_dto import (
    DeactivateFaceEnrollmentResult,
    FaceEmployeeQueryRequest,
)
from app.application.use_cases.exceptions import NotFoundError
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.face_embedding_repository import FaceEmbeddingRepositoryInterface


class DeactivateFaceEnrollment:
    """Deactivate all active embeddings for an employee."""

    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        face_embedding_repo: FaceEmbeddingRepositoryInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._face_embedding_repo = face_embedding_repo
        self._audit_repo = audit_repo

    def execute(self, request: FaceEmployeeQueryRequest) -> DeactivateFaceEnrollmentResult:
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")

        previous_active = self._face_embedding_repo.count_active_by_employee_id(request.employee_id)
        deactivated = self._face_embedding_repo.deactivate_active_by_employee_id(
            request.employee_id,
            commit=True,
        )
        active_after = self._face_embedding_repo.count_active_by_employee_id(request.employee_id)

        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="DEACTIVATE_FACE_ENROLLMENT",
            entity_type="FaceEmbedding",
            entity_id=request.employee_id,
            old_values=json.dumps(
                {
                    "previous_active_embeddings": previous_active,
                }
            ),
            new_values=json.dumps(
                {
                    "active_embeddings": active_after,
                }
            ),
            ip_address=request.ip_address,
        )

        return DeactivateFaceEnrollmentResult(
            employee_id=request.employee_id,
            deactivated_embeddings=deactivated,
            message="Face enrollment deactivated successfully",
        )

