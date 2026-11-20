from datetime import UTC, datetime
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.application.dto.attendance_dto import LiveAttendanceFaceRequest
from app.application.use_cases.attendance.live_attendance import (
    LiveCheckInByFace,
    LiveCheckOutByFace,
    UnifiedLiveAttendanceByFace,
)
from app.application.use_cases.exceptions import BadRequestError, ConflictError, NotFoundError
from app.config import get_settings
from app.dependencies import (
    get_attendance_record_repository,
    get_audit_repository,
    get_clock,
    get_employee_repository,
    get_employee_schedule_repository,
    get_face_recognition_service,
    get_liveness_service,
    get_system_settings_provider,
)
from app.domain.repositories.face_embedding_repository import ActiveFaceEmbeddingForRecognition
from app.domain.services.face_processing_service import FaceDetectionResult
from app.domain.services.face_recognition_service import FaceRecognitionResult
from app.domain.services.liveness_service import (
    LivenessFrame,
    LivenessValidationRequest,
    LivenessValidationResult,
)
from app.infrastructure.face_ai.facenet_recognition_service import FaceNetRecognitionService
from app.infrastructure.face_ai.image_validator import ImageValidator
from app.infrastructure.face_ai.simple_liveness_service import SimpleLivenessService
from app.main import create_app
from app.presentation.api.live_attendance import _unified_live_response
from app.presentation.schemas.live_attendance_schema import LivenessResultResponse
from app.infrastructure.security.permissions import require_admin
from fastapi.testclient import TestClient

from tests.test_attendance_management import (
    FakeAttendanceRepo,
    FakeAuditRepo,
    FakeClock,
    FakeEmployeeRepo,
    FakeRecognitionService,
    FakeScheduleRepo,
)


def _jpeg_frame(*, eye_dark=False, shift=0, asymmetry=0) -> bytes:
    y, x = np.indices((120, 120))
    checker = ((x // 6 + y // 6) % 2) * 36
    image = np.full((120, 120), 128, dtype=np.float32) + checker
    if asymmetry:
        image[:, :60] += asymmetry
        image[:, 60:] -= asymmetry
    if eye_dark:
        image[38:62, 20:100] -= 55
    if shift:
        image = np.roll(image, shift=shift, axis=1)
    image = np.clip(image, 0, 255).astype(np.uint8)
    bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    ok, buffer = cv2.imencode(".jpg", bgr)
    assert ok
    return buffer.tobytes()


def _frames(count=8, *, blink=False, moving=True, prefix="frame"):
    items = []
    for index in range(count):
        items.append(
            LivenessFrame(
                filename=f"{prefix}_{index}.jpg",
                content=_jpeg_frame(
                    eye_dark=blink and index == count // 2,
                    shift=index if moving else 0,
                ),
            )
        )
    return items


class FakeDetector:
    def detect_face(self, image_bytes, *, employee_id=None, filename=None):
        name = filename or ""
        if "noface" in name:
            return FaceDetectionResult(face_count=0)
        if "multi" in name:
            return FaceDetectionResult(face_count=2)
        if "tinybg" in name:
            return FaceDetectionResult(
                face_count=2,
                face_boxes=[(20, 20, 80, 80), (2, 2, 10, 10)],
                frame_size=(120, 120),
            )
        if "twoforeground" in name:
            return FaceDetectionResult(
                face_count=2,
                face_boxes=[(10, 32, 45, 45), (65, 32, 45, 45)],
                frame_size=(120, 120),
            )
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        crop = cv2.imdecode(array, cv2.IMREAD_COLOR)
        return FaceDetectionResult(
            face_count=1,
            face_crop=crop,
            face_boxes=[(20, 20, 80, 80)],
            frame_size=(120, 120),
        )


class CountingRecognitionService(FakeRecognitionService):
    def __init__(self, result=None, error=None):
        super().__init__(result=result, error=error)
        self.calls = 0

    def recognize(self, *, image_bytes, original_filename):
        self.calls += 1
        return super().recognize(image_bytes=image_bytes, original_filename=original_filename)


class FakeLivenessService:
    def __init__(self, *, passed=True, selected_frame=None, reason="Liveness failed"):
        self.passed = passed
        self.selected_frame = selected_frame or LivenessFrame(
            "selected.jpg",
            _jpeg_frame(eye_dark=True),
        )
        self.reason = reason
        self.calls = 0

    def validate(self, request):
        self.calls += 1
        return LivenessValidationResult(
            passed=self.passed,
            challenge_type=request.challenge_type,
            confidence=0.82 if self.passed else 0.1,
            frames_analyzed=len(request.frames),
            selected_frame=self.selected_frame if self.passed else None,
            failure_reason=None if self.passed else self.reason,
        )


def _live_context(*, liveness=None, recognition=None, now=datetime(2026, 6, 1, 8, 0)):
    employee_repo = FakeEmployeeRepo()
    attendance_repo = FakeAttendanceRepo(employee_repo)
    schedule_repo = FakeScheduleRepo()
    audit_repo = FakeAuditRepo()
    return {
        "attendance_repo": attendance_repo,
        "employee_repo": employee_repo,
        "schedule_repo": schedule_repo,
        "recognition_service": recognition or CountingRecognitionService(),
        "liveness_service": liveness or FakeLivenessService(),
        "audit_repo": audit_repo,
        "clock": FakeClock(now),
        "settings_provider": None,
    }


def _request(frames=None, challenge="BLINK"):
    return LiveAttendanceFaceRequest(
        frames=frames or _frames(blink=True),
        challenge_type=challenge,
        actor_user_id=1,
        ip_address="127.0.0.1",
    )


def test_liveness_rejects_no_frames():
    result = SimpleLivenessService(FakeDetector()).validate(
        LivenessValidationRequest(frames=[], challenge_type="BLINK")
    )
    assert not result.passed
    assert "No frames" in result.failure_reason


def test_liveness_rejects_no_face():
    result = SimpleLivenessService(FakeDetector()).validate(
        LivenessValidationRequest(frames=_frames(prefix="noface"), challenge_type="BLINK")
    )
    assert not result.passed
    assert "No face" in result.failure_reason


def test_liveness_rejects_multiple_faces():
    result = SimpleLivenessService(FakeDetector()).validate(
        LivenessValidationRequest(frames=_frames(prefix="multi"), challenge_type="BLINK")
    )
    assert not result.passed
    assert "Multiple faces" in result.failure_reason


def test_liveness_rejects_static_sequence():
    result = SimpleLivenessService(FakeDetector()).validate(
        LivenessValidationRequest(frames=_frames(moving=False, blink=False), challenge_type="BLINK")
    )
    assert not result.passed
    assert "static" in result.failure_reason


def test_liveness_rejects_missing_challenge_completion():
    result = SimpleLivenessService(FakeDetector()).validate(
        LivenessValidationRequest(frames=_frames(moving=True, blink=False), challenge_type="BLINK")
    )
    assert not result.passed
    assert "blink" in result.failure_reason.lower()


def test_liveness_accepts_valid_blink_sequence():
    result = SimpleLivenessService(FakeDetector()).validate(
        LivenessValidationRequest(frames=_frames(moving=True, blink=True), challenge_type="BLINK")
    )
    assert result.passed
    assert result.selected_frame is not None
    assert result.frames_analyzed == 8
    assert result.confidence >= 0.55


def test_liveness_accepts_primary_face_with_tiny_background_face():
    result = SimpleLivenessService(FakeDetector()).validate(
        LivenessValidationRequest(frames=_frames(moving=True, blink=True, prefix="tinybg"), challenge_type="BLINK")
    )

    assert result.passed
    assert result.selected_frame is not None
    assert result.frames_analyzed == 8


def test_liveness_rejects_two_significant_foreground_faces():
    result = SimpleLivenessService(FakeDetector()).validate(
        LivenessValidationRequest(frames=_frames(moving=True, blink=True, prefix="twoforeground"), challenge_type="BLINK")
    )

    assert not result.passed
    assert "Multiple" in result.failure_reason


def test_recognition_is_not_attempted_when_liveness_fails():
    recognition = CountingRecognitionService()
    context = _live_context(
        liveness=FakeLivenessService(passed=False, reason="Challenge not completed"),
        recognition=recognition,
    )
    with pytest.raises(BadRequestError):
        LiveCheckInByFace(**context).execute(_request())
    assert recognition.calls == 0
    assert context["audit_repo"].entries[-1]["action"] == "LIVENESS_VERIFICATION_FAILED"


def test_unknown_live_face_is_rejected_after_liveness_passes():
    recognition = CountingRecognitionService(
        result=FaceRecognitionResult(matched=False, failure_reason="no_match")
    )
    context = _live_context(recognition=recognition)
    with pytest.raises(NotFoundError):
        LiveCheckInByFace(**context).execute(_request())
    assert recognition.calls == 1


def test_valid_live_employee_check_in_and_duplicate_rejected():
    context = _live_context()
    result = LiveCheckInByFace(**context).execute(_request())
    assert result.attendance.record.employee_id == 1
    assert result.liveness.passed
    with pytest.raises(ConflictError):
        LiveCheckInByFace(**context).execute(_request())


def test_valid_live_employee_check_out_and_duplicate_rejected():
    context = _live_context()
    LiveCheckInByFace(**context).execute(_request())
    result = LiveCheckOutByFace(**context).execute(_request())
    assert result.attendance.record.check_out_time is not None
    assert result.liveness.passed
    with pytest.raises(ConflictError):
        LiveCheckOutByFace(**context).execute(_request())


def test_unified_live_attendance_first_attempt_checks_in_and_recognizes_once():
    recognition = CountingRecognitionService()
    context = _live_context(recognition=recognition)

    result = UnifiedLiveAttendanceByFace(**context).execute(_request())

    assert result.attendance.event_type == "CHECK_IN"
    assert result.attendance.record.employee_id == 1
    assert result.attendance.record.check_out_time is None
    assert recognition.calls == 1
    assert '"source": "LIVE_KIOSK"' in context["audit_repo"].entries[-1]["new_values"]


def test_unified_live_attendance_does_not_require_optional_pad_calibration(
    tmp_path,
    monkeypatch,
):
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "FACE_ANTI_SPOOF_CALIBRATION_PATH",
        str(tmp_path / "missing-calibration.json"),
    )
    context = _live_context()

    result = UnifiedLiveAttendanceByFace(**context).execute(_request())

    assert result.liveness.passed is True
    assert context["liveness_service"].calls == 1
    assert context["recognition_service"].calls == 1
    assert len(context["attendance_repo"].records) == 1


def test_unified_live_attendance_open_record_checks_out_and_reuses_record():
    recognition = CountingRecognitionService()
    context = _live_context(recognition=recognition)
    first = UnifiedLiveAttendanceByFace(**context).execute(_request())
    context["clock"].current = datetime(2026, 6, 1, 16, 0)

    second = UnifiedLiveAttendanceByFace(**context).execute(_request())

    assert second.attendance.event_type == "CHECK_OUT"
    assert second.attendance.record.id == first.attendance.record.id
    assert second.attendance.record.check_out_time == datetime(2026, 6, 1, 16, 0)
    assert second.attendance.record.working_hours == 8.0
    assert recognition.calls == 2


def test_unified_live_attendance_stale_open_record_starts_new_check_in():
    context = _live_context(now=datetime(2026, 6, 1, 8, 0))
    use_case = UnifiedLiveAttendanceByFace(**context)
    stale_record = use_case.execute(_request()).attendance.record
    context["clock"].current = datetime(2026, 6, 3, 8, 0)

    current = use_case.execute(_request())

    assert current.attendance.event_type == "CHECK_IN"
    assert current.attendance.record.id != stale_record.id
    assert current.attendance.record.attendance_date.isoformat() == "2026-06-03"
    assert stale_record.check_out_time is None


def test_live_checkout_rejects_stale_open_record():
    context = _live_context(now=datetime(2026, 6, 1, 8, 0))
    LiveCheckInByFace(**context).execute(_request())
    context["clock"].current = datetime(2026, 6, 3, 8, 0)

    with pytest.raises(ConflictError, match="No open attendance record"):
        LiveCheckOutByFace(**context).execute(_request())


def test_unified_live_attendance_completed_record_rejects_third_attempt():
    context = _live_context()
    use_case = UnifiedLiveAttendanceByFace(**context)
    use_case.execute(_request())
    context["clock"].current = datetime(2026, 6, 1, 16, 0)
    use_case.execute(_request())

    with pytest.raises(ConflictError, match="Attendance already completed for today"):
        use_case.execute(_request())

    assert len(context["attendance_repo"].records) == 1


def test_unified_live_attendance_rejects_inactive_recognized_employee():
    recognition = CountingRecognitionService(
        result=FaceRecognitionResult(
            matched=True,
            employee_id=3,
            matched_model_name="facenet-onnx-512d-haikalmumtaz-v1",
        )
    )
    context = _live_context(recognition=recognition)

    with pytest.raises(BadRequestError, match="inactive"):
        UnifiedLiveAttendanceByFace(**context).execute(_request())

    assert context["attendance_repo"].records == []


def test_unified_live_attendance_preserves_schedule_late_and_checkout_rules():
    context = _live_context(now=datetime(2026, 6, 1, 8, 11))
    context["schedule_repo"].add_assignment(grace=10, tolerance=5)
    use_case = UnifiedLiveAttendanceByFace(**context)

    check_in = use_case.execute(_request())
    context["clock"].current = datetime(2026, 6, 1, 15, 30)
    check_out = use_case.execute(_request())

    assert check_in.attendance.record.is_late is True
    assert check_out.attendance.record.is_early_departure is True
    assert check_out.attendance.record.working_hours == 7.32


def test_unified_live_attendance_preserves_unscheduled_status():
    context = _live_context(now=datetime(2026, 6, 7, 8, 0))

    result = UnifiedLiveAttendanceByFace(**context).execute(_request())

    assert result.attendance.record.is_unscheduled is True
    assert result.attendance.record.status.value == "UNSCHEDULED"


def test_unified_live_attendance_liveness_failure_changes_no_attendance():
    recognition = CountingRecognitionService()
    context = _live_context(
        liveness=FakeLivenessService(passed=False),
        recognition=recognition,
    )

    with pytest.raises(BadRequestError):
        UnifiedLiveAttendanceByFace(**context).execute(_request())

    assert recognition.calls == 0
    assert context["attendance_repo"].records == []


def test_unified_live_attendance_response_is_safe_and_timezone_aware():
    context = _live_context()
    result = UnifiedLiveAttendanceByFace(**context).execute(_request())

    payload = _unified_live_response(result).model_dump()

    assert payload["success"] is True
    assert payload["action"] == "CHECK_IN"
    assert payload["timestamp"].endswith("+02:00")
    forbidden = {"embedding", "vector", "token", "password", "image_bytes"}
    assert forbidden.isdisjoint(payload)


def test_unified_live_attendance_endpoint_is_registered_and_protected():
    client = TestClient(create_app())

    assert "/attendance/live/attendance" in client.get("/openapi.json").json()["paths"]
    response = client.post("/attendance/live/attendance")

    assert response.status_code in {401, 403}


def test_unified_live_attendance_endpoint_automatically_checks_in_then_out():
    context = _live_context()
    app = create_app()
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_attendance_record_repository] = lambda: context[
        "attendance_repo"
    ]
    app.dependency_overrides[get_employee_repository] = lambda: context["employee_repo"]
    app.dependency_overrides[get_employee_schedule_repository] = lambda: context[
        "schedule_repo"
    ]
    app.dependency_overrides[get_face_recognition_service] = lambda: context[
        "recognition_service"
    ]
    app.dependency_overrides[get_liveness_service] = lambda: context["liveness_service"]
    app.dependency_overrides[get_audit_repository] = lambda: context["audit_repo"]
    app.dependency_overrides[get_clock] = lambda: context["clock"]
    app.dependency_overrides[get_system_settings_provider] = lambda: None
    client = TestClient(app)
    files = [
        ("frames", (f"frame_{index}.jpg", b"frame", "image/jpeg"))
        for index in range(8)
    ]

    check_in = client.post(
        "/attendance/live/attendance",
        data={"challenge_type": "BLINK"},
        files=files,
    )
    context["clock"].current = datetime(2026, 6, 1, 16, 0)
    check_out = client.post(
        "/attendance/live/attendance",
        data={"challenge_type": "BLINK"},
        files=files,
    )

    assert check_in.status_code == 200
    assert check_in.json()["action"] == "CHECK_IN"
    assert check_out.status_code == 200
    assert check_out.json()["action"] == "CHECK_OUT"
    assert check_out.json()["attendance_record_id"] == check_in.json()[
        "attendance_record_id"
    ]


def test_liveness_response_does_not_expose_sensitive_values():
    response = LivenessResultResponse(
        passed=True,
        challenge_type="BLINK",
        confidence=0.82,
        frames_analyzed=8,
    )
    payload = response.model_dump()
    forbidden = {"embedding", "vector", "similarity_score", "token", "image_bytes"}
    assert forbidden.isdisjoint(payload.keys())


def test_facenet_recognition_still_uses_configured_model_name():
    class FakeEmbeddingRepo:
        def get_active_compatible_embeddings_for_recognition(self, model_name):
            return [
                ActiveFaceEmbeddingForRecognition(
                    employee_id=1,
                    embedding_vector=[1.0, 0.0],
                    model_name=model_name,
                )
            ]

    class FakeEmbedder:
        @property
        def model_name(self):
            return "facenet-onnx-512d-haikalmumtaz-v1"

        def generate_embedding(self, face_image):
            return [1.0, 0.0]

    service = FaceNetRecognitionService(
        image_validator=ImageValidator(),
        detector=FakeDetector(),
        embedder=FakeEmbedder(),
        face_embedding_repo=FakeEmbeddingRepo(),
    )
    result = service.recognize(image_bytes=_jpeg_frame(), original_filename="frame.jpg")
    assert result.matched
    assert result.matched_model_name == "facenet-onnx-512d-haikalmumtaz-v1"


def test_phase14_keeps_mtcnn_and_facenet_backends_configured():
    settings = get_settings()

    assert settings.FACE_DETECTOR_BACKEND == "mtcnn"
    assert settings.FACE_EMBEDDER_BACKEND == "facenet"
