"""Face embedding similarity service."""

from __future__ import annotations

import logging

import numpy as np

from app.config import get_settings
from app.domain.services.face_processing_service import FaceSimilarityServiceInterface

logger = logging.getLogger(__name__)


class FaceSimilarityService(FaceSimilarityServiceInterface):
    """Validate whether FaceNet embeddings represent the same person."""

    def __init__(self) -> None:
        settings = get_settings()
        self._threshold = settings.FACE_SIMILARITY_THRESHOLD

    def validate_embeddings(self, embeddings: list[list[float]]) -> None:
        for embedding in embeddings:
            self._normalize(embedding)

    def are_same_person(self, embeddings: list[list[float]]) -> bool:
        normalized = [self._normalize(embedding) for embedding in embeddings]
        if len(normalized) < 2:
            return True

        for index, first in enumerate(normalized):
            for second in normalized[index + 1 :]:
                similarity = float(np.dot(first, second))
                logger.debug("Enrollment pairwise cosine similarity: %.4f", similarity)
                if similarity < self._threshold:
                    return False
        return True

    def matches_existing_template(
        self,
        *,
        new_embeddings: list[list[float]],
        existing_embeddings: list[list[float]],
    ) -> bool:
        new_template = self._build_template(new_embeddings)
        existing_template = self._build_template(existing_embeddings)
        similarity = float(np.dot(new_template, existing_template))
        logger.debug("Re-enrollment template cosine similarity: %.4f", similarity)
        return similarity >= self._threshold

    def _build_template(self, embeddings: list[list[float]]) -> np.ndarray:
        if not embeddings:
            raise ValueError("At least one embedding is required to build a template")

        normalized = [self._normalize(embedding) for embedding in embeddings]
        template = np.mean(np.stack(normalized), axis=0)
        norm = float(np.linalg.norm(template))
        if norm <= 0 or not np.isfinite(template).all():
            raise ValueError("Invalid face embedding template")
        return template / norm

    @staticmethod
    def _normalize(embedding: list[float]) -> np.ndarray:
        if not embedding:
            raise ValueError("Face embedding vector is empty")

        vector = np.asarray(embedding, dtype=np.float32)
        if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all():
            raise ValueError("Face embedding vector contains invalid values")

        norm = float(np.linalg.norm(vector))
        if norm <= 0:
            raise ValueError("Face embedding vector cannot be normalized")
        return vector / norm
