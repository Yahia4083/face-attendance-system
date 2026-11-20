import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.config import get_settings
from app.domain.services.face_processing_service import FaceDetectionResult
from app.domain.services.liveness_service import (
    LivenessFrame,
    LivenessValidationRequest,
)
from app.infrastructure.face_ai.face_alignment import (
    align_face,
    validate_preprocessing_model_identity,
)
from app.infrastructure.face_ai.face_anti_spoofing import (
    AntiSpoofCalibration,
    OnnxFaceAntiSpoofingService,
)
from app.infrastructure.face_ai.face_quality import FaceEnrollmentQualityValidator
from app.infrastructure.face_ai.recognition_policy import aggregate_similarity
from app.infrastructure.face_ai.simple_liveness_service import SimpleLivenessService


def _calibration_payload(**overrides):
    settings = get_settings()
    payload = {
        "validated": True,
        "model_name": settings.FACE_ANTI_SPOOF_MODEL_NAME,
        "model_sha384": settings.FACE_ANTI_SPOOF_MODEL_SHA384,
        "aggregation": "median",
        "threshold": 0.73,
        "real_attempts": 12,
        "spoof_attempts": 14,
    }
    payload.update(overrides)
    return payload


def _write_calibration(path: Path, **overrides) -> Path:
    path.write_text(json.dumps(_calibration_payload(**overrides)), encoding="utf-8")
    return path


def _load_calibration(path: Path):
    settings = get_settings()
    return AntiSpoofCalibration.load(
        path,
        model_name=settings.FACE_ANTI_SPOOF_MODEL_NAME,
        model_sha384=settings.FACE_ANTI_SPOOF_MODEL_SHA384,
    )


def test_missing_pad_calibration_is_rejected(tmp_path):
    with pytest.raises(RuntimeError, match="calibration is missing"):
        _load_calibration(tmp_path / "missing.json")


def test_valid_pad_calibration_loads_through_runtime_parser(tmp_path):
    calibration = _load_calibration(_write_calibration(tmp_path / "calibration.json"))

    assert calibration.threshold == pytest.approx(0.73)
    assert calibration.real_attempts == 12
    assert calibration.spoof_attempts == 14


def test_invalid_pad_calibration_json_is_rejected(tmp_path):
    path = tmp_path / "calibration.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="file is invalid"):
        _load_calibration(path)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"validated": False}, "not been marked as validated"),
        ({"model_name": "another-model"}, "another model"),
        ({"model_sha384": "0" * 96}, "does not match the model file"),
        ({"threshold": 0.0}, "between 0 and 1"),
        ({"threshold": 1.0}, "between 0 and 1"),
        ({"aggregation": "mean"}, "aggregation is unsupported"),
    ],
)
def test_invalid_pad_calibration_metadata_is_rejected(tmp_path, overrides, message):
    path = _write_calibration(tmp_path / "calibration.json", **overrides)

    with pytest.raises(RuntimeError, match=message):
        _load_calibration(path)


def _jpeg_frame(*, shift: int = 0) -> bytes:
    y, x = np.indices((120, 120))
    checker = (((x + shift) // 5 + y // 5) % 2) * 90 + 70
    image = cv2.cvtColor(checker.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def _landmarks(*, nose_offset: float = 0.0):
    return {
        "left_eye": (40.0, 44.0),
        "right_eye": (80.0, 44.0),
        "nose": (60.0 + nose_offset, 64.0),
        "mouth_left": (47.0, 82.0),
        "mouth_right": (73.0, 82.0),
    }


def test_five_point_alignment_is_deterministic_and_face_focused():
    y, x = np.indices((180, 180))
    image = np.stack((x, y, (x + y) // 2), axis=2).astype(np.uint8)
    landmarks = {
        "left_eye": (55.0, 62.0),
        "right_eye": (119.0, 68.0),
        "nose": (85.0, 96.0),
        "mouth_left": (61.0, 124.0),
        "mouth_right": (108.0, 128.0),
    }

    first = align_face(image, landmarks)
    second = align_face(image, landmarks)

    assert first.shape == (160, 160, 3)
    assert np.array_equal(first, second)
    assert float(np.std(first)) > 1.0


def test_aligned_preprocessing_requires_a_versioned_embedding_identity():
    with pytest.raises(RuntimeError, match="aligned-v2"):
        validate_preprocessing_model_identity(
            alignment_enabled=True,
            model_name="facenet-onnx-512d-haikalmumtaz-v1",
        )


def test_enrollment_quality_rejects_blurred_face():
    detection = FaceDetectionResult(
        face_count=1,
        face_crop=np.full((120, 120, 3), 128, dtype=np.uint8),
        face_boxes=[(20, 20, 120, 120)],
        face_landmarks=_landmarks(),
        frame_size=(200, 200),
    )

    result = FaceEnrollmentQualityValidator().assess(detection)

    assert result.accepted is False
    assert "blurred" in (result.reason or "").lower()


def test_multi_embedding_mean_top_k_ignores_one_weak_enrollment_sample():
    probe = np.asarray([1.0, 0.0], dtype=np.float32)
    enrollment = [
        np.asarray([1.0, 0.0], dtype=np.float32),
        np.asarray([0.98, 0.2], dtype=np.float32) / np.linalg.norm([0.98, 0.2]),
        np.asarray([-1.0, 0.0], dtype=np.float32),
    ]

    score = aggregate_similarity(
        probe,
        enrollment,
        strategy="mean_top_k",
        top_k=2,
    )

    assert score > 0.98


class _FakeDetector:
    def detect_face(self, image_bytes, *, employee_id=None, filename=None):
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        return FaceDetectionResult(
            face_count=1,
            face_crop=image[20:100, 20:100],
            face_boxes=[(20, 20, 80, 80)],
            face_landmarks=_landmarks(),
            frame_size=(120, 120),
        )


class _FakeSession:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    @staticmethod
    def get_inputs():
        return [SimpleNamespace(name="actual_input_1")]

    @staticmethod
    def get_outputs():
        return [SimpleNamespace(name="output1")]

    def run(self, output_names, inputs):
        return [np.asarray([next(self.outputs)], dtype=np.float32)]


@pytest.fixture
def pad_model_path(tmp_path, monkeypatch):
    model_path = tmp_path / "model.onnx"
    model_bytes = b"Test model bytes for the fake inference session"
    model_path.write_bytes(model_bytes)
    monkeypatch.setattr(
        get_settings(), "FACE_ANTI_SPOOF_MODEL_SHA384", hashlib.sha384(model_bytes).hexdigest()
    )
    return model_path


def _anti_spoof_service(outputs, *, model_path, threshold=0.8):
    settings = get_settings()
    return OnnxFaceAntiSpoofingService(
        detector=_FakeDetector(),
        session=_FakeSession(outputs),
        model_path=model_path,
        calibration=AntiSpoofCalibration(
            threshold=threshold,
            model_name=settings.FACE_ANTI_SPOOF_MODEL_NAME,
            model_sha384=settings.FACE_ANTI_SPOOF_MODEL_SHA384,
            real_attempts=4,
            spoof_attempts=4,
            aggregation="median",
        ),
    )


def test_passive_anti_spoof_returns_structured_multi_frame_result(pad_model_path):
    service = _anti_spoof_service([[0.91, 0.09]] * 4, model_path=pad_model_path)
    frames = [LivenessFrame(f"frame_{index}.jpg", _jpeg_frame(shift=index)) for index in range(4)]

    result = service.evaluate(frames)

    assert result.is_live is True
    assert result.frames_analyzed == 4
    assert result.model_name == get_settings().FACE_ANTI_SPOOF_MODEL_NAME
    assert result.confidence == pytest.approx(0.91, abs=1e-4)


def test_optional_passive_pad_module_rejects_a_below_threshold_sequence(pad_model_path):
    service = _anti_spoof_service([[0.2, 0.8]] * 4, model_path=pad_model_path, threshold=0.8)
    frames = [LivenessFrame(f"frame_{index}.jpg", _jpeg_frame(shift=index)) for index in range(4)]

    result = service.evaluate(frames)

    assert result.is_live is False
    assert result.frames_analyzed == 4


class _LandmarkSequenceDetector:
    def __init__(self, *, swap_at: int | None = None):
        self.index = 0
        self.swap_at = swap_at

    def detect_face(self, image_bytes, *, employee_id=None, filename=None):
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        offset = float(self.index)
        landmarks = _landmarks(nose_offset=offset)
        if self.swap_at == self.index:
            landmarks = {name: (x + 35.0, y - 20.0) for name, (x, y) in landmarks.items()}
        self.index += 1
        return FaceDetectionResult(
            face_count=1,
            face_crop=image[20:100, 20:100],
            face_boxes=[(20, 20, 80, 80)],
            face_landmarks=landmarks,
            frame_size=(120, 120),
        )


def test_hardened_head_turn_uses_landmark_direction_and_passes():
    frames = [LivenessFrame(f"frame_{index}.jpg", _jpeg_frame(shift=index)) for index in range(8)]
    service = SimpleLivenessService(_LandmarkSequenceDetector(), hardened_mode=True)

    result = service.validate(
        LivenessValidationRequest(frames=frames, challenge_type="TURN_HEAD_LEFT")
    )

    assert result.passed is True


def test_hardened_liveness_rejects_face_discontinuity():
    frames = [LivenessFrame(f"frame_{index}.jpg", _jpeg_frame(shift=index)) for index in range(8)]
    service = SimpleLivenessService(
        _LandmarkSequenceDetector(swap_at=4),
        hardened_mode=True,
    )

    result = service.validate(
        LivenessValidationRequest(frames=frames, challenge_type="TURN_HEAD_LEFT")
    )

    assert result.passed is False
    assert "same face" in (result.failure_reason or "").lower()


def test_hardened_mode_does_not_claim_blink_without_eye_state_landmarks():
    service = SimpleLivenessService(_LandmarkSequenceDetector(), hardened_mode=True)

    result = service.validate(
        LivenessValidationRequest(
            frames=[LivenessFrame("frame.jpg", _jpeg_frame())] * 8,
            challenge_type="BLINK",
        )
    )

    assert result.passed is False
    assert "unavailable" in (result.failure_reason or "").lower()
