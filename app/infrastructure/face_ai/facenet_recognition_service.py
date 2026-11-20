"""FaceNet-based attendance recognition service."""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from app.domain.repositories.face_embedding_repository import FaceEmbeddingRepositoryInterface
from app.domain.services.face_processing_service import FaceDetectorInterface, FaceEmbedderInterface
from app.domain.services.face_recognition_service import (
    FaceRecognitionResult,
    FaceRecognitionServiceInterface,
)
from app.infrastructure.face_ai.image_validator import ImageValidator
from app.infrastructure.face_ai.recognition_policy import (
    RecognitionPolicy,
    aggregate_similarity,
)


class FaceNetRecognitionService(FaceRecognitionServiceInterface):
    """Recognize active employees from compatible active FaceNet embeddings."""

    def __init__(
        self,
        *,
        image_validator: ImageValidator,
        detector: FaceDetectorInterface,
        embedder: FaceEmbedderInterface,
        face_embedding_repo: FaceEmbeddingRepositoryInterface,
    ) -> None:
        self._image_validator = image_validator
        self._detector = detector
        self._embedder = embedder
        self._face_embedding_repo = face_embedding_repo
        self._policy = RecognitionPolicy.from_settings(model_name=self._embedder.model_name)

    def recognize(
        self,
        *,
        image_bytes: bytes,
        original_filename: str,
    ) -> FaceRecognitionResult:
        self._image_validator.validate(filename=original_filename, image_bytes=image_bytes)

        detection = self._detector.detect_face(image_bytes, filename=original_filename)
        if detection.error_message:
            if detection.error_message == "Invalid image file":
                raise ValueError(f"Invalid image file: {original_filename}")
            raise ValueError(detection.error_message)
        if detection.face_count == 0:
            raise ValueError(f"No face detected in uploaded image: {original_filename}")
        if detection.face_count > 1:
            raise ValueError(f"Multiple faces detected in uploaded image: {original_filename}")
        if detection.face_crop is None:
            raise ValueError(f"Invalid image file: {original_filename}")

        query_embedding = self._normalize(self._embedder.generate_embedding(detection.face_crop))
        candidates = self._build_candidate_embeddings()
        if not candidates:
            return FaceRecognitionResult(matched=False, failure_reason="no_match")

        scored_candidates = [
            (
                employee_id,
                aggregate_similarity(
                    np.asarray(query_embedding, dtype=np.float32),
                    [np.asarray(item, dtype=np.float32) for item in embeddings],
                    strategy=self._policy.aggregation,
                    top_k=self._policy.top_k,
                ),
            )
            for employee_id, embeddings in candidates.items()
        ]
        scored_candidates.sort(key=lambda item: item[1], reverse=True)

        best_employee_id, best_score = scored_candidates[0]
        second_best_score = scored_candidates[1][1] if len(scored_candidates) > 1 else None

        if best_score < self._policy.threshold:
            return FaceRecognitionResult(
                matched=False,
                similarity_score=best_score,
                second_best_score=second_best_score,
                failure_reason="no_match",
            )
        if (
            second_best_score is not None
            and best_score - second_best_score < self._policy.ambiguity_margin
        ):
            return FaceRecognitionResult(
                matched=False,
                similarity_score=best_score,
                second_best_score=second_best_score,
                failure_reason="ambiguous",
            )

        return FaceRecognitionResult(
            matched=True,
            employee_id=best_employee_id,
            matched_model_name=self._embedder.model_name,
            similarity_score=best_score,
            second_best_score=second_best_score,
        )

    def _build_candidate_embeddings(self) -> dict[int, list[list[float]]]:
        records = self._face_embedding_repo.get_active_compatible_embeddings_for_recognition(
            model_name=self._embedder.model_name,
        )
        grouped: dict[int, list[list[float]]] = defaultdict(list)
        for record in records:
            grouped[record.employee_id].append(self._normalize(record.embedding_vector))

        return dict(grouped)

    @staticmethod
    def _normalize(embedding: list[float]) -> list[float]:
        if not embedding:
            raise ValueError("Failed to generate embedding vector")
        array = np.asarray(embedding, dtype=np.float32)
        if not np.isfinite(array).all():
            raise ValueError("Failed to generate a valid embedding vector")
        norm = float(np.linalg.norm(array))
        if norm <= 0:
            raise ValueError("Failed to normalize embedding vector")
        return (array / norm).astype(float).tolist()
