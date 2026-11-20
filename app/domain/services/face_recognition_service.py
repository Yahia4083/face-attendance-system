"""Face recognition service contracts."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FaceRecognitionResult:
    """Result returned by the attendance face-recognition service."""

    matched: bool
    employee_id: Optional[int] = None
    matched_model_name: Optional[str] = None
    similarity_score: Optional[float] = None
    second_best_score: Optional[float] = None
    failure_reason: Optional[str] = None


class FaceRecognitionServiceInterface(ABC):
    """Recognize an active enrolled employee from one uploaded face image."""

    @abstractmethod
    def recognize(
        self,
        *,
        image_bytes: bytes,
        original_filename: str,
    ) -> FaceRecognitionResult:
        """Return the matched employee or a safe failure reason."""
        raise NotImplementedError
