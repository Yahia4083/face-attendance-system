"""DTOs for face enrollment use cases."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.domain.services.face_processing_service import FaceImageData


@dataclass(frozen=True)
class EnrollEmployeeFaceRequest:
    employee_id: int
    images: list[FaceImageData]
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class ReEnrollEmployeeFaceRequest:
    employee_id: int
    images: list[FaceImageData]
    actor_user_id: int
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class FaceEmployeeQueryRequest:
    employee_id: int
    actor_user_id: Optional[int] = None
    ip_address: Optional[str] = None


@dataclass(frozen=True)
class EnrollEmployeeFaceResult:
    employee_id: int
    employee_name: str
    enrolled_images: int
    active_embeddings: int
    model_name: str
    message: str


@dataclass(frozen=True)
class ReEnrollEmployeeFaceResult:
    employee_id: int
    employee_name: str
    deactivated_embeddings: int
    new_enrolled_images: int
    active_embeddings: int
    model_name: str
    message: str


@dataclass(frozen=True)
class FaceEnrollmentStatusResult:
    employee_id: int
    employee_name: str
    has_face_enrollment: bool
    active_embeddings: int
    inactive_embeddings: int
    latest_enrollment_at: Optional[datetime]
    active_model_name: Optional[str] = None


@dataclass(frozen=True)
class FaceEmbeddingMetadata:
    id: int
    image_path: str
    model_name: Optional[str]
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class ListFaceEmbeddingsResult:
    employee_id: int
    items: list[FaceEmbeddingMetadata]


@dataclass(frozen=True)
class DeactivateFaceEnrollmentResult:
    employee_id: int
    deactivated_embeddings: int
    message: str
