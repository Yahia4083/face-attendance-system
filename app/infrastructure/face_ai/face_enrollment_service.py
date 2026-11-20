"""Face enrollment processing service."""

from dataclasses import dataclass
import math
from typing import Any

from app.config import get_settings
from app.domain.services.face_processing_service import (
    FaceEnrollmentBatchValidationError,
    FaceEnrollmentServiceInterface,
    FaceImageData,
    FaceImageValidationIssue,
    FaceDetectorInterface,
    FaceEmbedderInterface,
    FaceStorageServiceInterface,
    GeneratedFaceImage,
    ProcessedFaceImage,
)
from app.infrastructure.face_ai.image_validator import ImageValidator
from app.infrastructure.face_ai.face_quality import FaceEnrollmentQualityValidator


@dataclass(frozen=True)
class _ValidatedFaceImage:
    """Enrollment image that passed every pre-embedding validation rule."""

    image: FaceImageData
    face_crop: Any
    position: int


class _FaceImageValidationFailure(ValueError):
    """Internal typed failure used to aggregate one image's validation issue."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class FaceEnrollmentService(FaceEnrollmentServiceInterface):
    """Validate images, detect faces, generate embeddings, and save files."""

    def __init__(
        self,
        *,
        image_validator: ImageValidator,
        detector: FaceDetectorInterface,
        embedder: FaceEmbedderInterface,
        storage_service: FaceStorageServiceInterface,
        quality_validator: FaceEnrollmentQualityValidator | None = None,
    ) -> None:
        self._image_validator = image_validator
        self._detector = detector
        self._embedder = embedder
        self._storage_service = storage_service
        self._quality_validator = quality_validator or FaceEnrollmentQualityValidator()
        settings = get_settings()
        self._min_images = settings.FACE_MIN_ENROLLMENT_IMAGES
        if settings.FACE_ALIGNMENT_ENABLED:
            self._min_images = max(
                self._min_images,
                settings.FACE_RECOMMENDED_ENROLLMENT_IMAGES,
            )
        self._max_images = settings.FACE_MAX_ENROLLMENT_IMAGES
        self._quality_enabled = settings.FACE_ENROLLMENT_QUALITY_ENABLED

    @property
    def model_name(self) -> str:
        return self._embedder.model_name

    def validate_and_generate_embeddings(
        self,
        *,
        employee_id: int,
        images: list[FaceImageData],
    ) -> list[GeneratedFaceImage]:
        if len(images) < self._min_images:
            raise ValueError(
                f"At least {self._min_images} face images are required for validated enrollment."
            )
        if len(images) > self._max_images:
            raise ValueError(f"Maximum number of images per request is {self._max_images}")

        validated_images: list[_ValidatedFaceImage] = []
        validation_issues: list[FaceImageValidationIssue] = []

        # Validates the complete set before FaceNet or persistent storage is used.
        for position, image in enumerate(images, start=1):
            image_name = image.filename or f"image_{position}"
            try:
                validated_images.append(
                    self._validate_face_image(
                        employee_id=employee_id,
                        image=image,
                        position=position,
                        image_name=image_name,
                    )
                )
            except _FaceImageValidationFailure as error:
                validation_issues.append(
                    FaceImageValidationIssue(
                        filename=image_name,
                        code=error.code,
                        message=error.message,
                        position=position,
                    )
                )

        if validation_issues:
            raise FaceEnrollmentBatchValidationError(validation_issues)

        generated_items: list[GeneratedFaceImage] = []
        embedding_issues: list[FaceImageValidationIssue] = []
        for validated in validated_images:
            try:
                embedding = self._embedder.generate_embedding(validated.face_crop)
                self._validate_embedding(embedding)
            except ValueError:
                embedding_issues.append(
                    FaceImageValidationIssue(
                        filename=validated.image.filename or f"image_{validated.position}",
                        code="FACE_PROCESSING_FAILED",
                        message=(
                            "A reliable face template could not be generated from this image. "
                            "Please choose another clear image."
                        ),
                        position=validated.position,
                    )
                )
                continue

            generated_items.append(
                GeneratedFaceImage(
                    filename=validated.image.filename,
                    image_bytes=validated.image.content,
                    embedding_vector=embedding,
                )
            )

        if embedding_issues:
            raise FaceEnrollmentBatchValidationError(embedding_issues)

        return generated_items

    def _validate_face_image(
        self,
        *,
        employee_id: int,
        image: FaceImageData,
        position: int,
        image_name: str,
    ) -> _ValidatedFaceImage:
        try:
            self._image_validator.validate(filename=image.filename, image_bytes=image.content)
        except ValueError as error:
            code, message = self._classify_file_validation_error(str(error))
            raise _FaceImageValidationFailure(code, message) from error

        detection = self._detector.detect_face(
            image.content,
            employee_id=employee_id,
            filename=image_name,
        )
        if detection.error_message:
            if detection.error_message == "Invalid image file":
                raise _FaceImageValidationFailure(
                    "INVALID_IMAGE",
                    "This image could not be read. Please choose another image.",
                )
            if "landmark" in detection.error_message.lower():
                raise _FaceImageValidationFailure(
                    "FACE_ALIGNMENT_FAILED",
                    "The face could not be aligned reliably. Please use a clear, frontal image.",
                )
            raise _FaceImageValidationFailure(
                "FACE_PROCESSING_FAILED",
                "The face could not be processed reliably. Please choose another clear image.",
            )
        if detection.face_count == 0:
            raise _FaceImageValidationFailure(
                "NO_FACE",
                "No clear face detected. Use an image where the employee's face is clearly visible.",
            )
        if detection.face_count > 1:
            raise _FaceImageValidationFailure(
                "MULTIPLE_FACES",
                "Multiple faces detected. Use an image containing only this employee.",
            )
        if detection.face_crop is None:
            raise _FaceImageValidationFailure(
                "INVALID_IMAGE",
                "This image could not be read. Please choose another image.",
            )

        if self._quality_enabled:
            quality = self._quality_validator.assess(detection)
            if not quality.accepted:
                code, message = self._classify_quality_error(quality.reason)
                raise _FaceImageValidationFailure(code, message)

        return _ValidatedFaceImage(
            image=image,
            face_crop=detection.face_crop,
            position=position,
        )

    @staticmethod
    def _classify_file_validation_error(reason: str) -> tuple[str, str]:
        normalized = reason.lower()
        if "format" in normalized:
            return (
                "INVALID_FORMAT",
                "Unsupported image format. Use a JPG, JPEG, or PNG image.",
            )
        if "too large" in normalized:
            return (
                "IMAGE_TOO_LARGE",
                "Image is larger than 5 MB. Please choose a smaller image.",
            )
        return (
            "INVALID_IMAGE",
            "This image could not be read. Please choose another image.",
        )

    @staticmethod
    def _classify_quality_error(reason: str | None) -> tuple[str, str]:
        safe_reason = reason or "The face image quality is not sufficient."
        normalized = safe_reason.lower()
        if "blurred" in normalized:
            return (
                "IMAGE_TOO_BLURRED",
                "Too blurred for reliable enrollment. Please replace this image with a sharper photo.",
            )
        if "too small" in normalized:
            return ("FACE_TOO_SMALL", "Face is too small. Use a closer image.")
        if "landmark" in normalized:
            return (
                "FACE_LANDMARKS_UNCLEAR",
                "Face landmarks are unclear. Please use a clear image looking directly at the camera.",
            )
        if "tilted" in normalized or "turned" in normalized or "frontal" in normalized:
            return ("FACE_POSE_INVALID", safe_reason)
        return ("IMAGE_QUALITY_FAILED", safe_reason)

    def save_generated_images(
        self,
        *,
        employee_id: int,
        generated_images: list[GeneratedFaceImage],
    ) -> list[ProcessedFaceImage]:
        processed_items: list[ProcessedFaceImage] = []
        saved_paths: list[str] = []

        try:
            for index, item in enumerate(generated_images, start=1):
                image_path = self._storage_service.save_employee_face_image(
                    employee_id=employee_id,
                    image_bytes=item.image_bytes,
                    original_filename=item.filename,
                    index=index,
                )
                saved_paths.append(image_path)
                processed_items.append(
                    ProcessedFaceImage(
                        image_path=image_path,
                        embedding_vector=item.embedding_vector,
                    )
                )
        except Exception:
            if saved_paths:
                self._storage_service.delete_files(saved_paths)
            raise

        return processed_items

    def process_and_store_images(
        self,
        *,
        employee_id: int,
        images: list[FaceImageData],
    ) -> list[ProcessedFaceImage]:
        generated = self.validate_and_generate_embeddings(
            employee_id=employee_id,
            images=images,
        )
        return self.save_generated_images(
            employee_id=employee_id,
            generated_images=generated,
        )

    def cleanup_saved_images(self, relative_paths: list[str]) -> None:
        self._storage_service.delete_files(relative_paths)

    @staticmethod
    def _validate_embedding(embedding: list[float]) -> None:
        if not embedding:
            raise ValueError("Failed to generate embedding vector")
        if not all(math.isfinite(value) for value in embedding):
            raise ValueError("Failed to generate a valid embedding vector")
