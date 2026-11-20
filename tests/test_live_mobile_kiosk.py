import httpx
import numpy as np
import pytest
from threading import Event
import time

from tools import live_mobile_attendance_kiosk as kiosk


def test_mobile_kiosk_camera_source_prefers_new_env_and_converts_numeric(monkeypatch):
    monkeypatch.setenv("MOBILE_CAMERA_SOURCE", "0")
    monkeypatch.setenv("MOBILE_CAMERA_STREAM_URL", "rtsp://example.test/old-stream")

    source = kiosk._camera_source()

    assert source == 0
    assert isinstance(source, int)


def test_mobile_kiosk_camera_source_falls_back_to_stream_url(monkeypatch):
    monkeypatch.delenv("MOBILE_CAMERA_SOURCE", raising=False)
    monkeypatch.setenv("MOBILE_CAMERA_STREAM_URL", "rtsp://172.20.10.1:8554/stream")

    assert kiosk._camera_source() == "rtsp://172.20.10.1:8554/stream"


def test_mobile_kiosk_camera_source_defaults_to_webcam_index_zero(monkeypatch):
    monkeypatch.delenv("MOBILE_CAMERA_SOURCE", raising=False)
    monkeypatch.delenv("MOBILE_CAMERA_STREAM_URL", raising=False)

    assert kiosk._camera_source() == 0


def test_mobile_kiosk_blank_stream_url_defaults_to_webcam_index_zero(monkeypatch):
    monkeypatch.delenv("MOBILE_CAMERA_SOURCE", raising=False)
    monkeypatch.setenv("MOBILE_CAMERA_STREAM_URL", " ")

    assert kiosk._camera_source() == 0


def test_mobile_kiosk_worker_frame_count_defaults_to_twelve(monkeypatch):
    monkeypatch.delenv("LIVE_ATTENDANCE_WORKER_FRAME_COUNT", raising=False)

    assert kiosk._worker_frame_count(minimum=8) == 12


def test_mobile_kiosk_worker_frame_count_never_goes_below_backend_minimum(monkeypatch):
    monkeypatch.setenv("LIVE_ATTENDANCE_WORKER_FRAME_COUNT", "4")

    assert kiosk._worker_frame_count(minimum=8) == 8


def test_mobile_kiosk_worker_frame_count_allows_higher_demo_values(monkeypatch):
    monkeypatch.setenv("LIVE_ATTENDANCE_WORKER_FRAME_COUNT", "18")

    assert kiosk._worker_frame_count(minimum=8) == 18


def test_mobile_kiosk_uses_dshow_for_integer_camera_source_on_windows(monkeypatch):
    calls = []

    class FakeCapture:
        @staticmethod
        def isOpened():
            return True

        @staticmethod
        def release():
            return None

    def fake_video_capture(source, *args):
        calls.append((source, args))
        return FakeCapture()

    monkeypatch.setattr(kiosk.os, "name", "nt")
    monkeypatch.setattr(kiosk.cv2, "VideoCapture", fake_video_capture)

    kiosk._open_camera(0)

    assert calls == [(0, (kiosk.cv2.CAP_DSHOW,))]


def test_mobile_kiosk_falls_back_to_msmf_when_dshow_cannot_open(monkeypatch):
    calls = []
    captures = []

    class FakeCapture:
        def __init__(self, opened):
            self.opened = opened
            self.released = False

        def isOpened(self):
            return self.opened

        def release(self):
            self.released = True

    def fake_video_capture(source, backend):
        calls.append((source, backend))
        capture = FakeCapture(opened=backend == kiosk.cv2.CAP_MSMF)
        captures.append(capture)
        return capture

    monkeypatch.setattr(kiosk.os, "name", "nt")
    monkeypatch.setattr(kiosk.cv2, "VideoCapture", fake_video_capture)

    selected = kiosk._open_camera(1)

    assert calls == [(1, kiosk.cv2.CAP_DSHOW), (1, kiosk.cv2.CAP_MSMF)]
    assert captures[0].released is True
    assert selected is captures[1]


def test_mobile_kiosk_uses_plain_video_capture_for_url(monkeypatch):
    calls = []

    class FakeCapture:
        pass

    def fake_video_capture(source, *args):
        calls.append((source, args))
        return FakeCapture()

    monkeypatch.setattr(kiosk.cv2, "VideoCapture", fake_video_capture)

    kiosk._open_camera("rtsp://172.20.10.1:8554/stream")

    assert calls == [("rtsp://172.20.10.1:8554/stream", ())]


def test_mobile_kiosk_prepare_frame_applies_rotation_and_flip():
    frame = np.arange(2 * 3 * 3, dtype=np.uint8).reshape(2, 3, 3)

    prepared = kiosk._prepare_frame(frame, rotate=180, flip=True)

    assert np.array_equal(prepared, np.fliplr(np.rot90(frame, 2)))


def test_mobile_kiosk_rotation_setting_rejects_unsupported_value(monkeypatch):
    monkeypatch.setenv("LIVE_CAMERA_ROTATE", "45")

    with pytest.raises(ValueError, match="LIVE_CAMERA_ROTATE"):
        kiosk._rotation_setting()


def test_mobile_kiosk_open_error_mentions_webcam_indexes_for_numeric_source():
    message = kiosk._camera_open_error(0)

    assert "MOBILE_CAMERA_SOURCE=0, 1, or 2" in message


def test_mobile_kiosk_open_error_mentions_vlc_or_browser_for_url_source():
    message = kiosk._camera_open_error("rtsp://172.20.10.1:8554/stream")

    assert "VLC or a browser" in message


def test_mobile_kiosk_idle_button_is_clickable_and_requests_single_action():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    session = kiosk.KioskSession(state_changed_at=0.0)
    _preview, bounds = kiosk._render_kiosk_frame(frame, session)
    interaction = kiosk.KioskInteraction(
        button_bounds=bounds,
        button_enabled=True,
    )

    interaction.on_mouse(
        kiosk.cv2.EVENT_LBUTTONDOWN,
        (bounds.left + bounds.right) // 2,
        (bounds.top + bounds.bottom) // 2,
        0,
        None,
    )

    assert interaction.consume_start() is True
    assert interaction.consume_start() is False


def test_mobile_kiosk_state_machine_blocks_reentry_and_resets_after_cooldown():
    session = kiosk.KioskSession(state_changed_at=0.0)

    assert session.start(now=1.0) is True
    assert session.start(now=1.1) is False
    session.transition(
        kiosk.KioskState.RECOGNIZING,
        "Verifying identity...",
        now=2.0,
    )
    session.advance(
        now=3.0,
        result_display_seconds=4.0,
        cooldown_seconds=3.0,
        request_in_progress=True,
    )
    assert session.state == kiosk.KioskState.PROCESSING_ATTENDANCE

    session.finish(
        success=True,
        result={"message": "Recorded", "action": "CHECK_IN"},
        now=4.0,
    )
    session.advance(
        now=8.0,
        result_display_seconds=4.0,
        cooldown_seconds=3.0,
        request_in_progress=False,
    )
    assert session.state == kiosk.KioskState.COOLDOWN
    assert session.can_start is False

    session.advance(
        now=11.0,
        result_display_seconds=4.0,
        cooldown_seconds=3.0,
        request_in_progress=False,
    )
    assert session.state == kiosk.KioskState.IDLE
    assert session.can_start is True


@pytest.mark.parametrize("success", [True, False])
def test_mobile_kiosk_result_always_reaches_idle_and_allows_a_second_attempt(success):
    session = kiosk.KioskSession(state_changed_at=0.0)
    attempt = kiosk.AttendanceAttemptRuntime()
    attempt.begin()

    session.finish(
        success=success,
        result={"message": "Completed" if success else "Rejected"},
        now=10.0,
    )
    attempt.clear()
    session.advance(
        now=14.0,
        result_display_seconds=4.0,
        cooldown_seconds=3.0,
        request_in_progress=attempt.request_in_progress,
    )
    assert session.state == kiosk.KioskState.COOLDOWN

    session.advance(
        now=17.0,
        result_display_seconds=4.0,
        cooldown_seconds=3.0,
        request_in_progress=attempt.request_in_progress,
    )

    assert session.state == kiosk.KioskState.IDLE
    assert session.result is None
    assert session.can_start is True
    assert session.start(now=18.0) is True


def test_mobile_kiosk_delayed_loop_catches_up_past_result_and_cooldown_deadlines():
    session = kiosk.KioskSession(state_changed_at=0.0)
    session.finish(success=True, result={"message": "Recorded"}, now=5.0)

    session.advance(
        now=30.0,
        result_display_seconds=4.0,
        cooldown_seconds=3.0,
        request_in_progress=False,
    )

    assert session.state == kiosk.KioskState.IDLE
    assert session.can_start is True


def test_mobile_kiosk_completed_worker_clears_processing_future_and_challenge():
    attempt = kiosk.AttendanceAttemptRuntime()
    future = kiosk.Future()
    attempt.begin()
    attempt.attach_request(future, challenge="TURN_HEAD_LEFT")
    future.set_result((True, {"message": "Recorded", "action": "CHECK_IN"}))

    completed = kiosk._consume_completed_request(attempt)

    assert completed == (True, {"message": "Recorded", "action": "CHECK_IN"})
    assert attempt.processing is False
    assert attempt.request_future is None
    assert attempt.challenge is None


def test_mobile_kiosk_failed_worker_still_releases_processing_lock():
    attempt = kiosk.AttendanceAttemptRuntime()
    future = kiosk.Future()
    attempt.begin()
    attempt.attach_request(future, challenge="TURN_HEAD_RIGHT")
    future.set_exception(RuntimeError("private backend failure"))

    success, payload = kiosk._consume_completed_request(attempt)

    assert success is False
    assert payload["error_category"] == "BACKEND_UNAVAILABLE"
    assert attempt.processing is False
    assert attempt.request_future is None
    assert attempt.challenge is None


def test_mobile_kiosk_primary_action_returns_after_cooldown_cleanup():
    frame = np.full((720, 1280, 3), 120, dtype=np.uint8)
    session = kiosk.KioskSession(state_changed_at=0.0)
    attempt = kiosk.AttendanceAttemptRuntime()
    _preview, bounds = kiosk._render_kiosk_frame(frame, session)

    assert kiosk._primary_action_available(
        session,
        attempt,
        button_bounds=bounds,
        camera_available=True,
    ) is True

    attempt.begin()
    assert kiosk._primary_action_available(
        session,
        attempt,
        button_bounds=bounds,
        camera_available=True,
    ) is False

    attempt.clear()
    assert kiosk._primary_action_available(
        session,
        attempt,
        button_bounds=bounds,
        camera_available=True,
    ) is True


def test_mobile_kiosk_keeps_latest_valid_frame_after_temporary_read_failure():
    valid_frame = np.full((4, 6, 3), 77, dtype=np.uint8)

    class FakeCapture:
        def __init__(self):
            self.calls = 0
            self.released = Event()

        def read(self):
            self.calls += 1
            if self.calls == 1:
                return True, valid_frame
            if self.calls == 2:
                return False, None
            self.released.wait(timeout=1.0)
            return False, None

        def release(self):
            self.released.set()

    capture = FakeCapture()
    reader = kiosk.CameraFrameReader(
        capture,
        rotate=0,
        flip=False,
        unavailable_after=3,
        stale_after_seconds=5.0,
    ).start()
    try:
        deadline = time.monotonic() + 1.0
        snapshot = reader.snapshot()
        while snapshot.consecutive_failures < 1 and time.monotonic() < deadline:
            time.sleep(0.005)
            snapshot = reader.snapshot()

        assert np.array_equal(snapshot.frame, valid_frame)
        assert snapshot.camera_available is True
        assert snapshot.consecutive_failures == 1
    finally:
        reader.close()


def test_mobile_kiosk_marks_camera_unavailable_only_after_failure_threshold():
    class FailingCapture:
        def __init__(self):
            self.released = False

        def read(self):
            if self.released:
                return False, None
            return False, None

        def release(self):
            self.released = True

    capture = FailingCapture()
    reader = kiosk.CameraFrameReader(
        capture,
        rotate=0,
        flip=False,
        unavailable_after=2,
        stale_after_seconds=5.0,
    ).start()
    try:
        deadline = time.monotonic() + 1.0
        snapshot = reader.snapshot()
        while snapshot.camera_available and time.monotonic() < deadline:
            time.sleep(0.005)
            snapshot = reader.snapshot()

        assert snapshot.consecutive_failures >= 2
        assert snapshot.camera_available is False
    finally:
        reader.close()


def test_mobile_kiosk_blocked_camera_read_does_not_block_ui_snapshot_polling():
    read_started = Event()
    released = Event()

    class BlockingCapture:
        @staticmethod
        def read():
            read_started.set()
            released.wait(timeout=2.0)
            return False, None

        @staticmethod
        def release():
            released.set()

    reader = kiosk.CameraFrameReader(
        BlockingCapture(),
        rotate=0,
        flip=False,
        unavailable_after=3,
        stale_after_seconds=0.05,
    ).start()
    try:
        assert read_started.wait(timeout=0.5)
        time.sleep(0.06)
        started = time.perf_counter()
        snapshot = reader.snapshot()
        elapsed = time.perf_counter() - started

        assert elapsed < 0.05
        assert snapshot.camera_available is False
        assert snapshot.frame is None
    finally:
        reader.close()


def test_mobile_kiosk_rejects_driver_generated_all_black_frames():
    assert kiosk._camera_frame_has_signal(True, np.zeros((10, 10, 3), dtype=np.uint8)) is False
    assert kiosk._camera_frame_has_signal(True, np.full((80, 80, 3), 140, dtype=np.uint8)) is False

    visible = np.zeros((80, 80, 3), dtype=np.uint8)
    visible[:, 40:] = 220
    assert kiosk._camera_frame_has_signal(True, visible) is True


def test_mobile_kiosk_transition_logging_is_opt_in(capsys):
    quiet = kiosk.KioskSession(state_changed_at=0.0)
    quiet.start(now=1.0)
    assert capsys.readouterr().out == ""

    verbose = kiosk.KioskSession(state_changed_at=0.0, debug_transitions=True)
    verbose.start(now=1.0)

    assert "IDLE -> CAPTURING" in capsys.readouterr().out


def test_mobile_kiosk_submit_uses_unified_backend_endpoint():
    calls = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {
                "success": True,
                "action": "CHECK_IN",
                "employee_id": 1,
                "message": "Check-in completed successfully.",
            }

    class FakeClient:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return FakeResponse()

    success, payload = kiosk._submit_sequence(
        FakeClient(),
        api_base_url="http://127.0.0.1:55000",
        token="test-token",
        challenge="BLINK",
        frames=[b"frame"] * 8,
    )

    assert success is True
    assert payload["action"] == "CHECK_IN"
    assert calls[0][0].endswith("/attendance/live/attendance")
    assert calls[0][1]["data"] == {"challenge_type": "BLINK"}


def test_mobile_kiosk_renews_expired_authorization_and_retries_once():
    calls = []

    class FakeClient:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            request = httpx.Request("POST", url)
            if url.endswith("/auth/login"):
                return httpx.Response(
                    200,
                    json={"access_token": "renewed-token"},
                    request=request,
                )
            authorization = kwargs["headers"]["Authorization"]
            if authorization == "Bearer expired-token":
                return httpx.Response(
                    401,
                    json={"detail": "Could not validate credentials"},
                    request=request,
                )
            return httpx.Response(
                200,
                json={"success": True, "action": "CHECK_IN"},
                request=request,
            )

    authorization = kiosk.KioskAuthorization(
        email="admin@example.com",
        password="private-password",
        access_token="expired-token",
    )
    success, payload = kiosk._submit_sequence(
        FakeClient(),
        api_base_url="http://127.0.0.1:55000",
        authorization=authorization,
        challenge="TURN_HEAD_LEFT",
        frames=[b"frame"] * 8,
    )

    assert success is True
    assert payload["action"] == "CHECK_IN"
    assert authorization.current_token() == "renewed-token"
    assert [call[0].rsplit("/", 2)[-2:] for call in calls] == [
        ["live", "attendance"],
        ["auth", "login"],
        ["live", "attendance"],
    ]
    assert calls[-1][1]["headers"]["Authorization"] == "Bearer renewed-token"
    assert "private-password" not in repr(authorization)


def test_mobile_kiosk_does_not_renew_for_forbidden_response():
    calls = []

    class FakeClient:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(
                403,
                json={"detail": "Insufficient permissions"},
                request=httpx.Request("POST", url),
            )

    authorization = kiosk.KioskAuthorization(
        email="employee@example.com",
        password="private-password",
        access_token="valid-but-forbidden-token",
    )
    success, payload = kiosk._submit_sequence(
        FakeClient(),
        api_base_url="http://127.0.0.1:55000",
        authorization=authorization,
        challenge="TURN_HEAD_RIGHT",
        frames=[b"frame"] * 8,
    )

    assert success is False
    assert payload["error_title"] == "Terminal is not authorized"
    assert len(calls) == 1


def test_mobile_kiosk_clears_in_memory_authorization():
    authorization = kiosk.KioskAuthorization(
        email="admin@example.com",
        password="private-password",
        access_token="access-token",
    )

    authorization.clear()

    assert authorization.email == ""
    assert authorization.password == ""
    assert authorization.current_token() == ""


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ("No face was detected", "No face detected"),
        ("Multiple faces were detected", "Multiple people"),
        ("Liveness challenge failed", "Live verification failed"),
        (
            "Liveness verification failed. Please turn your head slightly left when prompted.",
            "Left turn was not detected",
        ),
        (
            "Liveness verification failed. Please turn your head slightly right when prompted.",
            "Right turn was not detected",
        ),
        ("No enrolled employee matched", "Face not recognized"),
        ("Recognized employee is inactive", "account is inactive"),
        ("Attendance already completed for today.", "already completed"),
    ],
)
def test_mobile_kiosk_maps_backend_failures_to_safe_messages(detail, expected):
    assert expected in kiosk._friendly_error(detail)


def test_mobile_kiosk_result_and_cooldown_settings_are_configurable(monkeypatch):
    monkeypatch.setenv("LIVE_ATTENDANCE_RESULT_DISPLAY_SECONDS", "5")
    monkeypatch.setenv("LIVE_ATTENDANCE_COOLDOWN_SECONDS", "2")

    assert kiosk._result_display_seconds() == 5.0
    assert kiosk._cooldown_seconds() == 2.0


def test_mobile_kiosk_ui_debug_mode_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("UI_DEBUG_MODE", raising=False)
    monkeypatch.delenv("LIVE_ATTENDANCE_UI_DEBUG_MODE", raising=False)

    assert kiosk._ui_debug_mode() is False


def test_mobile_kiosk_normal_preview_hides_face_detection_boxes(monkeypatch):
    monkeypatch.setenv("UI_DEBUG_MODE", "0")
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    monkeypatch.setattr(kiosk, "_preview_face_boxes", lambda _frame: [(50, 40, 100, 120)])

    preview, guidance = kiosk._annotate_preview_faces(frame)

    assert np.array_equal(preview, frame)
    assert guidance == "Face positioned correctly."


def test_mobile_kiosk_debug_preview_can_show_face_detection_boxes(monkeypatch):
    monkeypatch.setenv("UI_DEBUG_MODE", "1")
    frame = np.zeros((200, 200, 3), dtype=np.uint8)
    monkeypatch.setattr(kiosk, "_preview_face_boxes", lambda _frame: [(50, 40, 100, 120)])

    preview, _guidance = kiosk._annotate_preview_faces(frame)

    assert not np.array_equal(preview, frame)
