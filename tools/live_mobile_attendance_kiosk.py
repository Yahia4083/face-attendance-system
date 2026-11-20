"""Single-action live camera terminal for liveness-gated attendance.

Usage:
    python tools/live_mobile_attendance_kiosk.py

Keyboard:
    SPACE = start attendance
    Q = quit
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from getpass import getpass
import math
import os
import random
from threading import Event, Lock, Thread
import time
from typing import Any

import cv2
import httpx
import numpy as np
from dotenv import load_dotenv

if __package__:
    from tools.kiosk_ui import (
        AttendanceKioskUI,
        ButtonBounds,
        KioskInteraction,
        KioskTheme,
    )
else:
    from kiosk_ui import AttendanceKioskUI, ButtonBounds, KioskInteraction, KioskTheme


WINDOW_NAME = "Live Mobile Attendance"
BACKEND_MIN_LIVE_FRAMES = 8
DEFAULT_WORKER_FRAME_COUNT = 12
DEFAULT_CAPTURE_SECONDS = 4.0
DEFAULT_RESULT_DISPLAY_SECONDS = 4.0
DEFAULT_COOLDOWN_SECONDS = 3.0
PROCESSING_MESSAGE_DELAY_SECONDS = 0.8
DEFAULT_CAMERA_RECOVERY_SECONDS = 2.0
DEFAULT_CAMERA_STALE_SECONDS = 2.0
_PREVIEW_FACE_CASCADE = None

# Compatibility aliases keep diagnostic face annotations tied to the shared theme.
KIOSK_SUCCESS = KioskTheme.SUCCESS
KIOSK_WARNING = KioskTheme.WARNING
KIOSK_DANGER = KioskTheme.ERROR

CHALLENGES = {
    "TURN_HEAD_LEFT": "Please turn your head slightly left",
    "TURN_HEAD_RIGHT": "Please turn your head slightly right",
}


class KioskState(StrEnum):
    IDLE = "IDLE"
    CAPTURING = "CAPTURING"
    LIVENESS = "LIVENESS"
    RECOGNIZING = "RECOGNIZING"
    PROCESSING_ATTENDANCE = "PROCESSING_ATTENDANCE"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    COOLDOWN = "COOLDOWN"


@dataclass
class KioskSession:
    state: KioskState = KioskState.IDLE
    message: str = "Ready for attendance."
    result: dict[str, Any] | None = None
    state_changed_at: float = 0.0
    debug_transitions: bool = False

    @property
    def can_start(self) -> bool:
        return self.state == KioskState.IDLE

    def transition(
        self,
        state: KioskState,
        message: str,
        *,
        now: float,
        result: dict[str, Any] | None = None,
    ) -> None:
        previous_state = self.state
        self.state = state
        self.message = message
        self.result = result
        self.state_changed_at = now
        if self.debug_transitions and previous_state != state:
            print(f"[kiosk] {previous_state.value} -> {state.value}")

    def start(self, *, now: float) -> bool:
        if not self.can_start:
            return False
        self.transition(
            KioskState.CAPTURING,
            "Starting verification...",
            now=now,
        )
        return True

    def finish(self, *, success: bool, result: dict[str, Any], now: float) -> None:
        self.transition(
            KioskState.SUCCESS if success else KioskState.ERROR,
            str(result.get("message") or "Attendance request completed."),
            now=now,
            result=result,
        )

    def advance(
        self,
        *,
        now: float,
        result_display_seconds: float,
        cooldown_seconds: float,
        request_in_progress: bool,
    ) -> None:
        elapsed = now - self.state_changed_at
        if (
            request_in_progress
            and self.state == KioskState.RECOGNIZING
            and elapsed >= PROCESSING_MESSAGE_DELAY_SECONDS
        ):
            self.transition(
                KioskState.PROCESSING_ATTENDANCE,
                "Recording attendance...",
                now=now,
            )
        if self.state in {KioskState.SUCCESS, KioskState.ERROR} and elapsed >= result_display_seconds:
            # Anchor cooldown to the result deadline so a delayed UI iteration can catch up.
            cooldown_started_at = self.state_changed_at + result_display_seconds
            self.transition(
                KioskState.COOLDOWN,
                "Please wait...",
                now=cooldown_started_at,
                result=self.result,
            )
        if self.state == KioskState.COOLDOWN and now - self.state_changed_at >= cooldown_seconds:
            self.transition(
                KioskState.IDLE,
                "Ready for attendance.",
                now=now,
            )


@dataclass
class AttendanceAttemptRuntime:
    """Own transient resources for exactly one attendance attempt."""

    request_future: Future | None = None
    challenge: str | None = None
    processing: bool = False

    @property
    def request_in_progress(self) -> bool:
        return self.processing and self.request_future is not None

    def begin(self) -> None:
        self.clear()
        self.processing = True

    def attach_request(self, request_future: Future, *, challenge: str) -> None:
        self.request_future = request_future
        self.challenge = challenge
        self.processing = True

    def clear(self) -> None:
        self.request_future = None
        self.challenge = None
        self.processing = False


@dataclass(repr=False)
class KioskAuthorization:
    """Keep terminal credentials in memory for automatic access-token renewal."""

    email: str
    password: str
    access_token: str
    _renewal_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def current_token(self) -> str:
        with self._renewal_lock:
            return self.access_token

    def renew(
        self,
        client: httpx.Client,
        api_base_url: str,
        *,
        failed_token: str,
    ) -> str:
        # Restores terminal authorization after its access token expires.
        with self._renewal_lock:
            if self.access_token != failed_token:
                return self.access_token
            self.access_token = _request_access_token(
                client,
                api_base_url,
                email=self.email,
                password=self.password,
            )
            return self.access_token

    def clear(self) -> None:
        # Drops terminal credentials when the kiosk process exits.
        with self._renewal_lock:
            self.email = ""
            self.password = ""
            self.access_token = ""


@dataclass
class CameraPreviewState:
    """Keep the last valid oriented frame available across transient read failures."""

    latest_frame: np.ndarray | None = None
    consecutive_failures: int = 0
    camera_available: bool = True

    def accept(self, frame: np.ndarray) -> np.ndarray:
        self.latest_frame = frame.copy()
        self.consecutive_failures = 0
        self.camera_available = True
        return self.latest_frame

    def reject(self, *, unavailable_after: int) -> np.ndarray | None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= unavailable_after:
            self.camera_available = False
        return self.latest_frame

    def reconnecting(self) -> None:
        self.camera_available = False

    def reopened(self) -> None:
        self.consecutive_failures = 0
        self.camera_available = True


@dataclass(frozen=True)
class CameraFrameSnapshot:
    frame: np.ndarray | None
    sequence: int
    camera_available: bool
    consecutive_failures: int


class CameraFrameReader:
    """Own VideoCapture reads so a blocked camera driver cannot freeze the UI loop."""

    def __init__(
        self,
        capture,
        *,
        rotate: int,
        flip: bool,
        unavailable_after: int,
        stale_after_seconds: float,
        debug: bool = False,
    ) -> None:
        self._capture = capture
        self._rotate = rotate
        self._flip = flip
        self._unavailable_after = unavailable_after
        self._stale_after_seconds = stale_after_seconds
        self._debug = debug
        self._lock = Lock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._preview = CameraPreviewState(camera_available=True)
        self._sequence = 0
        self._started_at = time.monotonic()
        self._last_success_at: float | None = None
        self._closed = False

    def start(self) -> "CameraFrameReader":
        if self._thread is None:
            self._thread = Thread(target=self._run, name="kiosk-camera-reader", daemon=True)
            self._thread.start()
        return self

    def snapshot(self, *, now: float | None = None) -> CameraFrameSnapshot:
        now = time.monotonic() if now is None else now
        with self._lock:
            frame = self._preview.latest_frame
            sequence = self._sequence
            failures = self._preview.consecutive_failures
            available = self._preview.camera_available and not self._closed
            last_success_at = self._last_success_at
            started_at = self._started_at

        freshness_origin = last_success_at if last_success_at is not None else started_at
        if now - freshness_origin >= self._stale_after_seconds:
            available = False
        return CameraFrameSnapshot(
            frame=frame,
            sequence=sequence,
            camera_available=available,
            consecutive_failures=failures,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        with self._lock:
            self._preview.camera_available = False

        # Releasing the capture is what normally unblocks a driver stalled in read().
        self._capture.release()
        if self._thread is not None:
            self._thread.join(timeout=0.75)
            if self._thread.is_alive() and self._debug:
                print("[kiosk] Camera reader did not stop before the recovery timeout.")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                ok, frame = self._capture.read()
            except Exception:
                ok, frame = False, None

            if self._stop.is_set():
                break
            now = time.monotonic()
            if not _camera_frame_has_signal(ok, frame):
                with self._lock:
                    self._preview.reject(unavailable_after=self._unavailable_after)
                time.sleep(0.01)
                continue

            prepared = _prepare_frame(frame, rotate=self._rotate, flip=self._flip)
            with self._lock:
                self._preview.accept(prepared)
                self._sequence += 1
                self._last_success_at = now


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _int_env(name: str, default: int) -> int:
    raw_value = _env(name, str(default))
    try:
        return int(raw_value)
    except ValueError:
        raise ValueError(f"{name} must be a whole number.") from None


def _float_env(name: str, default: float) -> float:
    raw_value = _env(name, str(default))
    try:
        return float(raw_value)
    except ValueError:
        raise ValueError(f"{name} must be a number.") from None


def _camera_source() -> int | str:
    source = os.getenv("MOBILE_CAMERA_SOURCE")
    if source is None or not source.strip():
        stream_url = os.getenv("MOBILE_CAMERA_STREAM_URL")
        source = stream_url if stream_url and stream_url.strip() else "0"

    source = source.strip()
    if source.isdigit():
        return int(source)
    return source


def _rotation_setting() -> int:
    raw_value = os.getenv("LIVE_CAMERA_ROTATE", "0").strip()
    try:
        rotate = int(raw_value)
    except ValueError:
        raise ValueError("LIVE_CAMERA_ROTATE must be one of 0, 90, -90, or 180.") from None

    if rotate not in {0, 90, -90, 180}:
        raise ValueError("LIVE_CAMERA_ROTATE must be one of 0, 90, -90, or 180.")
    return rotate


def _flip_setting() -> bool:
    return os.getenv("LIVE_CAMERA_FLIP", "0").strip().lower() in {"1", "true", "yes", "on"}


def _backend_min_frame_requirement() -> int:
    return BACKEND_MIN_LIVE_FRAMES


def _requested_worker_frame_count() -> int:
    frame_count = _int_env("LIVE_ATTENDANCE_WORKER_FRAME_COUNT", DEFAULT_WORKER_FRAME_COUNT)
    if frame_count <= 0:
        raise ValueError("LIVE_ATTENDANCE_WORKER_FRAME_COUNT must be greater than 0.")
    return frame_count


def _worker_frame_count(*, minimum: int | None = None) -> int:
    minimum = minimum or _backend_min_frame_requirement()
    return max(_requested_worker_frame_count(), minimum)


def _capture_seconds() -> float:
    seconds = _float_env("LIVE_ATTENDANCE_WORKER_CAPTURE_SECONDS", DEFAULT_CAPTURE_SECONDS)
    if seconds <= 0:
        raise ValueError("LIVE_ATTENDANCE_WORKER_CAPTURE_SECONDS must be greater than 0.")
    return seconds


def _result_display_seconds() -> float:
    seconds = _float_env(
        "LIVE_ATTENDANCE_RESULT_DISPLAY_SECONDS",
        DEFAULT_RESULT_DISPLAY_SECONDS,
    )
    if seconds <= 0:
        raise ValueError("LIVE_ATTENDANCE_RESULT_DISPLAY_SECONDS must be greater than 0.")
    return seconds


def _cooldown_seconds() -> float:
    seconds = _float_env("LIVE_ATTENDANCE_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS)
    if seconds < 0:
        raise ValueError("LIVE_ATTENDANCE_COOLDOWN_SECONDS must be 0 or greater.")
    return seconds


def _camera_recovery_seconds() -> float:
    seconds = _float_env("LIVE_CAMERA_RECOVERY_SECONDS", DEFAULT_CAMERA_RECOVERY_SECONDS)
    if seconds <= 0:
        raise ValueError("LIVE_CAMERA_RECOVERY_SECONDS must be greater than 0.")
    return seconds


def _camera_stale_seconds() -> float:
    seconds = _float_env("LIVE_CAMERA_STALE_SECONDS", DEFAULT_CAMERA_STALE_SECONDS)
    if seconds <= 0:
        raise ValueError("LIVE_CAMERA_STALE_SECONDS must be greater than 0.")
    return seconds


def _sound_enabled() -> bool:
    return os.getenv("LIVE_ATTENDANCE_SOUND_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _play_feedback(*, success: bool) -> None:
    if not _sound_enabled() or os.name != "nt":
        return
    try:
        import winsound

        sound = winsound.MB_ICONASTERISK if success else winsound.MB_ICONHAND
        winsound.MessageBeep(sound)
    except (ImportError, RuntimeError):
        return


def _prepare_frame(frame, *, rotate: int | None = None, flip: bool | None = None):
    if rotate is None:
        rotate = _rotation_setting()
    if flip is None:
        flip = _flip_setting()

    if rotate == 90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif rotate == -90:
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    elif rotate == 180:
        frame = cv2.rotate(frame, cv2.ROTATE_180)

    if flip:
        frame = cv2.flip(frame, 1)

    return frame


def _camera_frame_has_signal(ok: bool, frame) -> bool:
    """Accept only a real camera image, not an empty virtual-camera holding frame."""

    if not ok or frame is None or getattr(frame, "size", 0) <= 0:
        return False
    if np.count_nonzero(frame) <= 0:
        return False

    # Virtual cameras such as Camo can remain open while emitting a nearly uniform
    # grey waiting screen. Sampling keeps this check inexpensive in the reader loop.
    sample = frame[::16, ::16]
    if sample.size <= 0:
        return False
    if sample.ndim == 3:
        sample = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
    if sample.size < 16:
        return True
    histogram = np.bincount(sample.reshape(-1), minlength=256)
    dominant_luma_ratio = float(histogram.max()) / float(sample.size)
    return bool(float(np.std(sample)) >= 2.0 and dominant_luma_ratio < 0.92)


def _open_camera(camera_source: int | str):
    if isinstance(camera_source, int):
        if os.name == "nt":
            # Some Windows virtual cameras work with DirectShow while physical USB
            # cameras may only expose frames through Media Foundation.
            last_capture = None
            for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF):
                capture = cv2.VideoCapture(camera_source, backend)
                if capture.isOpened():
                    return capture
                capture.release()
                last_capture = capture
            return last_capture
        return cv2.VideoCapture(camera_source)
    return cv2.VideoCapture(camera_source)


def _recover_camera(camera_source: int | str, *, debug: bool = False):
    """Attempt one camera reopen without entering a nested UI loop."""

    capture = _open_camera(camera_source)
    if capture.isOpened():
        if debug:
            print("[kiosk] Camera recovery succeeded.")
        return capture

    capture.release()
    if debug:
        print("[kiosk] Camera recovery attempt failed.")
    return None


def _start_camera_reader(
    capture,
    *,
    rotate: int,
    flip: bool,
    unavailable_after: int,
    stale_after_seconds: float,
    debug: bool,
) -> CameraFrameReader:
    return CameraFrameReader(
        capture,
        rotate=rotate,
        flip=flip,
        unavailable_after=unavailable_after,
        stale_after_seconds=stale_after_seconds,
        debug=debug,
    ).start()


def _camera_open_error(camera_source: int | str) -> str:
    message = "Could not open camera source. Check MOBILE_CAMERA_SOURCE or MOBILE_CAMERA_STREAM_URL."
    if isinstance(camera_source, int):
        return (
            f"{message} Try MOBILE_CAMERA_SOURCE=0, 1, or 2 after checking available "
            "cameras with OpenCV."
        )
    return f"{message} If this is a URL, check that it opens in VLC or a browser first."


def _face_thresholds() -> tuple[float, float, float]:
    return (
        _float_env("LIVE_FACE_MIN_AREA_RATIO", 0.03),
        _float_env("LIVE_FACE_MAX_CENTER_DISTANCE_RATIO", 0.45),
        _float_env("LIVE_FACE_DOMINANCE_RATIO", 2.5),
    )


def _debug_ignored_faces() -> bool:
    return os.getenv("LIVE_CAMERA_DEBUG_FACES", "0").strip().lower() in {"1", "true", "yes", "on"}


def _ui_debug_mode() -> bool:
    raw_value = os.getenv(
        "LIVE_KIOSK_DEBUG",
        os.getenv(
            "UI_DEBUG_MODE",
            os.getenv("LIVE_ATTENDANCE_UI_DEBUG_MODE", "0"),
        ),
    )
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _presentation_mode() -> bool:
    return os.getenv("LIVE_KIOSK_PRESENTATION_MODE", "1").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _fullscreen_setting() -> bool:
    return os.getenv("LIVE_KIOSK_FULLSCREEN", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _kiosk_canvas_size() -> tuple[int, int]:
    width = _int_env("LIVE_KIOSK_WIDTH", 1280)
    height = _int_env("LIVE_KIOSK_HEIGHT", 720)
    if width < 800 or height < 450:
        raise ValueError("LIVE_KIOSK_WIDTH and LIVE_KIOSK_HEIGHT must define at least 800x450.")
    return width, height


def _kiosk_brand() -> str:
    return _env("LIVE_KIOSK_BRAND", "Face Attendance") or "Face Attendance"


def _preview_face_cascade():
    global _PREVIEW_FACE_CASCADE
    if _PREVIEW_FACE_CASCADE is not None:
        return _PREVIEW_FACE_CASCADE

    cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        return None
    _PREVIEW_FACE_CASCADE = cascade
    return cascade


def _preview_face_boxes(frame) -> list[tuple[int, int, int, int]]:
    cascade = _preview_face_cascade()
    if cascade is None:
        return []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    boxes = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(36, 36))
    return [tuple(int(value) for value in box) for box in boxes]


def _filter_preview_faces(
    boxes: list[tuple[int, int, int, int]],
    frame_shape,
) -> tuple[tuple[int, int, int, int] | None, list[tuple[int, int, int, int]], list[tuple[int, int, int, int]]]:
    if not boxes:
        return None, [], []

    min_area_ratio, max_center_distance_ratio, dominance_ratio = _face_thresholds()
    frame_height, frame_width = frame_shape[:2]
    frame_area = max(1.0, float(frame_width * frame_height))
    half_diagonal = max(1.0, math.hypot(frame_width, frame_height) / 2.0)
    center_x = frame_width / 2.0
    center_y = frame_height / 2.0

    significant: list[tuple[tuple[int, int, int, int], float]] = []
    ignored: list[tuple[int, int, int, int]] = []
    for box in boxes:
        x, y, width, height = box
        area = float(max(0, width) * max(0, height))
        area_ratio = area / frame_area
        face_center_x = x + (width / 2.0)
        face_center_y = y + (height / 2.0)
        center_distance_ratio = math.hypot(face_center_x - center_x, face_center_y - center_y) / half_diagonal
        if area_ratio >= min_area_ratio and center_distance_ratio <= max_center_distance_ratio:
            significant.append((box, area))
        else:
            ignored.append(box)

    if not significant:
        return None, [], ignored

    significant.sort(key=lambda item: item[1], reverse=True)
    if len(significant) == 1:
        return significant[0][0], [significant[0][0]], ignored

    primary, primary_area = significant[0]
    _, secondary_area = significant[1]
    if primary_area / max(secondary_area, 1.0) >= dominance_ratio:
        return primary, [primary], [box for box, _ in significant[1:]] + ignored
    return None, [box for box, _ in significant], ignored


def _annotate_preview_faces(frame):
    output = frame.copy()
    boxes = _preview_face_boxes(output)
    primary, significant, ignored = _filter_preview_faces(boxes, output.shape)

    # Normal presentation mode uses friendly guidance only; boxes are reserved for diagnostics.
    if _ui_debug_mode() and (_debug_ignored_faces() or ignored):
        for x, y, width, height in ignored:
            cv2.rectangle(output, (x, y), (x + width, y + height), KIOSK_WARNING, 1)

    if primary is not None:
        if _ui_debug_mode():
            x, y, width, height = primary
            cv2.rectangle(output, (x, y), (x + width, y + height), KIOSK_SUCCESS, 2)
        return output, "Face positioned correctly."

    if _ui_debug_mode():
        for x, y, width, height in significant:
            cv2.rectangle(output, (x, y), (x + width, y + height), KIOSK_DANGER, 2)

    if significant:
        return output, "Multiple foreground faces detected. Keep only one person close to the camera."
    return output, "Stand close to the camera and keep your face centered."


def _render_with_ui(
    ui: AttendanceKioskUI,
    frame,
    session: KioskSession,
    *,
    interaction: KioskInteraction | None = None,
    face_guidance: str | None = None,
    challenge: str | None = None,
    progress: float | None = None,
    camera_available: bool = True,
):
    interaction = interaction or KioskInteraction()
    rendered = ui.render(
        frame,
        state=session.state,
        message=session.message,
        result=session.result,
        face_guidance=face_guidance,
        challenge=challenge,
        progress=progress,
        button_hovered=interaction.button_hovered,
        button_pressed=interaction.button_pressed,
        state_age=max(0.0, time.monotonic() - session.state_changed_at),
        camera_available=camera_available,
    )
    return rendered.frame, rendered.button_bounds


def _primary_action_available(
    session: KioskSession,
    attempt: AttendanceAttemptRuntime,
    *,
    button_bounds: ButtonBounds | None,
    camera_available: bool,
) -> bool:
    """Expose the kiosk action only when no prior attempt still owns the terminal."""

    return bool(
        button_bounds is not None
        and session.state in {KioskState.IDLE, KioskState.ERROR}
        and not attempt.processing
        and camera_available
    )


def _release_interaction_lock(interaction: KioskInteraction) -> None:
    interaction.button_enabled = False
    interaction.button_bounds = None
    interaction.start_requested = False
    interaction.button_pressed = False


def _render_kiosk_frame(
    frame,
    session: KioskSession,
    *,
    face_guidance: str | None = None,
):
    """Compatibility renderer used by deterministic tests and external helpers."""

    height, width = frame.shape[:2]
    ui = AttendanceKioskUI(
        width=max(800, width),
        height=max(450, height),
        brand=_kiosk_brand(),
        presentation_mode=_presentation_mode(),
        debug_mode=_ui_debug_mode(),
    )
    source = frame
    if source.shape[1] != width or source.shape[0] != height:
        source = cv2.resize(source, (width, height), interpolation=cv2.INTER_AREA)
    return _render_with_ui(ui, source, session, face_guidance=face_guidance)

def _request_access_token(
    client: httpx.Client,
    api_base_url: str,
    *,
    email: str,
    password: str,
) -> str:
    response = client.post(
        f"{api_base_url}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise ValueError("Login response did not contain an access token.")
    return token


def _login(client: httpx.Client, api_base_url: str) -> KioskAuthorization:
    default_email = (
        os.getenv("LIVE_ATTENDANCE_ADMIN_EMAIL")
        or os.getenv("ADMIN_EMAIL")
        or "admin@example.com"
    )
    email = input(f"Admin email [{default_email}]: ").strip() or default_email
    password = getpass("Admin password: ")
    token = _request_access_token(
        client,
        api_base_url,
        email=email,
        password=password,
    )
    return KioskAuthorization(email=email, password=password, access_token=token)


def _capture_sequence(
    camera_reader: CameraFrameReader,
    *,
    ui: AttendanceKioskUI,
    session: KioskSession,
    interaction: KioskInteraction,
    frame_count: int,
    seconds: float,
    challenge: str,
):
    frames: list[bytes] = []
    start = time.monotonic()
    interval = max(0.05, seconds / max(1, frame_count))
    next_sample = start
    last_sampled_sequence = -1

    while len(frames) < frame_count and time.monotonic() - start <= seconds + 1.0:
        now = time.monotonic()
        snapshot = camera_reader.snapshot(now=now)
        frame = snapshot.frame
        face_guidance = None
        preview_frame = frame
        if frame is not None and snapshot.camera_available:
            preview_frame, face_guidance = _annotate_preview_faces(frame)
        preview, _button_bounds = _render_with_ui(
            ui,
            preview_frame,
            session,
            interaction=interaction,
            face_guidance=face_guidance,
            challenge=challenge,
            progress=len(frames) / max(1, frame_count),
            camera_available=snapshot.camera_available,
        )
        cv2.imshow(WINDOW_NAME, preview)
        cv2.waitKey(1 if snapshot.camera_available else 10)

        if (
            now >= next_sample
            and frame is not None
            and snapshot.camera_available
            and snapshot.sequence != last_sampled_sequence
        ):
            encoded_ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            if encoded_ok:
                frames.append(buffer.tobytes())
                last_sampled_sequence = snapshot.sequence
            next_sample = now + interval

    return frames


def _submit_sequence(
    client: httpx.Client,
    *,
    api_base_url: str,
    token: str | None = None,
    authorization: KioskAuthorization | None = None,
    challenge: str,
    frames: list[bytes],
):
    files = [
        ("frames", (f"live_frame_{index:03d}.jpg", content, "image/jpeg"))
        for index, content in enumerate(frames, start=1)
    ]
    request_token = authorization.current_token() if authorization is not None else token
    if not request_token:
        return False, _error_payload(
            "AUTHORIZATION",
            "Terminal is not authorized",
            "Please restart the terminal and sign in as an administrator.",
            recoverable=False,
        )

    def submit(access_token: str):
        return client.post(
            f"{api_base_url}/attendance/live/attendance",
            headers={"Authorization": f"Bearer {access_token}"},
            data={"challenge_type": challenge},
            files=files,
            timeout=120,
        )

    try:
        response = submit(request_token)
    except httpx.RequestError:
        return False, _error_payload(
            "BACKEND_UNAVAILABLE",
            "Attendance service unavailable",
            "Please try again shortly.",
        )

    if response.status_code == 401 and authorization is not None:
        try:
            request_token = authorization.renew(
                client,
                api_base_url,
                failed_token=request_token,
            )
        except httpx.RequestError:
            return False, _error_payload(
                "BACKEND_UNAVAILABLE",
                "Attendance service unavailable",
                "Please try again shortly.",
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return False, _error_payload(
                "AUTHORIZATION",
                "Terminal re-authorization failed",
                "Please contact an administrator to restart and authorize the terminal.",
                recoverable=False,
            )
        try:
            response = submit(request_token)
        except httpx.RequestError:
            return False, _error_payload(
                "BACKEND_UNAVAILABLE",
                "Attendance service unavailable",
                "Please try again shortly.",
            )

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "Live attendance request failed.")
        except ValueError:
            detail = "Live attendance request failed."
        return False, _friendly_error_details(detail, response.status_code)
    return True, response.json()


def _friendly_error(detail: object, status_code: int | None = None) -> str:
    presentation = _friendly_error_details(detail, status_code)
    return f"{presentation['error_title']}. {presentation['message']}"


def _error_payload(
    category: str,
    title: str,
    message: str,
    *,
    recoverable: bool = True,
) -> dict[str, Any]:
    return {
        "error_category": category,
        "error_title": title,
        "message": message,
        "recoverable": recoverable,
    }


def _friendly_error_details(detail: object, status_code: int | None = None) -> dict[str, Any]:
    if status_code == 401:
        return _error_payload(
            "AUTHORIZATION",
            "Terminal authorization expired",
            "Please contact an administrator to restart and authorize the terminal.",
            recoverable=False,
        )
    if status_code == 403:
        return _error_payload(
            "AUTHORIZATION",
            "Terminal is not authorized",
            "The signed-in account cannot use live attendance. Please contact an administrator.",
            recoverable=False,
        )
    if status_code is not None and status_code >= 500:
        return _error_payload(
            "BACKEND_UNAVAILABLE",
            "Attendance service unavailable",
            "Please try again shortly.",
        )
    if not isinstance(detail, str):
        return _error_payload(
            "INVALID_REQUEST",
            "Attendance not recorded",
            "The attendance request was invalid. Please try again.",
        )

    normalized = detail.lower()
    if "multiple" in normalized and "face" in normalized:
        return _error_payload(
            "MULTIPLE_FACES",
            "More than one person detected",
            "Multiple people are too close to the camera. Keep only one person in front of the device.",
        )
    if "no face" in normalized:
        return _error_payload(
            "NO_FACE",
            "No face detected",
            "Please move closer, face the camera, and try again.",
        )
    if (
        "liveness" in normalized
        or "static" in normalized
        or "challenge" in normalized
    ):
        if "turn your head slightly left" in normalized:
            return _error_payload(
                "LIVENESS",
                "Left turn was not detected",
                "Start facing the camera, then turn your head slightly left and hold briefly.",
            )
        if "turn your head slightly right" in normalized:
            return _error_payload(
                "LIVENESS",
                "Right turn was not detected",
                "Start facing the camera, then turn your head slightly right and hold briefly.",
            )
        return _error_payload(
            "LIVENESS",
            "Live verification failed",
            "Start facing the camera, then follow the displayed movement and try again.",
        )
    if (
        "clear frame" in normalized
        or "frame quality" in normalized
        or "image quality" in normalized
        or "blur" in normalized
    ):
        return _error_payload(
            "POOR_FRAMES",
            "Unable to capture a clear image",
            "Please keep still, look directly at the camera, and try again.",
        )
    if "no enrolled employee" in normalized or "no match" in normalized:
        return _error_payload(
            "UNKNOWN_FACE",
            "Face not recognized",
            "Please contact an administrator if the issue continues.",
        )
    if "ambiguous" in normalized:
        return _error_payload(
            "UNCLEAR_IDENTITY",
            "Identity could not be confirmed",
            "Keep one face centered and try again.",
        )
    if "inactive" in normalized:
        return _error_payload(
            "INACTIVE_EMPLOYEE",
            "Employee account inactive",
            "This employee account is inactive. Please contact an administrator.",
            recoverable=False,
        )
    if "already completed" in normalized:
        return _error_payload(
            "ATTENDANCE_COMPLETED",
            "Attendance already completed",
            "Attendance already completed for today.",
            recoverable=False,
        )
    if "no effective schedule" in normalized:
        return _error_payload(
            "NO_SCHEDULE",
            "Attendance not permitted",
            "No active schedule permits attendance at this time.",
            recoverable=False,
        )
    return _error_payload(
        "ATTENDANCE_REJECTED",
        "Attendance not recorded",
        detail.strip() or "Attendance could not be recorded. Please try again.",
    )


def _consume_completed_request(
    attempt: AttendanceAttemptRuntime,
) -> tuple[bool, dict[str, Any]] | None:
    """Consume a completed worker result and always release its transient lock."""

    request_future = attempt.request_future
    if request_future is None or not request_future.done():
        return None

    try:
        success, result = request_future.result()
        if not isinstance(result, dict):
            raise ValueError("Attendance worker returned an invalid result.")
        return bool(success), result
    except Exception:
        return False, _error_payload(
            "BACKEND_UNAVAILABLE",
            "Attendance service unavailable",
            "Please try again shortly.",
        )
    finally:
        attempt.clear()


def _configure_window(ui: AttendanceKioskUI, *, fullscreen: bool) -> None:
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    if fullscreen:
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    else:
        cv2.resizeWindow(WINDOW_NAME, ui.width, ui.height)


def _open_camera_with_feedback(
    camera_source: int | str,
    *,
    ui: AttendanceKioskUI,
    interaction: KioskInteraction,
):
    """Open or reconnect the camera while keeping a professional error screen visible."""

    error_message = _camera_open_error(camera_source)
    capture = _open_camera(camera_source)
    if capture.isOpened():
        return capture

    print(error_message)
    session = KioskSession(
        state=KioskState.ERROR,
        message="Please check the camera connection and try again.",
        result=_error_payload(
            "CAMERA_UNAVAILABLE",
            "Camera unavailable",
            "Please check the camera connection and try again.",
        ),
        state_changed_at=time.monotonic(),
    )
    placeholder = None
    while True:
        preview, button_bounds = _render_with_ui(
            ui,
            placeholder,
            session,
            interaction=interaction,
            camera_available=False,
        )
        interaction.button_bounds = button_bounds
        interaction.button_enabled = button_bounds is not None
        cv2.imshow(WINDOW_NAME, preview)
        key = cv2.waitKey(30) & 0xFF
        if key in {ord("q"), ord("Q")}:
            capture.release()
            return None
        if key == ord(" "):
            interaction.request_start()
        if not interaction.consume_start():
            continue

        session.transition(
            KioskState.CAPTURING,
            "Reconnecting camera...",
            now=time.monotonic(),
        )
        reconnecting, _bounds = _render_with_ui(
            ui,
            placeholder,
            session,
            interaction=interaction,
            camera_available=False,
        )
        cv2.imshow(WINDOW_NAME, reconnecting)
        cv2.waitKey(80)
        capture.release()
        capture = _open_camera(camera_source)
        if capture.isOpened():
            interaction.button_enabled = False
            interaction.button_bounds = None
            return capture
        session.transition(
            KioskState.ERROR,
            "Please check the camera connection and try again.",
            now=time.monotonic(),
            result=_error_payload(
                "CAMERA_UNAVAILABLE",
                "Camera unavailable",
                "Please check the camera connection and try again.",
            ),
        )


def main() -> None:
    load_dotenv()
    camera_source = _camera_source()
    api_base_url = _env("LIVE_ATTENDANCE_API_BASE_URL", "http://127.0.0.1:55000").rstrip("/")
    backend_min_frames = _backend_min_frame_requirement()
    requested_frame_count = _requested_worker_frame_count()
    frame_count = _worker_frame_count(minimum=backend_min_frames)
    capture_seconds = _capture_seconds()
    result_display_seconds = _result_display_seconds()
    cooldown_seconds = _cooldown_seconds()
    camera_recovery_seconds = _camera_recovery_seconds()
    camera_stale_seconds = _camera_stale_seconds()
    max_read_failures = max(3, _int_env("LIVE_CAMERA_MAX_READ_FAILURES", 30))
    rotate = _rotation_setting()
    flip = _flip_setting()
    canvas_width, canvas_height = _kiosk_canvas_size()
    fullscreen = _fullscreen_setting()
    presentation_mode = _presentation_mode()
    debug_mode = _ui_debug_mode()
    ui = AttendanceKioskUI(
        width=canvas_width,
        height=canvas_height,
        brand=_kiosk_brand(),
        presentation_mode=presentation_mode,
        debug_mode=debug_mode,
    )

    print(f"Opening camera source: {camera_source}")
    print(f"API base URL: {api_base_url}")
    if requested_frame_count < backend_min_frames:
        print(
            f"Requested frame count {requested_frame_count} is below the backend minimum; "
            f"using {backend_min_frames}."
        )
    print(f"Frame count: {frame_count}")
    print(f"Capture seconds: {capture_seconds}")
    print(f"Backend minimum live frames: {backend_min_frames}")
    print(f"Rotation: {rotate}")
    print(f"Flip: {str(flip).lower()}")
    print(f"Result display seconds: {result_display_seconds}")
    print(f"Cooldown seconds: {cooldown_seconds}")
    print(f"Camera recovery seconds: {camera_recovery_seconds}")
    print(f"Camera stale seconds: {camera_stale_seconds}")
    print(f"Sound: {str(_sound_enabled()).lower()}")
    print(f"Canvas: {canvas_width}x{canvas_height}")
    print(f"Fullscreen: {str(fullscreen).lower()}")
    print(f"Presentation mode: {str(presentation_mode).lower()}")
    print(f"UI debug mode: {str(debug_mode).lower()}")

    interaction = KioskInteraction()
    _configure_window(ui, fullscreen=fullscreen)
    cv2.setMouseCallback(WINDOW_NAME, interaction.on_mouse)
    capture = _open_camera_with_feedback(
        camera_source,
        ui=ui,
        interaction=interaction,
    )
    if capture is None:
        cv2.destroyAllWindows()
        return

    attempt = AttendanceAttemptRuntime()
    camera_reader = _start_camera_reader(
        capture,
        rotate=rotate,
        flip=flip,
        unavailable_after=max_read_failures,
        stale_after_seconds=camera_stale_seconds,
        debug=debug_mode,
    )
    capture = None
    authorization: KioskAuthorization | None = None
    try:
        with httpx.Client() as client, ThreadPoolExecutor(max_workers=1) as executor:
            authorization = _login(client, api_base_url)
            session = KioskSession(
                state_changed_at=time.monotonic(),
                debug_transitions=debug_mode,
            )
            next_camera_recovery_at = 0.0
            last_preview_frame = None

            while True:
                now = time.monotonic()
                completed_request = _consume_completed_request(attempt)
                if completed_request is not None:
                    success, result = completed_request
                    session.finish(success=success, result=result, now=now)
                    _play_feedback(success=success)

                previous_state = session.state
                session.advance(
                    now=now,
                    result_display_seconds=result_display_seconds,
                    cooldown_seconds=cooldown_seconds,
                    request_in_progress=attempt.request_in_progress,
                )
                if previous_state != KioskState.IDLE and session.state == KioskState.IDLE:
                    attempt.clear()
                    _release_interaction_lock(interaction)

                snapshot = (
                    camera_reader.snapshot(now=now)
                    if camera_reader is not None
                    else CameraFrameSnapshot(
                        frame=None,
                        sequence=0,
                        camera_available=False,
                        consecutive_failures=max_read_failures,
                    )
                )
                if snapshot.frame is not None:
                    last_preview_frame = snapshot.frame

                if camera_reader is not None and not snapshot.camera_available:
                    if debug_mode:
                        print(
                            "[kiosk] Camera frames became stale or unavailable; "
                            "scheduling controlled recovery."
                        )
                    camera_reader.close()
                    camera_reader = None
                    next_camera_recovery_at = now + camera_recovery_seconds

                if camera_reader is None and now >= next_camera_recovery_at:
                    recovered_capture = _recover_camera(camera_source, debug=debug_mode)
                    if recovered_capture is None:
                        next_camera_recovery_at = now + camera_recovery_seconds
                    else:
                        camera_reader = _start_camera_reader(
                            recovered_capture,
                            rotate=rotate,
                            flip=flip,
                            unavailable_after=max_read_failures,
                            stale_after_seconds=camera_stale_seconds,
                            debug=debug_mode,
                        )
                        snapshot = camera_reader.snapshot(now=now)

                if snapshot.frame is not None:
                    last_preview_frame = snapshot.frame
                frame = snapshot.frame if snapshot.frame is not None else last_preview_frame
                camera_available = camera_reader is not None and snapshot.camera_available
                current_frame_available = camera_available and snapshot.frame is not None
                face_guidance = None
                preview_frame = frame
                if session.state == KioskState.IDLE and frame is not None and camera_available:
                    preview_frame, face_guidance = _annotate_preview_faces(frame)

                preview, button_bounds = _render_with_ui(
                    ui,
                    preview_frame,
                    session,
                    interaction=interaction,
                    face_guidance=face_guidance,
                    camera_available=camera_available,
                )
                interaction.button_bounds = button_bounds
                interaction.button_enabled = _primary_action_available(
                    session,
                    attempt,
                    button_bounds=button_bounds,
                    camera_available=current_frame_available,
                )
                cv2.imshow(WINDOW_NAME, preview)
                key = cv2.waitKey(1 if camera_available else 30) & 0xFF

                if key in {ord("q"), ord("Q")}:
                    break
                if key == ord(" "):
                    interaction.request_start()

                if not interaction.consume_start():
                    continue
                if session.state == KioskState.ERROR:
                    attempt.clear()
                    session.transition(
                        KioskState.IDLE,
                        "Ready for attendance.",
                        now=now,
                    )
                if not session.start(now=now):
                    continue

                attempt.begin()
                _release_interaction_lock(interaction)
                starting_frame, _bounds = _render_with_ui(
                    ui,
                    frame,
                    session,
                    interaction=interaction,
                    camera_available=camera_available,
                )
                cv2.imshow(WINDOW_NAME, starting_frame)
                cv2.waitKey(1)

                challenge = random.choice(list(CHALLENGES.keys()))
                attempt.challenge = challenge
                session.transition(
                    KioskState.LIVENESS,
                    CHALLENGES[challenge],
                    now=time.monotonic(),
                )
                frames = _capture_sequence(
                    camera_reader,
                    ui=ui,
                    session=session,
                    interaction=interaction,
                    frame_count=frame_count,
                    seconds=capture_seconds,
                    challenge=challenge,
                )
                if len(frames) < backend_min_frames:
                    attempt.clear()
                    session.finish(
                        success=False,
                        result=_error_payload(
                            "POOR_FRAMES",
                            "Unable to capture a clear image",
                            "Please keep still, look directly at the camera, and try again.",
                        ),
                        now=time.monotonic(),
                    )
                    _play_feedback(success=False)
                    continue

                session.transition(
                    KioskState.RECOGNIZING,
                    "Verifying identity...",
                    now=time.monotonic(),
                )
                request_future = executor.submit(
                    _submit_sequence,
                    client,
                    api_base_url=api_base_url,
                    authorization=authorization,
                    challenge=challenge,
                    frames=frames,
                )
                attempt.attach_request(request_future, challenge=challenge)
    finally:
        attempt.clear()
        if authorization is not None:
            authorization.clear()
        if camera_reader is not None:
            camera_reader.close()
        if capture is not None:
            capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
