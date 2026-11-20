"""Development-only face detection debug image storage."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import cv2

from app.config import get_settings
from app.infrastructure.face_ai.bounding_box_utils import FaceBox

logger = logging.getLogger(__name__)

DebugBox = FaceBox | dict[str, object]


class FaceDetectionDebugService:
    """Save detector debug images without affecting enrollment success."""

    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = settings.FACE_DEBUG_MODE
        self._storage_root = Path(settings.STORAGE_PATH).expanduser().resolve()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def save_detection_debug_images(
        self,
        *,
        employee_id: int | None,
        filename: str | None,
        image,
        raw_boxes: list[DebugBox],
        filtered_boxes: list[DebugBox],
        detector_label: str = "detector",
    ) -> None:
        if not self._enabled:
            return

        safe_employee_id = employee_id if employee_id is not None else 0
        safe_filename = self._safe_filename(filename or "uploaded_image")
        safe_detector_label = self._safe_filename(detector_label)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        debug_dir = self._storage_root / "debug" / "face_detection" / str(safe_employee_id)

        try:
            debug_dir.mkdir(parents=True, exist_ok=True)
            raw_image = self._draw_boxes(
                image.copy(),
                raw_boxes,
                (0, 165, 255),
                detector_label=detector_label,
            )
            filtered_image = self._draw_boxes(
                image.copy(),
                filtered_boxes,
                (0, 255, 0),
                detector_label=detector_label,
            )
            cv2.imwrite(
                str(debug_dir / f"{timestamp}_{safe_filename}_{safe_detector_label}_raw.jpg"),
                raw_image,
            )
            cv2.imwrite(
                str(
                    debug_dir
                    / f"{timestamp}_{safe_filename}_{safe_detector_label}_filtered.jpg"
                ),
                filtered_image,
            )
        except Exception as error:
            logger.warning("Failed to save face detection debug images: %s", error)

    @staticmethod
    def _draw_boxes(
        image,
        boxes: list[DebugBox],
        color: tuple[int, int, int],
        *,
        detector_label: str,
    ):
        for item in boxes:
            x, y, w, h, confidence, accepted = FaceDetectionDebugService._coerce_box(item)
            cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)
            label = detector_label
            if confidence is not None:
                label = f"{label} {confidence:.3f}"
            if accepted is not None:
                label = f"{label} {'pass' if accepted else 'fail'}"
            cv2.putText(
                image,
                label,
                (x, max(18, y - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )
        return image

    @staticmethod
    def _coerce_box(item: DebugBox) -> tuple[int, int, int, int, float | None, bool | None]:
        if isinstance(item, dict):
            box = item.get("box", (0, 0, 0, 0))
            confidence = item.get("confidence")
            accepted = item.get("accepted")
            x, y, w, h = box  # type: ignore[misc]
            return (
                int(x),
                int(y),
                int(w),
                int(h),
                float(confidence) if confidence is not None else None,
                bool(accepted) if accepted is not None else None,
            )

        x, y, w, h = item
        return int(x), int(y), int(w), int(h), None, None

    @staticmethod
    def _safe_filename(filename: str) -> str:
        stem = Path(filename).stem or "uploaded_image"
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)[:80]
