import cv2
import numpy as np
import pytest

from tools import live_mobile_attendance_kiosk as kiosk
from tools.kiosk_ui import (
    AttendanceKioskUI,
    KioskInteraction,
    Rect,
    calculate_kiosk_layout,
    format_display_time,
    format_status,
    place_frame_aspect_fit,
)


@pytest.mark.parametrize("width,height", [(1280, 720), (1366, 768), (1920, 1080)])
def test_kiosk_layout_keeps_cards_inside_common_widescreen_resolutions(width, height):
    layout = calculate_kiosk_layout(width, height)

    assert layout.canvas == Rect(0, 0, width, height)
    assert layout.camera_card.right < layout.information_card.left
    assert layout.camera_viewport.left > layout.camera_card.left
    assert layout.camera_viewport.right < layout.camera_card.right
    assert layout.body.top >= layout.header.bottom
    assert layout.body.bottom <= layout.footer.top
    assert layout.information_card.width >= 350


def test_kiosk_layout_rejects_unreadably_small_canvas():
    with pytest.raises(ValueError, match="at least 800x450"):
        calculate_kiosk_layout(640, 360)


def test_camera_frame_is_letterboxed_without_aspect_ratio_distortion():
    canvas = np.zeros((450, 800, 3), dtype=np.uint8)
    source = np.zeros((480, 640, 3), dtype=np.uint8)

    visible = place_frame_aspect_fit(canvas, source, Rect(0, 0, 800, 450))

    assert visible is not None
    assert visible.width == 600
    assert visible.height == 450
    assert visible.width / visible.height == pytest.approx(4 / 3)


@pytest.mark.parametrize(
    ("state", "expected_action"),
    [
        ("IDLE", "START"),
        ("CAPTURING", None),
        ("LIVENESS", None),
        ("RECOGNIZING", None),
        ("PROCESSING_ATTENDANCE", None),
        ("SUCCESS", None),
        ("ERROR", "RETRY"),
        ("COOLDOWN", None),
    ],
)
def test_each_kiosk_state_has_a_dedicated_safe_renderer(state, expected_action):
    ui = AttendanceKioskUI(width=1280, height=720)
    source = np.zeros((480, 640, 3), dtype=np.uint8)
    result = {
        "action": "CHECK_IN",
        "employee_name": "Employee One",
        "employee_number": "EMP001",
        "timestamp": "2026-08-23T08:03:00+02:00",
        "status": "PRESENT",
        "error_title": "No face detected",
    }

    rendered = ui.render(
        source,
        state=state,
        message="Please try again.",
        result=result,
        challenge="TURN_HEAD_LEFT",
        progress=0.5,
        state_age=1.0,
        now=1.0,
    )

    assert rendered.frame.shape == (720, 1280, 3)
    assert rendered.button_action == expected_action
    assert (rendered.button_bounds is not None) is (expected_action is not None)
    assert rendered.camera_content_bounds is not None


@pytest.mark.parametrize("state", ["PROCESSING_ATTENDANCE", "SUCCESS", "ERROR", "COOLDOWN"])
def test_camera_panel_keeps_the_valid_preview_visible_in_transient_states(state):
    ui = AttendanceKioskUI(width=1280, height=720)
    camera_color = np.asarray([45, 135, 225], dtype=np.uint8)
    source = np.full((480, 640, 3), camera_color, dtype=np.uint8)

    rendered = ui.render(
        source,
        state=state,
        message="Preparing for the next employee...",
        result={"message": "Completed", "recoverable": True},
        camera_available=True,
        state_age=1.0,
        now=1.0,
    )

    bounds = rendered.camera_content_bounds
    center_x, center_y = bounds.center
    assert np.array_equal(rendered.frame[center_y, center_x], camera_color)


def test_camera_unavailable_banner_does_not_replace_the_last_valid_preview():
    ui = AttendanceKioskUI(width=1280, height=720)
    camera_color = np.asarray([80, 160, 220], dtype=np.uint8)
    source = np.full((480, 640, 3), camera_color, dtype=np.uint8)

    rendered = ui.render(
        source,
        state="COOLDOWN",
        message="Please wait...",
        camera_available=False,
        state_age=1.0,
        now=1.0,
    )

    bounds = rendered.camera_content_bounds
    center_x, center_y = bounds.center
    assert np.array_equal(rendered.frame[center_y, center_x], camera_color)


def test_primary_kiosk_button_is_large_enough_for_touch_style_input():
    ui = AttendanceKioskUI(width=1280, height=720)
    rendered = ui.render(
        np.zeros((720, 1280, 3), dtype=np.uint8),
        state="IDLE",
        message="Ready for attendance.",
        state_age=1.0,
    )

    assert rendered.button_bounds is not None
    assert rendered.button_bounds.height >= 60
    assert rendered.button_bounds.width >= 300


def test_kiosk_interaction_tracks_hover_press_and_consumes_one_request():
    interaction = KioskInteraction(
        button_bounds=Rect(100, 100, 400, 180),
        button_enabled=True,
    )

    interaction.on_mouse(cv2.EVENT_MOUSEMOVE, 200, 140, 0, None)
    assert interaction.button_hovered is True

    interaction.on_mouse(cv2.EVENT_LBUTTONDOWN, 200, 140, 0, None)
    assert interaction.button_pressed is True
    assert interaction.consume_start() is True
    assert interaction.consume_start() is False

    interaction.on_mouse(cv2.EVENT_LBUTTONUP, 200, 140, 0, None)
    assert interaction.button_pressed is False


def test_success_renderer_handles_long_names_without_changing_response_data():
    ui = AttendanceKioskUI(width=1280, height=720)
    source = np.zeros((720, 1280, 3), dtype=np.uint8)
    employee_name = "A Very Long Employee Name Used Only For Safe Layout Verification"

    rendered = ui.render(
        source,
        state="SUCCESS",
        message="Check-in completed successfully.",
        result={
            "action": "CHECK_IN",
            "employee_name": employee_name,
            "employee_number": "EMP001",
            "timestamp": "2026-08-23T08:03:00+02:00",
            "status": "UNSCHEDULED",
        },
        state_age=1.0,
    )

    assert rendered.frame.shape == (720, 1280, 3)
    assert employee_name == "A Very Long Employee Name Used Only For Safe Layout Verification"


def test_employee_facing_status_and_time_formatters_hide_raw_enum_style():
    assert format_status("MISSING_CHECKOUT") == "Missing Checkout"
    assert format_status("UNSCHEDULED") == "Unscheduled"
    assert format_display_time("2026-08-23T19:45:16+02:00") == "07:45 PM"


def test_kiosk_environment_supports_presentation_fullscreen_and_resolution(monkeypatch):
    monkeypatch.setenv("LIVE_KIOSK_PRESENTATION_MODE", "false")
    monkeypatch.setenv("LIVE_KIOSK_FULLSCREEN", "true")
    monkeypatch.setenv("LIVE_KIOSK_WIDTH", "1920")
    monkeypatch.setenv("LIVE_KIOSK_HEIGHT", "1080")

    assert kiosk._presentation_mode() is False
    assert kiosk._fullscreen_setting() is True
    assert kiosk._kiosk_canvas_size() == (1920, 1080)


@pytest.mark.parametrize("fullscreen", [False, True])
def test_window_configuration_supports_normal_and_fullscreen_modes(monkeypatch, fullscreen):
    calls = []
    ui = AttendanceKioskUI(width=1280, height=720)
    monkeypatch.setattr(kiosk.cv2, "namedWindow", lambda *args: calls.append(("named", args)))
    monkeypatch.setattr(kiosk.cv2, "resizeWindow", lambda *args: calls.append(("resize", args)))
    monkeypatch.setattr(
        kiosk.cv2,
        "setWindowProperty",
        lambda *args: calls.append(("fullscreen", args)),
    )

    kiosk._configure_window(ui, fullscreen=fullscreen)

    assert calls[0][0] == "named"
    if fullscreen:
        assert any(call[0] == "fullscreen" for call in calls)
        assert not any(call[0] == "resize" for call in calls)
    else:
        assert any(call[0] == "resize" for call in calls)
        assert not any(call[0] == "fullscreen" for call in calls)


@pytest.mark.parametrize(
    ("detail", "category", "title"),
    [
        ("No face was detected", "NO_FACE", "No face detected"),
        ("Multiple faces were detected", "MULTIPLE_FACES", "More than one person detected"),
        ("Frame quality is too low", "POOR_FRAMES", "Unable to capture a clear image"),
        ("Liveness challenge failed", "LIVENESS", "Live verification failed"),
        ("No enrolled employee matched", "UNKNOWN_FACE", "Face not recognized"),
    ],
)
def test_backend_errors_map_to_stable_kiosk_presentations(detail, category, title):
    presentation = kiosk._friendly_error_details(detail)

    assert presentation["error_category"] == category
    assert presentation["error_title"] == title
    assert presentation["message"]


def test_camera_unavailable_state_renders_without_a_camera_frame():
    ui = AttendanceKioskUI(width=1280, height=720)

    rendered = ui.render(
        None,
        state="ERROR",
        message="Please check the camera connection and try again.",
        result={"error_title": "Camera unavailable"},
        camera_available=False,
        state_age=1.0,
    )

    assert rendered.frame.shape == (720, 1280, 3)
    assert rendered.button_action == "RETRY"
    assert rendered.camera_content_bounds is None


def test_nonrecoverable_policy_result_does_not_offer_misleading_retry_action():
    ui = AttendanceKioskUI(width=1280, height=720)

    rendered = ui.render(
        np.zeros((720, 1280, 3), dtype=np.uint8),
        state="ERROR",
        message="Attendance already completed for today.",
        result={
            "error_title": "Attendance already completed",
            "recoverable": False,
        },
        state_age=1.0,
    )

    assert rendered.button_action is None
    assert rendered.button_bounds is None
