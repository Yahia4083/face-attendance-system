"""Pydantic schemas for face enrollment endpoints."""

from typing import Optional

from pydantic import BaseModel


class FaceEnrollmentResponse(BaseModel):
    employee_id: int
    employee_name: str
    enrolled_images: int
    active_embeddings: int
    model_name: str
    message: str


class FaceReEnrollmentResponse(BaseModel):
    employee_id: int
    employee_name: str
    deactivated_embeddings: int
    new_enrolled_images: int
    active_embeddings: int
    model_name: str
    message: str


class FaceImageValidationIssueResponse(BaseModel):
    filename: str
    code: str
    message: str
    position: int


class FaceEnrollmentValidationErrorDetail(BaseModel):
    success: bool = False
    message: str
    errors: list[FaceImageValidationIssueResponse]


class FaceEnrollmentValidationErrorResponse(BaseModel):
    detail: FaceEnrollmentValidationErrorDetail


class FaceEnrollmentStatusResponse(BaseModel):
    employee_id: int
    employee_name: str
    has_face_enrollment: bool
    active_embeddings: int
    inactive_embeddings: int
    latest_enrollment_at: Optional[str]
    active_model_name: Optional[str] = None


class FaceEmbeddingMetadataResponseItem(BaseModel):
    id: int
    image_path: str
    model_name: Optional[str]
    is_active: bool
    created_at: str


class FaceEmbeddingMetadataListResponse(BaseModel):
    employee_id: int
    items: list[FaceEmbeddingMetadataResponseItem]


class FaceDeactivateEnrollmentResponse(BaseModel):
    employee_id: int
    deactivated_embeddings: int
    message: str
