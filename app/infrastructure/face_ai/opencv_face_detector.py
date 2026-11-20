"""OpenCV-based face detector adapter."""

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
from app.infrastructure.face_ai.bounding_box_utils import (
    FaceBox,
    suppress_overlapping_boxes,
)
from app.infrastructure.face_ai.face_debug_service import FaceDetectionDebugService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _DetectionCandidate:
    image: np.ndarray
    raw_boxes: list[FaceBox]
    filtered_boxes: list[FaceBox]


class OpenCVFaceDetector(FaceDetectorInterface):
    """Face detector using OpenCV Haar Cascade with duplicate suppression."""

    def __init__(self) -> None:
        settings = get_settings()
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._classifier = cv2.CascadeClassifier(cascade_path)
        self._scale_factor = settings.FACE_DETECTION_SCALE_FACTOR
        self._min_neighbors = settings.FACE_DETECTION_MIN_NEIGHBORS
        self._iou_threshold = settings.FACE_DETECTION_IOU_THRESHOLD
        self._debug_service = FaceDetectionDebugService()

        if self._classifier.empty():
            raise RuntimeError("Failed to initialize OpenCV face detector")

    def detect_face(
        self,
        image_bytes: bytes,
        *,
        employee_id: Optional[int] = None,
        filename: Optional[str] = None,
    ) -> FaceDetectionResult:
        image = self._decode_image(image_bytes)
        if image is None:
            return FaceDetectionResult(face_count=0, error_message="Invalid image file")

        candidate = self._detect_on_image(image)
        if len(candidate.filtered_boxes) == 0:
            candidate = self._try_rotated_images(image, fallback=candidate)

        self._debug_service.save_detection_debug_images(
            employee_id=employee_id,
            filename=filename,
            image=candidate.image,
            raw_boxes=candidate.raw_boxes,
            filtered_boxes=candidate.filtered_boxes,
        )
        self._log_detection_details(filename, candidate.raw_boxes, candidate.filtered_boxes)

        face_count = len(candidate.filtered_boxes)
        frame_size = (int(candidate.image.shape[1]), int(candidate.image.shape[0]))
        if face_count != 1:
            return FaceDetectionResult(
                face_count=face_count,
                face_boxes=list(candidate.filtered_boxes),
                frame_size=frame_size,
            )

        crop = self._crop_face(candidate.image, candidate.filtered_boxes[0])
        if crop is None or getattr(crop, "size", 0) == 0:
            return FaceDetectionResult(face_count=0, error_message="Invalid image file")

        return FaceDetectionResult(
            face_count=1,
            face_crop=crop,
            face_boxes=list(candidate.filtered_boxes),
            frame_size=frame_size,
        )

    def _detect_on_image(self, image: np.ndarray) -> _DetectionCandidate:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        equalized = cv2.equalizeHist(gray)
        min_face_size = self._minimum_face_size(image)

        raw_faces = self._classifier.detectMultiScale(
            equalized,
            scaleFactor=self._scale_factor,
            minNeighbors=self._min_neighbors,
            minSize=(min_face_size, min_face_size),
            flags=cv2.CASCADE_SCALE_IMAGE,
        )

        raw_boxes = [self._normalize_box(face) for face in raw_faces]
        valid_boxes = [box for box in raw_boxes if self._is_reasonable_face_box(box, image)]
        filtered_boxes = suppress_overlapping_boxes(
            valid_boxes,
            iou_threshold=self._iou_threshold,
        )

        return _DetectionCandidate(
            image=image,
            raw_boxes=raw_boxes,
            filtered_boxes=filtered_boxes,
        )

    def _try_rotated_images(
        self,
        image: np.ndarray,
        *,
        fallback: _DetectionCandidate,
    ) -> _DetectionCandidate:
        for rotated in (
            cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
            cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE),
            cv2.rotate(image, cv2.ROTATE_180),
        ):
            candidate = self._detect_on_image(rotated)
            if len(candidate.filtered_boxes) > 0:
                return candidate
        return fallback

    def _minimum_face_size(self, image: np.ndarray) -> int:
        height, width = image.shape[:2]
        return max(48, int(min(height, width) * 0.08))

    def _is_reasonable_face_box(self, box: FaceBox, image: np.ndarray) -> bool:
        _, _, width, height = box
        image_height, image_width = image.shape[:2]
        min_size = self._minimum_face_size(image)
        max_size = int(max(image_width, image_height) * 0.95)
        aspect_ratio = width / height if height else 0

        return (
            width >= min_size
            and height >= min_size
            and width <= max_size
            and height <= max_size
            and 0.65 <= aspect_ratio <= 1.55
        )

    @staticmethod
    def _crop_face(image: np.ndarray, box: FaceBox) -> Optional[np.ndarray]:
        x, y, width, height = box
        margin_x = int(width * 0.2)
        margin_y = int(height * 0.2)

        x1 = max(0, x - margin_x)
        y1 = max(0, y - margin_y)
        x2 = min(image.shape[1], x + width + margin_x)
        y2 = min(image.shape[0], y + height + margin_y)

        if x2 <= x1 or y2 <= y1:
            return None
        return image[y1:y2, x1:x2]

    @staticmethod
    def _decode_image(image_bytes: bytes) -> Optional[np.ndarray]:
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    @staticmethod
    def _normalize_box(box) -> FaceBox:
        x, y, width, height = box
        return int(x), int(y), int(width), int(height)

    @staticmethod
    def _log_detection_details(
        filename: Optional[str],
        raw_boxes: list[FaceBox],
        filtered_boxes: list[FaceBox],
    ) -> None:
        logger.info(
            "Face detection result filename=%s raw_count=%s raw_boxes=%s "
            "filtered_count=%s filtered_boxes=%s",
            filename or "uploaded_image",
            len(raw_boxes),
            raw_boxes,
            len(filtered_boxes),
            filtered_boxes,
        )
