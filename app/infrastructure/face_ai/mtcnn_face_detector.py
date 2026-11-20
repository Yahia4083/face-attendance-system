"""MTCNN-based face detector adapter for enrollment."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from app.config import get_settings
from app.domain.services.face_processing_service import (
    FaceDetectionResult,
    FaceDetectorInterface,
)
from app.infrastructure.face_ai.bounding_box_utils import FaceBox
from app.infrastructure.face_ai.face_alignment import (
    ALIGNED_PREPROCESSING_VERSION,
    LEGACY_PREPROCESSING_VERSION,
    align_face,
)
from app.infrastructure.face_ai.face_debug_service import FaceDetectionDebugService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _MTCNNDetectionCandidate:
    image_bgr: np.ndarray
    raw_detections: list[dict[str, object]]
    filtered_detections: list[dict[str, object]]


class MTCNNFaceDetector(FaceDetectorInterface):
    """Face detector using mtcnn-opencv and OpenCV DNN ONNX models."""

    DETECTOR_LABEL = "MTCNN"

    def __init__(self, *, alignment_enabled: bool | None = None) -> None:
        settings = get_settings()
        self._confidence_threshold = settings.FACE_DETECTION_CONFIDENCE_THRESHOLD
        self._min_face_size = settings.FACE_MTCNN_MIN_FACE_SIZE
        self._scale_factor = settings.FACE_MTCNN_SCALE_FACTOR
        self._alignment_enabled = (
            settings.FACE_ALIGNMENT_ENABLED
            if alignment_enabled is None
            else alignment_enabled
        )
        self._debug_service = FaceDetectionDebugService()

        try:
            from mtcnn_cv2 import MTCNN
        except ModuleNotFoundError as error:
            raise RuntimeError(
                "MTCNN detector backend is configured but mtcnn-opencv cannot be imported. "
                "Install mtcnn-opencv==1.0.2 and ensure the Python 3.14 imghdr compatibility "
                "shim exists at the project root."
            ) from error

        try:
            self._detector = MTCNN(
                min_face_size=self._min_face_size,
                scale_factor=self._scale_factor,
            )
        except Exception as error:
            raise RuntimeError(
                "MTCNN detector backend failed to initialize. Verify mtcnn-opencv model files "
                "are installed and readable in the virtual environment."
            ) from error

    def detect_face(
        self,
        image_bytes: bytes,
        *,
        employee_id: Optional[int] = None,
        filename: Optional[str] = None,
    ) -> FaceDetectionResult:
        image_bgr = self._decode_image(image_bytes)
        if image_bgr is None:
            return FaceDetectionResult(face_count=0, error_message="Invalid image file")

        candidate = self._detect_on_image(image_bgr)
        if len(candidate.filtered_detections) == 0:
            candidate = self._try_rotated_images(image_bgr, fallback=candidate)

        self._debug_service.save_detection_debug_images(
            employee_id=employee_id,
            filename=filename,
            image=candidate.image_bgr,
            raw_boxes=candidate.raw_detections,
            filtered_boxes=candidate.filtered_detections,
            detector_label="mtcnn",
        )
        self._log_detection_details(filename, candidate.raw_detections, candidate.filtered_detections)

        face_count = len(candidate.filtered_detections)
        face_boxes = [self._coerce_box(detection["box"]) for detection in candidate.filtered_detections]
        landmark_sets = [
            self._coerce_landmarks(detection.get("keypoints"))
            for detection in candidate.filtered_detections
        ]
        frame_size = (int(candidate.image_bgr.shape[1]), int(candidate.image_bgr.shape[0]))
        if face_count != 1:
            return FaceDetectionResult(
                face_count=face_count,
                face_boxes=face_boxes,
                face_landmarks_list=landmark_sets,
                frame_size=frame_size,
                preprocessing_version=self._preprocessing_version,
            )

        box = face_boxes[0]
        landmarks = landmark_sets[0]
        if self._alignment_enabled:
            if landmarks is None:
                return FaceDetectionResult(
                    face_count=1,
                    face_boxes=face_boxes,
                    frame_size=frame_size,
                    error_message="Face landmarks could not be aligned reliably.",
                    preprocessing_version=self._preprocessing_version,
                )
            try:
                crop = align_face(candidate.image_bgr, landmarks)
            except ValueError:
                return FaceDetectionResult(
                    face_count=1,
                    face_boxes=face_boxes,
                    face_landmarks=landmarks,
                    frame_size=frame_size,
                    error_message="Face landmarks could not be aligned reliably.",
                    preprocessing_version=self._preprocessing_version,
                )
        else:
            crop = self._crop_face(candidate.image_bgr, box)
        if crop is None or getattr(crop, "size", 0) == 0:
            return FaceDetectionResult(face_count=0, error_message="Invalid image file")

        return FaceDetectionResult(
            face_count=1,
            face_crop=crop,
            face_boxes=face_boxes,
            face_landmarks=landmarks,
            face_landmarks_list=landmark_sets,
            frame_size=frame_size,
            preprocessing_version=self._preprocessing_version,
        )

    @property
    def _preprocessing_version(self) -> str:
        return (
            ALIGNED_PREPROCESSING_VERSION
            if self._alignment_enabled
            else LEGACY_PREPROCESSING_VERSION
        )

    def _detect_on_image(self, image_bgr: np.ndarray) -> _MTCNNDetectionCandidate:
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

        try:
            detections = self._detector.detect_faces(image_rgb)
        except Exception as error:
            logger.exception("MTCNN detection failed")
            raise RuntimeError("Face detector failed to process the uploaded image") from error

        raw_detections = [self._normalize_detection(detection) for detection in detections]
        filtered_detections = [
            {**detection, "accepted": True}
            for detection in raw_detections
            if self._is_accepted_detection(detection, image_bgr)
        ]
        raw_detections = [
            {
                **detection,
                "accepted": self._is_accepted_detection(detection, image_bgr),
            }
            for detection in raw_detections
        ]

        return _MTCNNDetectionCandidate(
            image_bgr=image_bgr,
            raw_detections=raw_detections,
            filtered_detections=filtered_detections,
        )

    def _try_rotated_images(
        self,
        image_bgr: np.ndarray,
        *,
        fallback: _MTCNNDetectionCandidate,
    ) -> _MTCNNDetectionCandidate:
        for rotated in (
            cv2.rotate(image_bgr, cv2.ROTATE_90_CLOCKWISE),
            cv2.rotate(image_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE),
            cv2.rotate(image_bgr, cv2.ROTATE_180),
        ):
            candidate = self._detect_on_image(rotated)
            if len(candidate.filtered_detections) > 0:
                return candidate
        return fallback

    def _is_accepted_detection(
        self,
        detection: dict[str, object],
        image_bgr: np.ndarray,
    ) -> bool:
        confidence = float(detection["confidence"])
        box = self._coerce_box(detection["box"])
        return confidence >= self._confidence_threshold and self._is_reasonable_face_box(
            box,
            image_bgr,
        )

    def _is_reasonable_face_box(self, box: FaceBox, image_bgr: np.ndarray) -> bool:
        _, _, width, height = box
        image_height, image_width = image_bgr.shape[:2]
        min_size = max(24, self._min_face_size)
        max_size = int(max(image_width, image_height) * 0.98)
        aspect_ratio = width / height if height else 0

        return (
            width >= min_size
            and height >= min_size
            and width <= max_size
            and height <= max_size
            and 0.55 <= aspect_ratio <= 1.8
        )

    @staticmethod
    def _crop_face(image_bgr: np.ndarray, box: FaceBox) -> Optional[np.ndarray]:
        x, y, width, height = box
        margin_x = int(width * 0.18)
        margin_y = int(height * 0.18)

        x1 = max(0, x - margin_x)
        y1 = max(0, y - margin_y)
        x2 = min(image_bgr.shape[1], x + width + margin_x)
        y2 = min(image_bgr.shape[0], y + height + margin_y)

        if x2 <= x1 or y2 <= y1:
            return None
        return image_bgr[y1:y2, x1:x2]

    @staticmethod
    def _decode_image(image_bytes: bytes) -> Optional[np.ndarray]:
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    @staticmethod
    def _normalize_detection(detection: dict[str, object]) -> dict[str, object]:
        return {
            "box": MTCNNFaceDetector._coerce_box(detection["box"]),
            "confidence": float(detection.get("confidence", 0.0)),
            "keypoints": MTCNNFaceDetector._coerce_landmarks(detection.get("keypoints")),
            "accepted": False,
        }

    @staticmethod
    def _coerce_landmarks(value: object):
        if not isinstance(value, dict):
            return None
        required = ("left_eye", "right_eye", "nose", "mouth_left", "mouth_right")
        try:
            return {
                name: (float(value[name][0]), float(value[name][1]))  # type: ignore[index]
                for name in required
            }
        except (KeyError, TypeError, ValueError, IndexError):
            return None

    @staticmethod
    def _coerce_box(box: object) -> FaceBox:
        x, y, width, height = box  # type: ignore[misc]
        return int(x), int(y), int(width), int(height)

    @staticmethod
    def _log_detection_details(
        filename: Optional[str],
        raw_detections: list[dict[str, object]],
        filtered_detections: list[dict[str, object]],
    ) -> None:
        def safe_metadata(items: list[dict[str, object]]) -> list[dict[str, object]]:
            return [
                {
                    "box": item.get("box"),
                    "confidence": item.get("confidence"),
                    "accepted": item.get("accepted"),
                }
                for item in items
            ]

        logger.info(
            "MTCNN face detection filename=%s raw_count=%s raw=%s "
            "filtered_count=%s filtered=%s",
            filename or "uploaded_image",
            len(raw_detections),
            safe_metadata(raw_detections),
            len(filtered_detections),
            safe_metadata(filtered_detections),
        )
