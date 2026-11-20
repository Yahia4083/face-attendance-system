"""Face embedding repository contract."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ActiveFaceEmbeddingForRecognition:
    """Active compatible embedding data used internally for recognition."""

    employee_id: int
    embedding_vector: list[float]
    model_name: str


class FaceEmbeddingRepositoryInterface(ABC):
    """Abstraction for face embedding persistence operations."""

    @abstractmethod
    def create_embedding(
        self,
        *,
        employee_id: int,
        embedding_vector: list[float],
        image_path: str,
        model_name: str,
        is_active: bool = True,
        commit: bool = True,
    ) -> Any:
        """Create a single embedding record."""
        raise NotImplementedError

    @abstractmethod
    def create_many_embeddings(
        self,
        *,
        embeddings: list[dict[str, Any]],
        commit: bool = True,
    ) -> list[Any]:
        """Create multiple embedding records."""
        raise NotImplementedError

    @abstractmethod
    def get_active_by_employee_id(self, employee_id: int) -> list[Any]:
        """Return active embeddings for an employee."""
        raise NotImplementedError

    @abstractmethod
    def get_active_embedding_vectors_by_employee_id(
        self,
        employee_id: int,
        *,
        model_name: str,
    ) -> list[list[float]]:
        """Return active embedding vectors for an employee and model."""
        raise NotImplementedError

    @abstractmethod
    def get_active_model_names_by_employee_id(self, employee_id: int) -> list[str]:
        """Return distinct active embedding model names for an employee."""
        raise NotImplementedError

    @abstractmethod
    def get_all_by_employee_id(self, employee_id: int) -> list[Any]:
        """Return all embeddings for an employee."""
        raise NotImplementedError

    @abstractmethod
    def count_active_by_employee_id(self, employee_id: int) -> int:
        """Count active embeddings for an employee."""
        raise NotImplementedError

    @abstractmethod
    def count_inactive_by_employee_id(self, employee_id: int) -> int:
        """Count inactive embeddings for an employee."""
        raise NotImplementedError

    @abstractmethod
    def deactivate_active_by_employee_id(
        self,
        employee_id: int,
        *,
        commit: bool = True,
    ) -> int:
        """Deactivate all active embeddings for an employee and return affected rows."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_by_employee_id(self, employee_id: int) -> Optional[Any]:
        """Return latest embedding record for an employee."""
        raise NotImplementedError

    @abstractmethod
    def get_active_compatible_embeddings_for_recognition(
        self,
        *,
        model_name: str,
    ) -> list[ActiveFaceEmbeddingForRecognition]:
        """Return active embeddings for active employees and a compatible model."""
        raise NotImplementedError
