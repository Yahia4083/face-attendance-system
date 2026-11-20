"""Face processing service contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


FaceLandmarks = dict[str, tuple[float, float]]


@dataclass(frozen=True)
class FaceDetectionResult:
    """Result returned by face detector."""

    face_count: int
    face_crop: Optional[Any] = None
    error_message: Optional[str] = None
    face_boxes: Optional[list[tuple[int, int, int, int]]] = None
    face_landmarks: Optional[FaceLandmarks] = None
    face_landmarks_list: Optional[list[FaceLandmarks]] = None
    frame_size: Optional[tuple[int, int]] = None
    preprocessing_version: str = "legacy-v1"


@dataclass(frozen=True)
class FaceImageData:
    """Upload payload normalized for use cases."""

    filename: str
    content: bytes


@dataclass(frozen=True)
class ProcessedFaceImage:
    """Processed and saved face image output."""

    image_path: str
    embedding_vector: list[float]


@dataclass(frozen=True)
class GeneratedFaceImage:
    """Validated face image with a generated embedding before final storage."""

    filename: str
    image_bytes: bytes
    embedding_vector: list[float]


@dataclass(frozen=True)
class FaceImageValidationIssue:
    """Safe validation problem associated with one uploaded enrollment image."""

    filename: str
    code: str
    message: str
    position: int


class FaceEnrollmentBatchValidationError(ValueError):
    """Reject an enrollment batch while preserving every per-file issue."""

    def __init__(self, issues: list[FaceImageValidationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("Some enrollment images need attention.")


class FaceDetectorInterface(ABC):
    """Abstraction for face detection."""

    @abstractmethod
    def detect_face(
        self,
        image_bytes: bytes,
        *,
        employee_id: Optional[int] = None,
        filename: Optional[str] = None,
    ) -> FaceDetectionResult:
        """Detect faces and return face crop when a single face is detected."""
        raise NotImplementedError


class FaceEmbedderInterface(ABC):
    """Abstraction for embedding generation."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the underlying embedding model name."""
        raise NotImplementedError

    @abstractmethod
    def generate_embedding(self, face_image: Any) -> list[float]:
        """Generate embedding vector for a single face image."""
        raise NotImplementedError


class FaceStorageServiceInterface(ABC):
    """Abstraction for face file storage."""

    @abstractmethod
    def save_employee_face_image(
        self,
        *,
        employee_id: int,
        image_bytes: bytes,
        original_filename: str,
        index: int,
    ) -> str:
        """Persist a face image and return relative storage path."""
        raise NotImplementedError

    @abstractmethod
    def delete_files(self, relative_paths: list[str]) -> None:
        """Delete provided files from storage if they exist."""
        raise NotImplementedError


class FaceEnrollmentServiceInterface(ABC):
    """Abstraction for image validation, face processing, and storage orchestration."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return current embedder model name."""
        raise NotImplementedError

    @abstractmethod
    def validate_and_generate_embeddings(
        self,
        *,
        employee_id: int,
        images: list[FaceImageData],
    ) -> list[GeneratedFaceImage]:
        """Validate images, detect exactly one face, and generate embeddings."""
        raise NotImplementedError

    @abstractmethod
    def save_generated_images(
        self,
        *,
        employee_id: int,
        generated_images: list[GeneratedFaceImage],
    ) -> list[ProcessedFaceImage]:
        """Persist already validated images and attach storage paths."""
        raise NotImplementedError

    @abstractmethod
    def process_and_store_images(
        self,
        *,
        employee_id: int,
        images: list[FaceImageData],
    ) -> list[ProcessedFaceImage]:
        """Validate images, generate embeddings, and save files."""
        raise NotImplementedError

    @abstractmethod
    def cleanup_saved_images(self, relative_paths: list[str]) -> None:
        """Remove saved files when the enrollment transaction fails."""
        raise NotImplementedError


class FaceSimilarityServiceInterface(ABC):
    """Abstraction for comparing face embedding vectors."""

    @abstractmethod
    def validate_embeddings(self, embeddings: list[list[float]]) -> None:
        """Ensure embeddings are non-empty, finite, and normalizable."""
        raise NotImplementedError

    @abstractmethod
    def are_same_person(self, embeddings: list[list[float]]) -> bool:
        """Return whether all embeddings in one request belong to one person."""
        raise NotImplementedError

    @abstractmethod
    def matches_existing_template(
        self,
        *,
        new_embeddings: list[list[float]],
        existing_embeddings: list[list[float]],
    ) -> bool:
        """Return whether new embeddings match an existing employee template."""
        raise NotImplementedError
