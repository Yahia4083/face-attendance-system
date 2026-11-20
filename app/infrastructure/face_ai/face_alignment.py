"""Deterministic five-landmark alignment for FaceNet preprocessing."""

from __future__ import annotations

import cv2
import numpy as np

from app.domain.services.face_processing_service import FaceLandmarks


ALIGNED_FACE_SIZE = 160
ALIGNED_PREPROCESSING_VERSION = "aligned-v2"
LEGACY_PREPROCESSING_VERSION = "legacy-v1"

# The target keeps forehead, cheeks, mouth, and jaw while avoiding broad hair/background margins.
_TARGET_LANDMARKS = np.asarray(
    [
        (52.0, 58.0),
        (108.0, 58.0),
        (80.0, 86.0),
        (58.0, 116.0),
        (102.0, 116.0),
    ],
    dtype=np.float32,
)
_LANDMARK_ORDER = ("left_eye", "right_eye", "nose", "mouth_left", "mouth_right")


def validate_preprocessing_model_identity(*, alignment_enabled: bool, model_name: str) -> None:
    """Prevent embeddings from incompatible crop pipelines sharing one model identity."""
    aligned_identity = model_name.strip().lower().endswith("-aligned-v2")
    if alignment_enabled and not aligned_identity:
        raise RuntimeError(
            "FACE_ALIGNMENT_ENABLED requires a distinct FaceNet model identity ending in "
            "'-aligned-v2'. Existing legacy-v1 embeddings must be re-enrolled explicitly."
        )
    if not alignment_enabled and aligned_identity:
        raise RuntimeError(
            "A FaceNet model identity ending in '-aligned-v2' requires FACE_ALIGNMENT_ENABLED=true."
        )


def align_face(
    image_bgr: np.ndarray,
    landmarks: FaceLandmarks,
    *,
    output_size: int = ALIGNED_FACE_SIZE,
) -> np.ndarray:
    """Normalize face rotation, scale, and position from five MTCNN landmarks."""
    source = _landmark_array(landmarks)
    target = _TARGET_LANDMARKS * (float(output_size) / ALIGNED_FACE_SIZE)
    transform = _similarity_transform(source, target)
    return cv2.warpAffine(
        image_bgr,
        transform,
        (output_size, output_size),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )


def _landmark_array(landmarks: FaceLandmarks) -> np.ndarray:
    try:
        points = np.asarray([landmarks[name] for name in _LANDMARK_ORDER], dtype=np.float32)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Five facial landmarks are required for aligned preprocessing.") from error
    if points.shape != (5, 2) or not np.isfinite(points).all():
        raise ValueError("Facial landmarks are invalid for aligned preprocessing.")
    return points


def _similarity_transform(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Estimate a deterministic least-squares similarity transform."""
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    source_centered = source - source_mean
    target_centered = target - target_mean

    variance = float(np.sum(source_centered**2))
    if variance <= 1e-8:
        raise ValueError("Facial landmarks do not define a usable face geometry.")

    covariance = source_centered.T @ target_centered
    left, singular_values, right_t = np.linalg.svd(covariance)
    rotation = right_t.T @ left.T
    if np.linalg.det(rotation) < 0:
        right_t[-1, :] *= -1
        rotation = right_t.T @ left.T

    scale = float(np.sum(singular_values) / variance)
    linear = scale * rotation
    translation = target_mean - (linear @ source_mean)
    return np.hstack([linear, translation.reshape(2, 1)]).astype(np.float32)
