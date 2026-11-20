"""Versioned and optionally calibrated FaceNet recognition scoring policy."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.infrastructure.face_ai.face_alignment import (
    ALIGNED_PREPROCESSING_VERSION,
    LEGACY_PREPROCESSING_VERSION,
)


SUPPORTED_AGGREGATIONS = {"centroid", "best", "mean_top_k"}


@dataclass(frozen=True)
class RecognitionPolicy:
    """Operating point and aggregation strategy for one embedding identity."""

    model_name: str
    preprocessing_version: str
    threshold: float
    ambiguity_margin: float
    aggregation: str
    top_k: int
    source: str

    @classmethod
    def from_settings(cls, *, model_name: str) -> "RecognitionPolicy":
        settings = get_settings()
        preprocessing_version = (
            ALIGNED_PREPROCESSING_VERSION
            if settings.FACE_ALIGNMENT_ENABLED
            else LEGACY_PREPROCESSING_VERSION
        )
        configured_path = settings.FACE_RECOGNITION_CALIBRATION_PATH.strip()
        if configured_path:
            return cls._from_calibration(
                Path(configured_path).expanduser().resolve(),
                model_name=model_name,
                preprocessing_version=preprocessing_version,
            )

        aggregation = settings.FACE_RECOGNITION_AGGREGATION.strip().lower()
        _validate_aggregation(aggregation)
        return cls(
            model_name=model_name,
            preprocessing_version=preprocessing_version,
            threshold=float(settings.FACE_RECOGNITION_THRESHOLD),
            ambiguity_margin=float(settings.FACE_RECOGNITION_AMBIGUITY_MARGIN),
            aggregation=aggregation,
            top_k=max(1, int(settings.FACE_RECOGNITION_TOP_K)),
            source="legacy_configuration",
        )

    @classmethod
    def _from_calibration(
        cls,
        path: Path,
        *,
        model_name: str,
        preprocessing_version: str,
    ) -> "RecognitionPolicy":
        if not path.exists():
            raise RuntimeError("Face recognition calibration file was not found.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("Face recognition calibration file is invalid.") from error
        if payload.get("validated") is not True:
            raise RuntimeError("Face recognition calibration has not been marked as validated.")
        if payload.get("model_name") != model_name:
            raise RuntimeError("Face recognition calibration belongs to another embedding model.")
        if payload.get("preprocessing_version") != preprocessing_version:
            raise RuntimeError("Face recognition calibration uses incompatible preprocessing.")

        aggregation = str(payload.get("aggregation", "")).strip().lower()
        _validate_aggregation(aggregation)
        try:
            threshold = float(payload["threshold"])
            ambiguity_margin = float(payload["ambiguity_margin"])
            top_k = int(payload.get("top_k", 3))
            genuine_attempts = int(payload["genuine_attempts"])
            impostor_attempts = int(payload["impostor_attempts"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("Face recognition calibration fields are invalid.") from error
        if not -1.0 < threshold < 1.0 or not 0.0 <= ambiguity_margin < 1.0:
            raise RuntimeError("Face recognition calibration operating point is invalid.")
        if top_k < 1 or genuine_attempts < 1 or impostor_attempts < 1:
            raise RuntimeError("Face recognition calibration dataset metadata is invalid.")
        return cls(
            model_name=model_name,
            preprocessing_version=preprocessing_version,
            threshold=threshold,
            ambiguity_margin=ambiguity_margin,
            aggregation=aggregation,
            top_k=top_k,
            source="calibration_file",
        )


def aggregate_similarity(
    probe: np.ndarray,
    enrollment_embeddings: list[np.ndarray],
    *,
    strategy: str,
    top_k: int,
) -> float:
    """Score one probe against all compatible embeddings for one employee."""
    _validate_aggregation(strategy)
    if not enrollment_embeddings:
        return -1.0
    scores = sorted(
        (float(np.dot(probe, embedding)) for embedding in enrollment_embeddings),
        reverse=True,
    )
    if strategy == "best":
        return scores[0]
    if strategy == "mean_top_k":
        selected = scores[: max(1, min(top_k, len(scores)))]
        return float(np.mean(np.asarray(selected, dtype=np.float32)))

    centroid = np.mean(np.stack(enrollment_embeddings), axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm <= 0.0 or not np.isfinite(centroid).all():
        return -1.0
    return float(np.dot(probe, centroid / norm))


def _validate_aggregation(strategy: str) -> None:
    if strategy not in SUPPORTED_AGGREGATIONS:
        supported = ", ".join(sorted(SUPPORTED_AGGREGATIONS))
        raise RuntimeError(f"Unsupported face recognition aggregation. Use one of: {supported}.")
