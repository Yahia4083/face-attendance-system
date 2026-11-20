import pytest
from types import SimpleNamespace

from app.config import PROJECT_ROOT, resolve_project_path
from tools.capture_biometric_evaluation_attempt import (
    _next_attempt_directory,
    _write_attempt,
)
import tools.check_live_attendance_readiness as readiness
from tools.check_live_attendance_readiness import (
    ReadinessCheck,
    _required_checks_pass,
)


def test_project_relative_security_paths_do_not_depend_on_current_directory(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    resolved = resolve_project_path("storage/models/anti_spoof/local-calibration.json")

    assert resolved == PROJECT_ROOT / "storage/models/anti_spoof/local-calibration.json"


def test_pad_capture_uses_independent_numbered_attempt_directories(tmp_path):
    first = _next_attempt_directory(
        tmp_path,
        label="real",
        spoof_type="phone_static",
    )
    first.mkdir(parents=True)

    second = _next_attempt_directory(
        tmp_path,
        label="real",
        spoof_type="phone_static",
    )
    spoof = _next_attempt_directory(
        tmp_path,
        label="spoof",
        spoof_type="phone_static",
    )

    assert second == tmp_path / "real" / "attempt_002"
    assert spoof == tmp_path / "spoof" / "phone_static" / "attempt_001"


def test_pad_capture_writes_validated_sequence_without_overwriting(tmp_path):
    output = tmp_path / "real" / "attempt_001"
    _write_attempt(output, [b"frame-one", b"frame-two"])

    assert (output / "frame_001.jpg").read_bytes() == b"frame-one"
    assert (output / "frame_002.jpg").read_bytes() == b"frame-two"
    with pytest.raises(ValueError, match="new or empty"):
        _write_attempt(output, [b"replacement"])


def test_missing_optional_pad_does_not_block_runtime_readiness():
    checks = [
        ReadinessCheck("Active liveness", True, "available"),
        ReadinessCheck(
            "Passive PAD",
            False,
            "calibration not configured",
            required=False,
        ),
    ]

    assert _required_checks_pass(checks) is True


def test_required_runtime_failure_still_blocks_runtime_readiness():
    checks = [
        ReadinessCheck("Active liveness", False, "unavailable"),
        ReadinessCheck("Passive PAD", True, "available", required=False),
    ]

    assert _required_checks_pass(checks) is False


def test_camera_readiness_recovers_after_one_controlled_reopen(monkeypatch):
    captures = []
    readers = []

    class FakeCapture:
        def __init__(self):
            self.released = False

        def isOpened(self):
            return True

        def release(self):
            self.released = True

    class FakeReader:
        def __init__(self, capture, **_kwargs):
            self.capture = capture
            self.has_frame = len(readers) == 1
            readers.append(self)

        def start(self):
            return self

        def snapshot(self):
            frame = SimpleNamespace(shape=(720, 1280, 3)) if self.has_frame else None
            return SimpleNamespace(camera_available=True, frame=frame)

        def close(self):
            self.capture.release()

    def open_camera(_source):
        capture = FakeCapture()
        captures.append(capture)
        return capture

    monkeypatch.setattr(readiness, "_camera_source", lambda: 0)
    monkeypatch.setattr(readiness, "_open_camera", open_camera)
    monkeypatch.setattr(readiness, "CameraFrameReader", FakeReader)
    monkeypatch.setattr(readiness.time, "sleep", lambda _seconds: None)

    check = readiness._check_camera(0.001)

    assert check.passed is True
    assert "recovered after one reopen" in check.detail
    assert len(captures) == 2
    assert all(capture.released for capture in captures)
