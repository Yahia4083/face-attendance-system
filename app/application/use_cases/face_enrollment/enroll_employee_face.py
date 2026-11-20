"""Use case for initial face enrollment."""

import json

from app.application.dto.face_enrollment_dto import (
    EnrollEmployeeFaceRequest,
    EnrollEmployeeFaceResult,
)
from app.application.use_cases.exceptions import (
    BadRequestError,
    ConflictError,
    FaceEnrollmentValidationError,
    NotFoundError,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.face_embedding_repository import FaceEmbeddingRepositoryInterface
from app.domain.services.face_processing_service import (
    FaceEnrollmentBatchValidationError,
    FaceEnrollmentServiceInterface,
    FaceSimilarityServiceInterface,
)


class EnrollEmployeeFace:
    """Enroll new active embeddings for an employee."""

    def __init__(
        self,
        *,
        employee_repo: EmployeeRepositoryInterface,
        face_embedding_repo: FaceEmbeddingRepositoryInterface,
        face_enrollment_service: FaceEnrollmentServiceInterface,
        face_similarity_service: FaceSimilarityServiceInterface,
        audit_repo: AuditRepositoryInterface,
    ) -> None:
        self._employee_repo = employee_repo
        self._face_embedding_repo = face_embedding_repo
        self._face_enrollment_service = face_enrollment_service
        self._face_similarity_service = face_similarity_service
        self._audit_repo = audit_repo

    def execute(self, request: EnrollEmployeeFaceRequest) -> EnrollEmployeeFaceResult:
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        if not employee.is_active:
            raise BadRequestError("Employee is inactive")

        if not request.images:
            raise BadRequestError("No files uploaded")

        existing_active = self._face_embedding_repo.count_active_by_employee_id(request.employee_id)
        if existing_active > 0:
            raise ConflictError("Employee already has active face enrollment. Use /re-enroll instead.")

        saved_paths: list[str] = []
        try:
            # Validates uploaded images and generates FaceNet embeddings.
            generated = self._face_enrollment_service.validate_and_generate_embeddings(
                employee_id=request.employee_id,
                images=request.images,
            )
            embeddings = [item.embedding_vector for item in generated]
            # Validates that all generated embeddings belong to one person.
            self._face_similarity_service.validate_embeddings(embeddings)
            if not self._face_similarity_service.are_same_person(embeddings):
                raise ValueError("All uploaded images must belong to the same employee.")

            # Saves validated enrollment images and prepares embedding records.
            processed = self._face_enrollment_service.save_generated_images(
                employee_id=request.employee_id,
                generated_images=generated,
            )
            saved_paths = [item.image_path for item in processed]
            self._face_embedding_repo.create_many_embeddings(
                embeddings=[
                    {
                        "employee_id": request.employee_id,
                        "embedding_vector": item.embedding_vector,
                        "image_path": item.image_path,
                        "model_name": self._face_enrollment_service.model_name,
                        "is_active": True,
                    }
                    for item in processed
                ],
                commit=True,
            )
        except FaceEnrollmentBatchValidationError as error:
            if saved_paths:
                self._face_enrollment_service.cleanup_saved_images(saved_paths)
            raise FaceEnrollmentValidationError(error.issues) from error
        except ValueError as error:
            # Cleans up saved enrollment images after validation failure.
            if saved_paths:
                self._face_enrollment_service.cleanup_saved_images(saved_paths)
            raise BadRequestError(str(error))
        except RuntimeError as error:
            if saved_paths:
                self._face_enrollment_service.cleanup_saved_images(saved_paths)
            raise BadRequestError("Face enrollment processing failed. Please try again.") from error
        except Exception:
            if saved_paths:
                self._face_enrollment_service.cleanup_saved_images(saved_paths)
            raise

        active_embeddings = self._face_embedding_repo.count_active_by_employee_id(request.employee_id)

        # Writes the face-enrollment event to the audit log.
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="ENROLL_FACE",
            entity_type="FaceEmbedding",
            entity_id=request.employee_id,
            new_values=json.dumps(
                {
                    "employee_id": request.employee_id,
                    "enrolled_images": len(saved_paths),
                    "active_embeddings": active_embeddings,
                    "model_name": self._face_enrollment_service.model_name,
                    "detector_backend": "mtcnn",
                    "same_person_validation": True,
                }
            ),
            ip_address=request.ip_address,
        )

        return EnrollEmployeeFaceResult(
            employee_id=request.employee_id,
            employee_name=employee.full_name,
            enrolled_images=len(saved_paths),
            active_embeddings=active_embeddings,
            model_name=self._face_enrollment_service.model_name,
            message="Face enrollment completed successfully",
        )
