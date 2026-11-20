"""Calibrated ONNX RGB presentation-attack detection."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import time
from typing import Any

import cv2
import numpy as np

from app.config import get_settings, resolve_project_path
from app.domain.services.face_anti_spoofing_service import (
    AntiSpoofFailureCategory,
    AntiSpoofResult,
    FaceAntiSpoofingServiceInterface,
)
from app.domain.services.face_processing_service import FaceDetectorInterface
from app.domain.services.liveness_service import LivenessFrame
from app.infrastructure.face_ai.bounding_box_utils import FaceBox, select_primary_face_box


_MODEL_MEAN_RGB = np.asarray([151.2405, 119.5950, 107.8395], dtype=np.float32)
_MODEL_SCALE_RGB = np.asarray([63.0105, 56.4570, 55.0035], dtype=np.float32)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AntiSpoofCalibration:
    """Validated local operating point for one exact model and camera dataset."""

    threshold: float
    model_name: str
    model_sha384: str
    real_attempts: int
    spoof_attempts: int
    aggregation: str

    @classmethod
    def load(cls, path: Path, *, model_name: str, model_sha384: str) -> "AntiSpoofCalibration":
        if not path.exists():
            raise RuntimeError(
                "Passive anti-spoofing calibration is missing. Run the local biometric "
                "security evaluator before enabling live attendance."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError("Passive anti-spoofing calibration file is invalid.") from error

        if payload.get("validated") is not True:
            raise RuntimeError("Passive anti-spoofing calibration has not been marked as validated.")
        if payload.get("model_name") != model_name:
            raise RuntimeError("Passive anti-spoofing calibration belongs to another model.")
        if str(payload.get("model_sha384", "")).lower() != model_sha384.lower():
            raise RuntimeError("Passive anti-spoofing calibration does not match the model file.")

        try:
            threshold = float(payload["threshold"])
            real_attempts = int(payload["real_attempts"])
            spoof_attempts = int(payload["spoof_attempts"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("Passive anti-spoofing calibration fields are invalid.") from error
        if not 0.0 < threshold < 1.0:
            raise RuntimeError("Passive anti-spoofing calibration threshold must be between 0 and 1.")
        if real_attempts < 1 or spoof_attempts < 1:
            raise RuntimeError("Calibration requires both real and spoof camera attempts.")
        if payload.get("aggregation") != "median":
            raise RuntimeError("Passive anti-spoofing calibration aggregation is unsupported.")

        return cls(
            threshold=threshold,
            model_name=model_name,
            model_sha384=model_sha384,
            real_attempts=real_attempts,
            spoof_attempts=spoof_attempts,
            aggregation="median",
        )


@dataclass(frozen=True)
class AntiSpoofSequenceScore:
    """Internal raw sequence score used by the local calibration tool."""

    real_score: float | None
    frames_analyzed: int
    latency_ms: float
    failure_reason: str | None = None


class OnnxFaceAntiSpoofingService(FaceAntiSpoofingServiceInterface):
    """Classify several camera face crops and apply a calibrated median decision."""

    def __init__(
        self,
        *,
        detector: FaceDetectorInterface,
        session: Any | None = None,
        calibration: AntiSpoofCalibration | None = None,
        model_path: Path | None = None,
        require_calibration: bool = True,
    ) -> None:
        settings = get_settings()
        self._detector = detector
        self._model_name = settings.FACE_ANTI_SPOOF_MODEL_NAME
        self._model_path = (
            model_path.resolve()
            if model_path is not None
            else resolve_project_path(settings.FACE_ANTI_SPOOF_MODEL_PATH)
        )
        if not self._model_path.exists():
            raise RuntimeError("Passive anti-spoofing model file was not found.")

        model_hash = _sha384(self._model_path)
        configured_hash = settings.FACE_ANTI_SPOOF_MODEL_SHA384.strip().lower()
        if configured_hash and model_hash != configured_hash:
            raise RuntimeError("Passive anti-spoofing model checksum validation failed.")

        self._calibration = calibration
        if self._calibration is None and require_calibration:
            self._calibration = AntiSpoofCalibration.load(
                resolve_project_path(settings.FACE_ANTI_SPOOF_CALIBRATION_PATH),
                model_name=self._model_name,
                model_sha384=model_hash,
            )
        self._sample_frames = max(1, settings.FACE_ANTI_SPOOF_SAMPLE_FRAMES)
        self._min_valid_frames = max(1, settings.FACE_ANTI_SPOOF_MIN_VALID_FRAMES)
        self._security_debug = settings.FACE_SECURITY_DEBUG

        if session is None:
            try:
                import onnxruntime as ort
            except ModuleNotFoundError as error:
                raise RuntimeError("onnxruntime is required for passive anti-spoofing.") from error
            session = ort.InferenceSession(
                str(self._model_path),
                providers=["CPUExecutionProvider"],
            )
        self._session = session
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name

    def evaluate(self, frames: list[LivenessFrame]) -> AntiSpoofResult:
        if self._calibration is None:
            raise RuntimeError("Passive anti-spoofing cannot decide without local calibration.")
        scored = self.score_sequence(frames)
        if scored.failure_reason or scored.real_score is None:
            if self._security_debug:
                logger.debug(
                    "PAD sequence rejected before classification: frames=%s latency_ms=%s reason=%s",
                    scored.frames_analyzed,
                    scored.latency_ms,
                    scored.failure_reason,
                )
            return AntiSpoofResult(
                is_live=False,
                model_name=self._model_name,
                frames_analyzed=scored.frames_analyzed,
                failure_reason=scored.failure_reason,
                failure_category=AntiSpoofFailureCategory.FRAME_VALIDATION,
                latency_ms=scored.latency_ms,
            )
        passed = scored.real_score >= self._calibration.threshold
        if self._security_debug:
            logger.debug(
                "PAD decision: frames=%s median_real_score=%.6f threshold=%.6f result=%s latency_ms=%s",
                scored.frames_analyzed,
                scored.real_score,
                self._calibration.threshold,
                "PASS" if passed else "REJECT",
                scored.latency_ms,
            )
        return AntiSpoofResult(
            is_live=passed,
            model_name=self._model_name,
            frames_analyzed=scored.frames_analyzed,
            confidence=round(scored.real_score, 4),
            failure_reason=(
                None
                if passed
                else "A live person could not be verified. Please look directly at the camera and try again."
            ),
            failure_category=(
                None if passed else AntiSpoofFailureCategory.PRESENTATION_ATTACK
            ),
            latency_ms=scored.latency_ms,
        )

    def score_sequence(self, frames: list[LivenessFrame]) -> AntiSpoofSequenceScore:
        """Return a raw real-class score for offline local calibration only."""
        started = time.perf_counter()
        candidates = [frame for frame in frames if frame.content]
        if not candidates:
            return self._score_failure("No camera frames were submitted.", started=started)

        scores: list[float] = []
        for frame in _representative_frames(candidates, self._sample_frames):
            image = _decode_image(frame.content)
            if image is None:
                return self._score_failure("A camera frame could not be read.", started=started)

            detection = self._detector.detect_face(frame.content, filename=frame.filename)
            box = self._resolve_primary_box(detection)
            if box is None:
                reason = (
                    "No clear face was detected. Please keep one face visible."
                    if detection.face_count == 0
                    else "Multiple foreground faces were detected. Keep only one person close to the camera."
                )
                return self._score_failure(
                    reason,
                    started=started,
                    frames_analyzed=len(scores),
                )

            crop = _crop_exact_face(image, box)
            if crop is None:
                return self._score_failure(
                    "The face could not be analyzed clearly.",
                    started=started,
                    frames_analyzed=len(scores),
                )
            scores.append(self._real_probability(crop))

        if len(scores) < self._min_valid_frames:
            return self._score_failure(
                "Not enough clear frames were available for live-person verification.",
                started=started,
                frames_analyzed=len(scores),
            )

        sequence_score = float(np.median(np.asarray(scores, dtype=np.float32)))
        return AntiSpoofSequenceScore(
            real_score=sequence_score,
            frames_analyzed=len(scores),
            latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
        )

    def _resolve_primary_box(self, detection) -> FaceBox | None:
        if detection.error_message or detection.face_count == 0:
            return None
        boxes = detection.face_boxes or []
        if detection.face_count == 1 and boxes:
            return boxes[0]
        settings = get_settings()
        return select_primary_face_box(
            boxes,
            frame_size=detection.frame_size,
            min_area_ratio=settings.LIVE_FACE_MIN_AREA_RATIO,
            max_center_distance_ratio=settings.LIVE_FACE_MAX_CENTER_DISTANCE_RATIO,
            dominance_ratio=settings.LIVE_FACE_DOMINANCE_RATIO,
        )

    def _real_probability(self, face_crop: np.ndarray) -> float:
        rgb = cv2.cvtColor(
            cv2.resize(face_crop, (128, 128), interpolation=cv2.INTER_CUBIC),
            cv2.COLOR_BGR2RGB,
        ).astype(np.float32)
        normalized = (rgb - _MODEL_MEAN_RGB) / _MODEL_SCALE_RGB
        tensor = np.transpose(normalized, (2, 0, 1))[None].astype(np.float32)
        output = np.asarray(
            self._session.run([self._output_name], {self._input_name: tensor})[0]
        ).reshape(-1)
        if output.size != 2 or not np.isfinite(output).all():
            raise RuntimeError("Passive anti-spoofing model returned an invalid result.")
        if np.any(output < 0.0) or np.any(output > 1.0) or not np.isclose(output.sum(), 1.0, atol=1e-3):
            shifted = output - np.max(output)
            output = np.exp(shifted) / np.sum(np.exp(shifted))
        # Open Model Zoo defines class 0 as real and class 1 as spoof.
        return float(output[0])

    def _score_failure(
        self,
        reason: str,
        *,
        started: float,
        frames_analyzed: int = 0,
    ) -> AntiSpoofSequenceScore:
        return AntiSpoofSequenceScore(
            real_score=None,
            frames_analyzed=frames_analyzed,
            failure_reason=reason,
            latency_ms=round((time.perf_counter() - started) * 1000.0, 2),
        )


class DisabledFaceAntiSpoofingService(FaceAntiSpoofingServiceInterface):
    """Compatibility adapter used only when passive PAD is explicitly disabled."""

    def evaluate(self, frames: list[LivenessFrame]) -> AntiSpoofResult:
        return AntiSpoofResult(
            is_live=True,
            model_name="disabled",
            frames_analyzed=0,
        )


class FailClosedFaceAntiSpoofingService(FaceAntiSpoofingServiceInterface):
    """Reject live attendance when required PAD configuration cannot be trusted."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name

    def evaluate(self, frames: list[LivenessFrame]) -> AntiSpoofResult:
        return AntiSpoofResult(
            is_live=False,
            model_name=self._model_name,
            frames_analyzed=0,
            failure_reason=(
                "Live-person verification is not calibrated for this camera. "
                "Please contact an administrator."
            ),
            failure_category=AntiSpoofFailureCategory.CONFIGURATION_ERROR,
        )


def _representative_frames(frames: list[LivenessFrame], count: int) -> list[LivenessFrame]:
    if len(frames) <= count:
        return frames
    indexes = np.linspace(0, len(frames) - 1, num=count, dtype=int)
    return [frames[int(index)] for index in indexes]


def _decode_image(content: bytes) -> np.ndarray | None:
    array = np.frombuffer(content, dtype=np.uint8)
    return cv2.imdecode(array, cv2.IMREAD_COLOR)


def _crop_exact_face(image: np.ndarray, box: FaceBox) -> np.ndarray | None:
    x, y, width, height = box
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(image.shape[1], x + width)
    y2 = min(image.shape[0], y + height)
    if x2 <= x1 or y2 <= y1:
        return None
    return image[y1:y2, x1:x2]


def _sha384(path: Path) -> str:
    digest = hashlib.sha384()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
