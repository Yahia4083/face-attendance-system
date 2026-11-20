"""Practical MVP liveness validation for live mobile-camera attendance."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Optional

import cv2
import numpy as np

from app.config import get_settings
from app.domain.services.face_processing_service import FaceDetectorInterface
from app.domain.services.liveness_service import (
    LivenessChallengeType,
    LivenessFrame,
    LivenessServiceInterface,
    LivenessValidationRequest,
    LivenessValidationResult,
)
from app.infrastructure.face_ai.bounding_box_utils import select_primary_face_box


@dataclass(frozen=True)
class _AnalyzedFrame:
    frame: LivenessFrame
    crop_gray: np.ndarray
    eye_mean: float
    asymmetry: float
    sharpness: float
    box: tuple[int, int, int, int] | None = None
    normalized_landmarks: np.ndarray | None = None
    yaw_proxy: float | None = None


@dataclass(frozen=True)
class _FaceCandidate:
    box: tuple[int, int, int, int]
    area: float
    area_ratio: float
    center_distance_ratio: float


class SimpleLivenessService(LivenessServiceInterface):
    """Validate liveness using one-face tracking, motion, and simple challenges.

    This deliberately avoids storing frames or adding a heavy anti-spoofing model.
    It is an MVP challenge-response layer that reduces basic still-photo spoofing,
    not a certified presentation-attack detection system.
    """

    def __init__(
        self,
        detector: FaceDetectorInterface,
        *,
        hardened_mode: bool = False,
    ) -> None:
        self._detector = detector
        self._hardened_mode = hardened_mode

    def validate(self, request: LivenessValidationRequest) -> LivenessValidationResult:
        settings = get_settings()
        challenge_type = self._normalize_challenge(request.challenge_type)
        if challenge_type is None:
            return self._failed(
                request.challenge_type,
                0,
                "Unsupported liveness challenge.",
            )
        if self._hardened_mode and challenge_type == LivenessChallengeType.BLINK:
            return self._failed(
                challenge_type.value,
                0,
                "Blink verification is unavailable in hardened mode. Please use a head-turn challenge.",
            )

        frames = [frame for frame in request.frames if frame.content]
        if not frames:
            return self._failed(challenge_type.value, 0, "No frames submitted.")

        # Limits the submitted frame sequence to the configured maximum.
        frames = frames[: max(1, settings.LIVE_ATTENDANCE_MAX_FRAMES)]
        if len(frames) < settings.LIVE_ATTENDANCE_MIN_FRAMES:
            return self._failed(
                challenge_type.value,
                len(frames),
                f"At least {settings.LIVE_ATTENDANCE_MIN_FRAMES} live frames are required.",
            )

        analyzed: list[_AnalyzedFrame] = []
        for frame in frames:
            # Detects and analyzes one face candidate in the current frame.
            detection = self._detector.detect_face(frame.content, filename=frame.filename)
            face_crop, face_error, face_box, landmarks = self._resolve_primary_face_crop(
                frame,
                detection,
            )
            if face_error:
                return self._failed(challenge_type.value, len(analyzed), face_error)
            if face_crop is None:
                return self._failed(
                    challenge_type.value,
                    len(analyzed),
                    "Face could not be analyzed clearly.",
                )

            analyzed_frame = self._analyze_frame(
                frame,
                face_crop,
                box=face_box,
                landmarks=landmarks,
            )
            if analyzed_frame is None:
                return self._failed(
                    challenge_type.value,
                    len(analyzed),
                    "Frame quality is too low for liveness verification.",
                )
            analyzed.append(analyzed_frame)

        if self._hardened_mode:
            continuity_error = self._same_face_continuity_error(analyzed)
            if continuity_error:
                return self._failed(
                    challenge_type.value,
                    len(analyzed),
                    continuity_error,
                )

        motion_score = self._motion_score(analyzed)
        # Calculates the motion score across analyzed face frames.
        if motion_score < settings.LIVE_ATTENDANCE_MIN_MOTION_SCORE:
            return self._failed(
                challenge_type.value,
                len(analyzed),
                "Liveness verification failed because the face remained too static.",
                confidence=min(0.49, motion_score / max(settings.LIVE_ATTENDANCE_MIN_MOTION_SCORE, 0.01)),
            )

        challenge_confidence = self._challenge_confidence(challenge_type, analyzed)
        # Calculates the final liveness confidence score.
        confidence = min(1.0, max(0.0, (challenge_confidence * 0.75) + min(0.25, motion_score / 80)))
        if confidence < settings.LIVE_ATTENDANCE_MIN_CHALLENGE_CONFIDENCE:
            return self._failed(
                challenge_type.value,
                len(analyzed),
                self._challenge_failure_message(challenge_type),
                confidence=confidence,
            )

        selected = max(analyzed, key=lambda item: item.sharpness).frame
        # Selects the sharpest approved frame for face recognition.
        return LivenessValidationResult(
            passed=True,
            challenge_type=challenge_type.value,
            confidence=round(confidence, 3),
            frames_analyzed=len(analyzed),
            selected_frame=selected,
        )

    def _resolve_primary_face_crop(
        self,
        frame: LivenessFrame,
        detection,
    ) -> tuple[
        Optional[np.ndarray],
        Optional[str],
        tuple[int, int, int, int] | None,
        dict[str, tuple[float, float]] | None,
    ]:
        if detection.error_message:
            return None, detection.error_message, None, None
        if detection.face_count == 0:
            return None, "No face detected. Please keep one face visible.", None, None

        if detection.face_count == 1:
            boxes = detection.face_boxes or []
            box = boxes[0] if boxes else None
            if detection.face_crop is not None:
                return detection.face_crop, None, box, detection.face_landmarks
            if boxes:
                return (
                    self._crop_from_frame_content(frame.content, boxes[0]),
                    None,
                    boxes[0],
                    detection.face_landmarks,
                )
            return None, "Face could not be analyzed clearly.", None, None

        boxes = detection.face_boxes or []
        if not boxes:
            return (
                None,
                "Multiple faces detected. Keep only one person close to the camera.",
                None,
                None,
            )

        # Selects the primary face box when multiple boxes are detected.
        frame_size = detection.frame_size or self._frame_size_from_content(frame.content)
        primary_box = self._select_primary_face_box(
            boxes,
            frame_size=frame_size,
        )
        if primary_box is None:
            return (
                None,
                "Multiple foreground faces detected. Keep only one person close to the camera.",
                None,
                None,
            )

        crop = self._crop_from_frame_content(frame.content, primary_box)
        if crop is None:
            return None, "Face could not be analyzed clearly.", None, None
        landmarks = None
        if detection.face_landmarks_list:
            try:
                landmarks = detection.face_landmarks_list[boxes.index(primary_box)]
            except (ValueError, IndexError):
                landmarks = None
        return crop, None, primary_box, landmarks

    @staticmethod
    def _frame_size_from_content(content: bytes) -> Optional[tuple[int, int]]:
        image = SimpleLivenessService._decode_frame(content)
        if image is None:
            return None
        return int(image.shape[1]), int(image.shape[0])

    @staticmethod
    def _decode_frame(content: bytes) -> Optional[np.ndarray]:
        image_array = np.frombuffer(content, dtype=np.uint8)
        return cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    @staticmethod
    def _crop_from_frame_content(content: bytes, box: tuple[int, int, int, int]) -> Optional[np.ndarray]:
        image = SimpleLivenessService._decode_frame(content)
        if image is None:
            return None
        return SimpleLivenessService._crop_box(image, box)

    @staticmethod
    def _crop_box(image: np.ndarray, box: tuple[int, int, int, int]) -> Optional[np.ndarray]:
        x, y, width, height = box
        margin_x = int(width * 0.18)
        margin_y = int(height * 0.18)
        x1 = max(0, x - margin_x)
        y1 = max(0, y - margin_y)
        x2 = min(image.shape[1], x + width + margin_x)
        y2 = min(image.shape[0], y + height + margin_y)
        if x2 <= x1 or y2 <= y1:
            return None
        return image[y1:y2, x1:x2]

    @staticmethod
    def _select_primary_face_box(
        boxes: list[tuple[int, int, int, int]],
        *,
        frame_size: Optional[tuple[int, int]],
    ) -> Optional[tuple[int, int, int, int]]:
        settings = get_settings()
        return select_primary_face_box(
            boxes,
            frame_size=frame_size,
            min_area_ratio=settings.LIVE_FACE_MIN_AREA_RATIO,
            max_center_distance_ratio=settings.LIVE_FACE_MAX_CENTER_DISTANCE_RATIO,
            dominance_ratio=settings.LIVE_FACE_DOMINANCE_RATIO,
        )

    @staticmethod
    def _face_candidates(
        boxes: list[tuple[int, int, int, int]],
        *,
        frame_size: Optional[tuple[int, int]],
    ) -> list[_FaceCandidate]:
        if not frame_size:
            return [
                _FaceCandidate(
                    box=box,
                    area=float(max(0, box[2]) * max(0, box[3])),
                    area_ratio=1.0,
                    center_distance_ratio=0.0,
                )
                for box in boxes
            ]

        frame_width, frame_height = frame_size
        frame_area = max(1.0, float(frame_width * frame_height))
        half_diagonal = max(1.0, math.hypot(frame_width, frame_height) / 2.0)
        frame_center_x = frame_width / 2.0
        frame_center_y = frame_height / 2.0

        candidates: list[_FaceCandidate] = []
        for box in boxes:
            x, y, width, height = box
            area = float(max(0, width) * max(0, height))
            center_x = x + (width / 2.0)
            center_y = y + (height / 2.0)
            distance = math.hypot(center_x - frame_center_x, center_y - frame_center_y)
            candidates.append(
                _FaceCandidate(
                    box=box,
                    area=area,
                    area_ratio=area / frame_area,
                    center_distance_ratio=distance / half_diagonal,
                )
            )
        return candidates

    @staticmethod
    def _normalize_challenge(value: str) -> Optional[LivenessChallengeType]:
        normalized = (value or "").strip().upper()
        try:
            return LivenessChallengeType(normalized)
        except ValueError:
            return None

    @staticmethod
    def _failed(
        challenge_type: str,
        frames_analyzed: int,
        reason: str,
        *,
        confidence: float = 0.0,
    ) -> LivenessValidationResult:
        return LivenessValidationResult(
            passed=False,
            challenge_type=challenge_type,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            frames_analyzed=frames_analyzed,
            selected_frame=None,
            failure_reason=reason,
        )

    @staticmethod
    def _analyze_frame(
        frame: LivenessFrame,
        face_crop,
        *,
        box: tuple[int, int, int, int] | None = None,
        landmarks: dict[str, tuple[float, float]] | None = None,
    ) -> Optional[_AnalyzedFrame]:
        crop = np.asarray(face_crop)
        if crop.size == 0:
            return None

        if len(crop.shape) == 3:
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = crop.astype(np.uint8)

        resized = cv2.resize(gray, (96, 96), interpolation=cv2.INTER_AREA)
        if float(np.std(resized)) < 2.0:
            return None

        # Extracts eye, asymmetry, and sharpness signals from the face crop.
        eye_band = resized[30:52, :]
        left = resized[:, :48]
        right = resized[:, 48:]
        mean_value = float(np.mean(resized)) + 1.0
        asymmetry = float(np.mean(left) - np.mean(right)) / mean_value
        sharpness = float(cv2.Laplacian(resized, cv2.CV_64F).var())

        normalized_landmarks, yaw_proxy = SimpleLivenessService._landmark_signals(
            landmarks,
            box,
        )
        return _AnalyzedFrame(
            frame=frame,
            crop_gray=resized.astype(np.float32),
            eye_mean=float(np.mean(eye_band)),
            asymmetry=asymmetry,
            sharpness=sharpness,
            box=box,
            normalized_landmarks=normalized_landmarks,
            yaw_proxy=yaw_proxy,
        )

    @staticmethod
    def _landmark_signals(
        landmarks: dict[str, tuple[float, float]] | None,
        box: tuple[int, int, int, int] | None,
    ) -> tuple[np.ndarray | None, float | None]:
        if not landmarks or not box:
            return None, None
        names = ("left_eye", "right_eye", "nose", "mouth_left", "mouth_right")
        try:
            points = np.asarray([landmarks[name] for name in names], dtype=np.float32)
        except (KeyError, TypeError, ValueError):
            return None, None
        x, y, width, height = box
        if width <= 0 or height <= 0 or points.shape != (5, 2):
            return None, None
        normalized = points.copy()
        normalized[:, 0] = (normalized[:, 0] - x) / width
        normalized[:, 1] = (normalized[:, 1] - y) / height
        eye_distance = float(np.linalg.norm(points[1] - points[0]))
        if eye_distance <= 1e-6:
            return None, None
        eye_midpoint_x = float((points[0, 0] + points[1, 0]) / 2.0)
        yaw_proxy = float(points[2, 0] - eye_midpoint_x) / eye_distance
        return normalized, yaw_proxy

    def _same_face_continuity_error(self, frames: list[_AnalyzedFrame]) -> str | None:
        settings = get_settings()
        if any(item.box is None or item.normalized_landmarks is None for item in frames):
            return "Facial landmarks could not be tracked throughout the live challenge."

        for previous, current in zip(frames, frames[1:]):
            previous_box = previous.box
            current_box = current.box
            assert previous_box is not None and current_box is not None
            previous_points = previous.normalized_landmarks
            current_points = current.normalized_landmarks
            assert previous_points is not None and current_points is not None

            landmark_rms = float(np.sqrt(np.mean((current_points - previous_points) ** 2)))
            if landmark_rms > settings.LIVE_LIVENESS_MAX_LANDMARK_RMS:
                return "The same face could not be tracked throughout the live challenge."

            previous_center = np.asarray(
                [previous_box[0] + previous_box[2] / 2.0, previous_box[1] + previous_box[3] / 2.0]
            )
            current_center = np.asarray(
                [current_box[0] + current_box[2] / 2.0, current_box[1] + current_box[3] / 2.0]
            )
            center_jump = float(np.linalg.norm(current_center - previous_center)) / max(
                previous_box[2],
                previous_box[3],
                1,
            )
            if center_jump > settings.LIVE_LIVENESS_MAX_CENTER_JUMP_RATIO:
                return "The primary face moved out of tracking range during the challenge."
        return None

    @staticmethod
    def _motion_score(frames: list[_AnalyzedFrame]) -> float:
        if len(frames) < 2:
            return 0.0
        diffs = [
            float(np.mean(np.abs(right.crop_gray - left.crop_gray)))
            for left, right in zip(frames, frames[1:])
        ]
        return max(diffs) if diffs else 0.0

    def _challenge_confidence(
        self,
        challenge_type: LivenessChallengeType,
        frames: list[_AnalyzedFrame],
    ) -> float:
        settings = get_settings()
        if self._hardened_mode:
            yaws = [frame.yaw_proxy for frame in frames]
            if any(value is None for value in yaws):
                return 0.0
            values = [float(value) for value in yaws if value is not None]
            baseline = values[0]
            if abs(baseline) > settings.LIVE_LIVENESS_FRONTAL_YAW_LIMIT:
                return 0.0
            direction = 1.0 if challenge_type == LivenessChallengeType.TURN_HEAD_LEFT else -1.0
            direction *= settings.LIVE_LIVENESS_TURN_DIRECTION_MULTIPLIER
            directional_progress = max(direction * (value - baseline) for value in values[1:])
            progressive_steps = sum(
                1
                for left, right in zip(values, values[1:])
                if direction * (right - left) > 0.005
            )
            required_steps = max(1, (len(values) - 1) // 3)
            if progressive_steps < required_steps:
                return 0.0
            return min(
                1.0,
                max(0.0, directional_progress)
                / max(settings.LIVE_LIVENESS_TURN_TARGET_DELTA, 0.001),
            )

        if challenge_type == LivenessChallengeType.BLINK:
            values = [frame.eye_mean for frame in frames]
            signal = max(values) - min(values)
            return min(1.0, signal / max(settings.LIVE_ATTENDANCE_BLINK_CHANGE_THRESHOLD, 0.01))

        # Calculates head-turn challenge confidence from asymmetry changes.
        values = [frame.asymmetry for frame in frames]
        first = values[0]
        last = values[-1]
        span = max(values) - min(values)
        directional_change = (
            first - last
            if challenge_type == LivenessChallengeType.TURN_HEAD_LEFT
            else last - first
        )
        signal = max(span * 0.75, directional_change)
        return min(1.0, max(0.0, signal / max(settings.LIVE_ATTENDANCE_TURN_CHANGE_THRESHOLD, 0.001)))

    @staticmethod
    def _challenge_failure_message(challenge_type: LivenessChallengeType) -> str:
        if challenge_type == LivenessChallengeType.BLINK:
            return "Liveness verification failed. Please blink when prompted and keep only one face visible."
        if challenge_type == LivenessChallengeType.TURN_HEAD_LEFT:
            return "Liveness verification failed. Please turn your head slightly left when prompted."
        return "Liveness verification failed. Please turn your head slightly right when prompted."
