"""Enrollment image quality checks based on face geometry and crop clarity."""

from __future__ import annotations

from dataclasses import dataclass
import math

import cv2
import numpy as np

from app.config import get_settings
from app.domain.services.face_processing_service import FaceDetectionResult, FaceLandmarks


@dataclass(frozen=True)
class FaceQualityResult:
    """Quality decision and user-facing rejection reason."""

    accepted: bool
    reason: str | None = None
    blur_score: float | None = None
    face_area_ratio: float | None = None


class FaceEnrollmentQualityValidator:
    """Reject face samples that are unreliable for enrollment."""

    def assess(self, detection: FaceDetectionResult) -> FaceQualityResult:
        crop = np.asarray(detection.face_crop)
        if crop.size == 0:
            return FaceQualityResult(False, "Please use an image where the employee's face is clearly visible.")

        settings = get_settings()
        area_ratio = self._face_area_ratio(detection)
        if area_ratio is not None and area_ratio < settings.FACE_ENROLLMENT_MIN_FACE_AREA_RATIO:
            return FaceQualityResult(
                False,
                "The face is too small. Please use a closer image.",
                face_area_ratio=area_ratio,
            )

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop.astype(np.uint8)
        blur_score = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        if blur_score < settings.FACE_ENROLLMENT_MIN_BLUR_SCORE:
            return FaceQualityResult(
                False,
                "The image is too blurred for reliable enrollment.",
                blur_score=blur_score,
                face_area_ratio=area_ratio,
            )

        pose_error = self._pose_error(detection.face_landmarks)
        if pose_error:
            return FaceQualityResult(
                False,
                pose_error,
                blur_score=blur_score,
                face_area_ratio=area_ratio,
            )

        return FaceQualityResult(
            True,
            blur_score=blur_score,
            face_area_ratio=area_ratio,
        )

    @staticmethod
    def _face_area_ratio(detection: FaceDetectionResult) -> float | None:
        if not detection.face_boxes or not detection.frame_size:
            return None
        _, _, width, height = detection.face_boxes[0]
        frame_width, frame_height = detection.frame_size
        if frame_width <= 0 or frame_height <= 0:
            return None
        return float(max(0, width) * max(0, height)) / float(frame_width * frame_height)

    @staticmethod
    def _pose_error(landmarks: FaceLandmarks | None) -> str | None:
        if not landmarks:
            return None
        try:
            left_eye = np.asarray(landmarks["left_eye"], dtype=np.float32)
            right_eye = np.asarray(landmarks["right_eye"], dtype=np.float32)
            nose = np.asarray(landmarks["nose"], dtype=np.float32)
        except (KeyError, TypeError, ValueError):
            return "The face landmarks are unclear. Please look directly at the camera."

        eye_vector = right_eye - left_eye
        eye_distance = float(np.linalg.norm(eye_vector))
        if eye_distance <= 1e-6:
            return "The face landmarks are unclear. Please look directly at the camera."

        roll_degrees = abs(math.degrees(math.atan2(float(eye_vector[1]), float(eye_vector[0]))))
        eye_midpoint = (left_eye + right_eye) / 2.0
        yaw_proxy = abs(float(nose[0] - eye_midpoint[0])) / eye_distance
        settings = get_settings()
        if roll_degrees > settings.FACE_ENROLLMENT_MAX_ROLL_DEGREES:
            return "The head is tilted too far. Please keep the face upright."
        if yaw_proxy > settings.FACE_ENROLLMENT_MAX_YAW_PROXY:
            return "The head is turned too far. Please use a more frontal image."
        return None
