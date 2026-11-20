"""Use case for face re-enrollment."""

import json

from app.application.dto.face_enrollment_dto import (
    ReEnrollEmployeeFaceRequest,
    ReEnrollEmployeeFaceResult,
)
from app.application.use_cases.exceptions import (
    BadRequestError,
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


class ReEnrollEmployeeFace:
    """Replace active embeddings with a new enrollment set."""

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

    def execute(self, request: ReEnrollEmployeeFaceRequest) -> ReEnrollEmployeeFaceResult:
        employee = self._employee_repo.get_by_id(request.employee_id)
        if employee is None:
            raise NotFoundError("Employee not found")
        if not employee.is_active:
            raise BadRequestError("Employee is inactive")

        if not request.images:
            raise BadRequestError("No files uploaded")

        previous_active = self._face_embedding_repo.count_active_by_employee_id(request.employee_id)
        previous_model_names = self._face_embedding_repo.get_active_model_names_by_employee_id(
            request.employee_id
        )
        previous_model_name = ", ".join(previous_model_names) if previous_model_names else None

        saved_paths: list[str] = []
        try:
            # Validates uploaded replacement images and generates embeddings.
            generated = self._face_enrollment_service.validate_and_generate_embeddings(
                employee_id=request.employee_id,
                images=request.images,
            )
            embeddings = [item.embedding_vector for item in generated]
            # Validates that all replacement embeddings belong to one person.
            self._face_similarity_service.validate_embeddings(embeddings)
            if not self._face_similarity_service.are_same_person(embeddings):
                raise ValueError("All uploaded images must belong to the same employee.")

            existing_compatible_embeddings = (
                self._face_embedding_repo.get_active_embedding_vectors_by_employee_id(
                    request.employee_id,
                    model_name=self._face_enrollment_service.model_name,
                )
            )
            # Compares replacement embeddings with the current active template.
            if existing_compatible_embeddings and not self._face_similarity_service.matches_existing_template(
                new_embeddings=embeddings,
                existing_embeddings=existing_compatible_embeddings,
            ):
                raise ValueError("Uploaded faces do not match the currently enrolled employee.")

            processed = self._face_enrollment_service.save_generated_images(
                employee_id=request.employee_id,
                generated_images=generated,
            )
            saved_paths = [item.image_path for item in processed]

            # Deactivates current embeddings and inserts the replacement embeddings.
            deactivated_embeddings = self._face_embedding_repo.deactivate_active_by_employee_id(
                request.employee_id,
                commit=False,
            )
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
            # Cleans up saved replacement images after failure.
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

        # Writes the face re-enrollment event to the audit log.
        self._audit_repo.log(
            actor_user_id=request.actor_user_id,
            action="RE_ENROLL_FACE",
            entity_type="FaceEmbedding",
            entity_id=request.employee_id,
            old_values=json.dumps(
                {
                    "previous_active_embeddings": previous_active,
                    "previous_model_name": previous_model_name,
                }
            ),
            new_values=json.dumps(
                {
                    "employee_id": request.employee_id,
                    "new_enrolled_images": len(saved_paths),
                    "active_embeddings": active_embeddings,
                    "model_name": self._face_enrollment_service.model_name,
                    "detector_backend": "mtcnn",
                    "same_person_validation": True,
                    "previous_model_name": previous_model_name,
                }
            ),
            ip_address=request.ip_address,
        )

        return ReEnrollEmployeeFaceResult(
            employee_id=request.employee_id,
            employee_name=employee.full_name,
            deactivated_embeddings=deactivated_embeddings,
            new_enrolled_images=len(saved_paths),
            active_embeddings=active_embeddings,
            model_name=self._face_enrollment_service.model_name,
            message="Face re-enrollment completed successfully",
        )
