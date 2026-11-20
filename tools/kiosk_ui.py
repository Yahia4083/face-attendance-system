"""Responsive OpenCV presentation layer for the physical attendance kiosk."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class Rect:
    """Pixel-aligned rectangle used by the kiosk layout and hit testing."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.width // 2, self.top + self.height // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def inset(self, amount: int) -> "Rect":
        return Rect(
            self.left + amount,
            self.top + amount,
            self.right - amount,
            self.bottom - amount,
        )


ButtonBounds = Rect


@dataclass
class KioskInteraction:
    """Tracks pointer feedback and emits one guarded primary-action request."""

    button_bounds: ButtonBounds | None = None
    button_enabled: bool = False
    start_requested: bool = False
    pointer_x: int = -1
    pointer_y: int = -1
    button_pressed: bool = False

    @property
    def button_hovered(self) -> bool:
        return bool(
            self.button_enabled
            and self.button_bounds is not None
            and self.button_bounds.contains(self.pointer_x, self.pointer_y)
        )

    def on_mouse(self, event, x, y, _flags, _parameter) -> None:
        self.pointer_x = int(x)
        self.pointer_y = int(y)
        if event == cv2.EVENT_LBUTTONDOWN and self.button_hovered:
            self.button_pressed = True
            self.start_requested = True
        elif event == cv2.EVENT_LBUTTONUP:
            self.button_pressed = False

    def request_start(self) -> None:
        if self.button_enabled:
            self.start_requested = True

    def consume_start(self) -> bool:
        requested = self.start_requested
        self.start_requested = False
        return requested


class KioskTheme:
    """Semantic OpenCV BGR colors shared by every kiosk state."""

    BACKGROUND = (39, 27, 13)
    BACKGROUND_GRID = (47, 34, 18)
    SURFACE = (57, 40, 20)
    SURFACE_SECONDARY = (72, 52, 28)
    CAMERA_BACKGROUND = (19, 15, 10)
    PRIMARY = (132, 117, 18)
    PRIMARY_HOVER = (148, 135, 24)
    PRIMARY_PRESSED = (112, 94, 13)
    PRIMARY_MUTED = (91, 82, 58)
    SUCCESS = (91, 137, 42)
    WARNING = (40, 151, 204)
    ERROR = (84, 75, 185)
    TEXT_PRIMARY = (247, 245, 241)
    TEXT_SECONDARY = (219, 213, 204)
    TEXT_MUTED = (164, 157, 146)
    BORDER = (91, 67, 38)
    GUIDE = (211, 204, 190)
    SHADOW = (17, 13, 9)


@dataclass(frozen=True)
class KioskLayout:
    canvas: Rect
    header: Rect
    body: Rect
    camera_card: Rect
    camera_viewport: Rect
    information_card: Rect
    footer: Rect


@dataclass(frozen=True)
class KioskRenderResult:
    frame: np.ndarray
    button_bounds: ButtonBounds | None
    button_action: str | None
    camera_content_bounds: Rect | None


def calculate_kiosk_layout(width: int, height: int) -> KioskLayout:
    """Calculate a stable two-column kiosk layout for common 16:9 displays."""

    if width < 800 or height < 450:
        raise ValueError("Kiosk canvas must be at least 800x450 pixels.")

    scale = min(width / 1280.0, height / 720.0)
    margin = max(14, int(round(24 * scale)))
    gap = max(12, int(round(20 * scale)))
    header_height = max(60, int(round(76 * scale)))
    footer_height = max(34, int(round(42 * scale)))
    canvas = Rect(0, 0, width, height)
    header = Rect(0, 0, width, header_height)
    footer = Rect(0, height - footer_height, width, height)
    body = Rect(
        margin,
        header.bottom + margin,
        width - margin,
        footer.top - margin,
    )

    information_width = max(int(round(350 * scale)), int(body.width * 0.31))
    information_width = min(information_width, int(body.width * 0.39))
    camera_card = Rect(
        body.left,
        body.top,
        body.right - information_width - gap,
        body.bottom,
    )
    information_card = Rect(
        camera_card.right + gap,
        body.top,
        body.right,
        body.bottom,
    )
    card_padding = max(10, int(round(14 * scale)))
    camera_label_height = max(28, int(round(34 * scale)))
    camera_viewport = Rect(
        camera_card.left + card_padding,
        camera_card.top + card_padding + camera_label_height,
        camera_card.right - card_padding,
        camera_card.bottom - card_padding,
    )
    return KioskLayout(
        canvas=canvas,
        header=header,
        body=body,
        camera_card=camera_card,
        camera_viewport=camera_viewport,
        information_card=information_card,
        footer=footer,
    )


def place_frame_aspect_fit(
    canvas: np.ndarray,
    frame: np.ndarray | None,
    bounds: Rect,
) -> Rect | None:
    """Place a camera frame without distortion and return its visible bounds."""

    _draw_rounded_rect(canvas, bounds, KioskTheme.CAMERA_BACKGROUND, radius=6, thickness=-1)
    if frame is None or frame.size == 0:
        return None

    frame_height, frame_width = frame.shape[:2]
    if frame_width <= 0 or frame_height <= 0 or bounds.width <= 0 or bounds.height <= 0:
        return None
    ratio = min(bounds.width / frame_width, bounds.height / frame_height)
    output_width = max(1, int(round(frame_width * ratio)))
    output_height = max(1, int(round(frame_height * ratio)))
    resized = cv2.resize(frame, (output_width, output_height), interpolation=cv2.INTER_AREA)
    left = bounds.left + (bounds.width - output_width) // 2
    top = bounds.top + (bounds.height - output_height) // 2
    canvas[top : top + output_height, left : left + output_width] = resized
    return Rect(left, top, left + output_width, top + output_height)


class AttendanceKioskUI:
    """Render the attendance state machine into one professional kiosk canvas."""

    PROCESSING_STATES = {"CAPTURING", "LIVENESS", "RECOGNIZING", "PROCESSING_ATTENDANCE"}

    def __init__(
        self,
        *,
        width: int = 1280,
        height: int = 720,
        brand: str = "Face Attendance",
        presentation_mode: bool = True,
        debug_mode: bool = False,
    ) -> None:
        self.width = int(width)
        self.height = int(height)
        self.scale = min(self.width / 1280.0, self.height / 720.0)
        self.brand = brand.strip() or "Face Attendance"
        self.presentation_mode = bool(presentation_mode)
        self.debug_mode = bool(debug_mode)
        self.layout = calculate_kiosk_layout(self.width, self.height)
        self._background = self._build_background()

    def render(
        self,
        camera_frame: np.ndarray | None,
        *,
        state: object,
        message: str,
        result: dict[str, Any] | None = None,
        face_guidance: str | None = None,
        challenge: str | None = None,
        progress: float | None = None,
        button_hovered: bool = False,
        button_pressed: bool = False,
        state_age: float = 0.0,
        camera_available: bool = True,
        now: float | None = None,
    ) -> KioskRenderResult:
        state_name = getattr(state, "value", str(state)).upper()
        now = time.monotonic() if now is None else now
        canvas = self._background.copy()
        self._draw_header(canvas, state_name, camera_available)
        camera_content = self._draw_camera_card(
            canvas,
            camera_frame,
            state_name=state_name,
            face_guidance=face_guidance,
            camera_available=camera_available,
        )
        button_bounds, button_action = self._draw_information_card(
            canvas,
            state_name=state_name,
            message=message,
            result=result or {},
            face_guidance=face_guidance,
            challenge=challenge,
            progress=progress,
            hovered=button_hovered,
            pressed=button_pressed,
            now=now,
        )
        self._draw_footer(canvas, state_name)

        if 0.0 <= state_age < 0.16:
            # A short fade softens state changes without adding a persistent animation cost.
            fade = max(0.68, min(1.0, 0.68 + (state_age / 0.16) * 0.32))
            canvas = cv2.addWeighted(canvas, fade, self._background, 1.0 - fade, 0)
        return KioskRenderResult(
            frame=canvas,
            button_bounds=button_bounds,
            button_action=button_action,
            camera_content_bounds=camera_content,
        )

    def _build_background(self) -> np.ndarray:
        canvas = np.full((self.height, self.width, 3), KioskTheme.BACKGROUND, dtype=np.uint8)
        spacing = max(90, int(round(132 * self.scale)))
        for x in range(0, self.width, spacing):
            cv2.line(canvas, (x, 0), (x, self.height), KioskTheme.BACKGROUND_GRID, 1, cv2.LINE_AA)
        for y in range(0, self.height, spacing):
            cv2.line(canvas, (0, y), (self.width, y), KioskTheme.BACKGROUND_GRID, 1, cv2.LINE_AA)
        cv2.rectangle(canvas, (0, 0), (max(3, int(round(4 * self.scale))), self.height), KioskTheme.PRIMARY, -1)
        return canvas

    def _draw_header(self, canvas: np.ndarray, state_name: str, camera_available: bool) -> None:
        header = self.layout.header
        cv2.line(
            canvas,
            (0, header.bottom - 1),
            (self.width, header.bottom - 1),
            KioskTheme.BORDER,
            max(1, int(round(self.scale))),
        )
        accent_left = max(20, int(round(28 * self.scale)))
        cv2.rectangle(
            canvas,
            (accent_left, header.top + int(round(17 * self.scale))),
            (accent_left + max(3, int(round(4 * self.scale))), header.top + int(round(58 * self.scale))),
            KioskTheme.PRIMARY,
            -1,
        )
        brand_x = accent_left + int(round(16 * self.scale))
        self._draw_text(
            canvas,
            self.brand,
            x=brand_x,
            y=header.top + int(round(35 * self.scale)),
            scale=self._font_scale(0.68),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(2),
            font=cv2.FONT_HERSHEY_SIMPLEX,
        )
        self._draw_text(
            canvas,
            "SECURE IDENTITY AND ATTENDANCE TERMINAL",
            x=brand_x,
            y=header.top + int(round(55 * self.scale)),
            scale=self._font_scale(0.27),
            color=KioskTheme.TEXT_MUTED,
            thickness=self._thickness(1),
        )
        status_text, status_color = self._system_status(state_name, camera_available)
        self._draw_status_indicator(canvas, status_text, status_color)

    def _draw_camera_card(
        self,
        canvas: np.ndarray,
        camera_frame: np.ndarray | None,
        *,
        state_name: str,
        face_guidance: str | None,
        camera_available: bool,
    ) -> Rect | None:
        card = self.layout.camera_card
        self._draw_card(canvas, card)
        self._draw_text(
            canvas,
            "LIVE CAMERA",
            x=card.left + int(round(18 * self.scale)),
            y=card.top + int(round(33 * self.scale)),
            scale=self._font_scale(0.34),
            color=KioskTheme.TEXT_MUTED,
            thickness=self._thickness(1),
        )
        camera_content = place_frame_aspect_fit(canvas, camera_frame, self.layout.camera_viewport)
        if camera_content is None:
            self._draw_camera_placeholder(canvas, camera_available)
            return None

        if state_name in {"IDLE", "CAPTURING", "LIVENESS"}:
            self._draw_face_guide(canvas, camera_content)

        if not camera_available:
            self._draw_camera_unavailable_banner(canvas, camera_content)

        if self.debug_mode:
            debug_text = f"State: {state_name}"
            if face_guidance:
                debug_text += f" | Preview: {face_guidance}"
            self._draw_camera_debug_line(canvas, camera_content, debug_text)
        return camera_content

    def _draw_information_card(
        self,
        canvas: np.ndarray,
        *,
        state_name: str,
        message: str,
        result: dict[str, Any],
        face_guidance: str | None,
        challenge: str | None,
        progress: float | None,
        hovered: bool,
        pressed: bool,
        now: float,
    ) -> tuple[ButtonBounds | None, str | None]:
        card = self.layout.information_card
        self._draw_card(canvas, card)
        padding = max(18, int(round(26 * self.scale)))
        content = card.inset(padding)
        self._draw_text(
            canvas,
            "ATTENDANCE STATUS",
            x=content.left,
            y=content.top + int(round(18 * self.scale)),
            scale=self._font_scale(0.31),
            color=KioskTheme.TEXT_MUTED,
            thickness=self._thickness(1),
        )

        if state_name == "IDLE":
            return self._render_idle(canvas, content, face_guidance, hovered, pressed)
        if state_name == "SUCCESS":
            self._render_success(canvas, content, result)
            return None, None
        if state_name == "ERROR":
            bounds = self._render_error(canvas, content, message, result, hovered, pressed)
            return bounds, "RETRY" if bounds is not None else None
        if state_name == "COOLDOWN":
            self._render_cooldown(canvas, content, now)
            return None, None
        self._render_processing(
            canvas,
            content,
            state_name=state_name,
            message=message,
            challenge=challenge,
            progress=progress,
            now=now,
        )
        return None, None

    def _render_idle(
        self,
        canvas: np.ndarray,
        content: Rect,
        face_guidance: str | None,
        hovered: bool,
        pressed: bool,
    ) -> tuple[ButtonBounds, str]:
        title_y = content.top + int(round(82 * self.scale))
        self._draw_wrapped_text(
            canvas,
            "Ready for attendance",
            bounds=Rect(content.left, title_y - 35, content.right, title_y + 22),
            scale=self._font_scale(0.8),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(2),
            align="left",
            max_lines=2,
            font=cv2.FONT_HERSHEY_SIMPLEX,
        )
        body_top = title_y + int(round(40 * self.scale))
        self._draw_wrapped_text(
            canvas,
            "Stand in front of the camera, position your face inside the guide, then press the button below.",
            bounds=Rect(content.left, body_top, content.right, body_top + int(round(100 * self.scale))),
            scale=self._font_scale(0.48),
            color=KioskTheme.TEXT_SECONDARY,
            thickness=self._thickness(1),
            align="left",
            max_lines=4,
        )
        guidance = self._friendly_guidance(face_guidance)
        guide_y = min(content.bottom - int(round(135 * self.scale)), body_top + int(round(125 * self.scale)))
        self._draw_small_notice(canvas, Rect(content.left, guide_y, content.right, guide_y + int(round(54 * self.scale))), guidance)
        button = self._primary_button_bounds(content)
        self._draw_button(
            canvas,
            button,
            "START ATTENDANCE",
            hovered=hovered,
            pressed=pressed,
            enabled=True,
        )
        return button, "START"

    def _render_processing(
        self,
        canvas: np.ndarray,
        content: Rect,
        *,
        state_name: str,
        message: str,
        challenge: str | None,
        progress: float | None,
        now: float,
    ) -> None:
        if state_name == "LIVENESS":
            title = self._challenge_title(challenge, message)
            body = "Start facing forward, then follow the instruction slowly inside the guide."
            step = "Verification step 1 of 2"
        elif state_name == "RECOGNIZING":
            title = "Verifying identity..."
            body = "Please remain in front of the camera."
            step = "Verification step 2 of 2"
        elif state_name == "PROCESSING_ATTENDANCE":
            title = "Recording attendance..."
            body = "Your identity was verified. Please wait a moment."
            step = "Completing attendance"
        else:
            title = "Starting verification..."
            body = "Please look directly at the camera."
            step = "Preparing camera"

        spinner_center = (content.left + int(round(35 * self.scale)), content.top + int(round(82 * self.scale)))
        self._draw_spinner(canvas, spinner_center, now, KioskTheme.PRIMARY)
        title_bounds = Rect(
            content.left,
            content.top + int(round(118 * self.scale)),
            content.right,
            content.top + int(round(205 * self.scale)),
        )
        self._draw_wrapped_text(
            canvas,
            title,
            bounds=title_bounds,
            scale=self._font_scale(0.78),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(2),
            align="left",
            max_lines=2,
            font=cv2.FONT_HERSHEY_SIMPLEX,
        )
        body_top = title_bounds.bottom + int(round(20 * self.scale))
        self._draw_wrapped_text(
            canvas,
            body,
            bounds=Rect(content.left, body_top, content.right, body_top + int(round(90 * self.scale))),
            scale=self._font_scale(0.49),
            color=KioskTheme.TEXT_SECONDARY,
            thickness=self._thickness(1),
            align="left",
            max_lines=3,
        )
        progress_top = content.bottom - int(round(92 * self.scale))
        self._draw_text(
            canvas,
            step,
            x=content.left,
            y=progress_top,
            scale=self._font_scale(0.4),
            color=KioskTheme.TEXT_MUTED,
            thickness=self._thickness(1),
        )
        normalized = progress
        if normalized is None:
            normalized = 0.25 + (math.sin(now * 2.4) + 1.0) * 0.2
        self._draw_progress_bar(
            canvas,
            Rect(content.left, progress_top + int(round(17 * self.scale)), content.right, progress_top + int(round(27 * self.scale))),
            normalized,
        )

    def _render_success(self, canvas: np.ndarray, content: Rect, result: dict[str, Any]) -> None:
        action = str(result.get("action") or "ATTENDANCE").upper()
        heading = "Check-in successful" if action == "CHECK_IN" else "Check-out successful"
        icon_center = (content.left + int(round(31 * self.scale)), content.top + int(round(70 * self.scale)))
        self._draw_result_icon(canvas, icon_center, KioskTheme.SUCCESS, success=True)
        self._draw_wrapped_text(
            canvas,
            heading,
            bounds=Rect(
                content.left,
                content.top + int(round(112 * self.scale)),
                content.right,
                content.top + int(round(175 * self.scale)),
            ),
            scale=self._font_scale(0.72),
            color=KioskTheme.SUCCESS,
            thickness=self._thickness(2),
            align="left",
            max_lines=2,
            font=cv2.FONT_HERSHEY_SIMPLEX,
        )
        name = str(result.get("employee_name") or "Recognized employee")
        self._draw_fitted_text(
            canvas,
            name,
            bounds=Rect(
                content.left,
                content.top + int(round(196 * self.scale)),
                content.right,
                content.top + int(round(235 * self.scale)),
            ),
            preferred_scale=self._font_scale(0.68),
            minimum_scale=self._font_scale(0.42),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(2),
        )
        employee_number = str(result.get("employee_number") or "--")
        self._draw_text(
            canvas,
            f"Employee No. {employee_number}",
            x=content.left,
            y=content.top + int(round(267 * self.scale)),
            scale=self._font_scale(0.43),
            color=KioskTheme.TEXT_MUTED,
            thickness=self._thickness(1),
        )
        display_time = format_display_time(result.get("timestamp"))
        self._draw_text(
            canvas,
            display_time,
            x=content.left,
            y=content.top + int(round(337 * self.scale)),
            scale=self._font_scale(1.08),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(2),
            font=cv2.FONT_HERSHEY_SIMPLEX,
        )
        if action == "CHECK_OUT" and result.get("working_hours") is not None:
            try:
                detail = f"Working hours: {float(result['working_hours']):.2f} hours"
            except (TypeError, ValueError):
                detail = "Check-out recorded"
            self._draw_badge(canvas, content, detail, KioskTheme.PRIMARY)
        else:
            self._draw_badge(
                canvas,
                content,
                format_status(result.get("status")),
                self._attendance_status_color(result.get("status")),
            )

    def _render_error(
        self,
        canvas: np.ndarray,
        content: Rect,
        message: str,
        result: dict[str, Any],
        hovered: bool,
        pressed: bool,
    ) -> ButtonBounds | None:
        icon_center = (content.left + int(round(31 * self.scale)), content.top + int(round(68 * self.scale)))
        self._draw_result_icon(canvas, icon_center, KioskTheme.ERROR, success=False)
        title = str(result.get("error_title") or "Attendance not recorded")
        self._draw_wrapped_text(
            canvas,
            title,
            bounds=Rect(
                content.left,
                content.top + int(round(110 * self.scale)),
                content.right,
                content.top + int(round(180 * self.scale)),
            ),
            scale=self._font_scale(0.7),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(2),
            align="left",
            max_lines=2,
            font=cv2.FONT_HERSHEY_SIMPLEX,
        )
        self._draw_wrapped_text(
            canvas,
            message or "Please try again.",
            bounds=Rect(
                content.left,
                content.top + int(round(205 * self.scale)),
                content.right,
                content.bottom - int(round(125 * self.scale)),
            ),
            scale=self._font_scale(0.49),
            color=KioskTheme.TEXT_SECONDARY,
            thickness=self._thickness(1),
            align="left",
            max_lines=5,
        )
        if bool(result.get("recoverable", True)):
            button = self._primary_button_bounds(content)
            self._draw_button(
                canvas,
                button,
                "TRY AGAIN",
                hovered=hovered,
                pressed=pressed,
                enabled=True,
            )
            return button
        return None

    def _render_cooldown(self, canvas: np.ndarray, content: Rect, now: float) -> None:
        center = (content.left + int(round(35 * self.scale)), content.top + int(round(90 * self.scale)))
        self._draw_spinner(canvas, center, now, KioskTheme.WARNING)
        self._draw_wrapped_text(
            canvas,
            "Preparing for the next employee...",
            bounds=Rect(
                content.left,
                content.top + int(round(135 * self.scale)),
                content.right,
                content.top + int(round(245 * self.scale)),
            ),
            scale=self._font_scale(0.72),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(2),
            align="left",
            max_lines=3,
            font=cv2.FONT_HERSHEY_SIMPLEX,
        )
        self._draw_wrapped_text(
            canvas,
            "The terminal will be ready again automatically.",
            bounds=Rect(
                content.left,
                content.top + int(round(275 * self.scale)),
                content.right,
                content.top + int(round(355 * self.scale)),
            ),
            scale=self._font_scale(0.47),
            color=KioskTheme.TEXT_SECONDARY,
            thickness=self._thickness(1),
            align="left",
            max_lines=3,
        )

    def _draw_footer(self, canvas: np.ndarray, state_name: str) -> None:
        footer = self.layout.footer
        cv2.line(canvas, (0, footer.top), (self.width, footer.top), KioskTheme.BORDER, 1)
        baseline = footer.top + max(23, int(round(27 * self.scale)))
        self._draw_text(
            canvas,
            "Secure face attendance",
            x=max(18, int(round(28 * self.scale))),
            y=baseline,
            scale=self._font_scale(0.36),
            color=KioskTheme.TEXT_MUTED,
            thickness=self._thickness(1),
        )
        if not self.presentation_mode or self.debug_mode:
            hint = "SPACE: Start / Try Again    Q: Exit"
            if self.debug_mode:
                hint += f"    State: {state_name}"
            self._draw_text(
                canvas,
                hint,
                x=self.width - max(18, int(round(28 * self.scale))),
                y=baseline,
                scale=self._font_scale(0.34),
                color=KioskTheme.TEXT_MUTED,
                thickness=self._thickness(1),
                align="right",
            )

    def _draw_card(self, canvas: np.ndarray, bounds: Rect) -> None:
        radius = max(5, int(round(7 * self.scale)))
        _draw_rounded_rect(canvas, bounds, KioskTheme.SURFACE, radius=radius, thickness=-1)
        _draw_rounded_rect(canvas, bounds, KioskTheme.BORDER, radius=radius, thickness=max(1, int(round(self.scale))))

    def _draw_face_guide(self, canvas: np.ndarray, camera_bounds: Rect) -> None:
        guide_width = int(camera_bounds.width * 0.34)
        guide_height = int(camera_bounds.height * 0.64)
        center_x, center_y = camera_bounds.center
        center_y += int(camera_bounds.height * 0.01)
        axes = (max(50, guide_width // 2), max(72, guide_height // 2))
        overlay = canvas.copy()
        cv2.ellipse(overlay, (center_x, center_y), axes, 0, 0, 360, KioskTheme.GUIDE, max(1, self._thickness(1)), cv2.LINE_AA)
        canvas[:] = cv2.addWeighted(overlay, 0.58, canvas, 0.42, 0)
        corner = max(18, int(round(26 * self.scale)))
        left = center_x - axes[0]
        right = center_x + axes[0]
        top = center_y - axes[1]
        bottom = center_y + axes[1]
        for start, end in (
            ((left, top + corner), (left, top)),
            ((left, top), (left + corner, top)),
            ((right - corner, top), (right, top)),
            ((right, top), (right, top + corner)),
            ((left, bottom - corner), (left, bottom)),
            ((left, bottom), (left + corner, bottom)),
            ((right - corner, bottom), (right, bottom)),
            ((right, bottom - corner), (right, bottom)),
        ):
            cv2.line(canvas, start, end, KioskTheme.GUIDE, self._thickness(2), cv2.LINE_AA)

    def _draw_camera_debug_line(self, canvas: np.ndarray, bounds: Rect, text: str) -> None:
        bar_height = max(24, int(round(31 * self.scale)))
        bar = Rect(bounds.left, bounds.bottom - bar_height, bounds.right, bounds.bottom)
        overlay = canvas.copy()
        cv2.rectangle(overlay, (bar.left, bar.top), (bar.right, bar.bottom), (10, 10, 10), -1)
        canvas[:] = cv2.addWeighted(overlay, 0.72, canvas, 0.28, 0)
        self._draw_fitted_text(
            canvas,
            text,
            bounds=bar.inset(max(5, int(round(7 * self.scale)))),
            preferred_scale=self._font_scale(0.33),
            minimum_scale=self._font_scale(0.24),
            color=KioskTheme.TEXT_SECONDARY,
            thickness=1,
        )

    def _draw_camera_unavailable_banner(self, canvas: np.ndarray, bounds: Rect) -> None:
        """Report a sustained camera failure without hiding the last valid frame."""

        margin = max(8, int(round(11 * self.scale)))
        height = max(31, int(round(38 * self.scale)))
        banner = Rect(
            bounds.left + margin,
            bounds.top + margin,
            bounds.right - margin,
            bounds.top + margin + height,
        )
        _draw_rounded_rect(
            canvas,
            banner,
            KioskTheme.ERROR,
            radius=max(3, int(round(5 * self.scale))),
            thickness=-1,
        )
        self._draw_text(
            canvas,
            "Camera unavailable",
            x=banner.left + max(10, int(round(13 * self.scale))),
            y=banner.top + int(round(25 * self.scale)),
            scale=self._font_scale(0.4),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(1),
        )

    def _draw_camera_placeholder(self, canvas: np.ndarray, camera_available: bool) -> None:
        bounds = self.layout.camera_viewport
        center_x, center_y = bounds.center
        color = KioskTheme.TEXT_MUTED if camera_available else KioskTheme.ERROR
        cv2.circle(canvas, (center_x, center_y - 18), max(22, int(round(30 * self.scale))), color, self._thickness(2), cv2.LINE_AA)
        self._draw_text(
            canvas,
            "Waiting for camera" if camera_available else "Camera unavailable",
            x=center_x,
            y=center_y + int(round(48 * self.scale)),
            scale=self._font_scale(0.52),
            color=color,
            thickness=self._thickness(1),
            align="center",
        )

    def _draw_status_indicator(self, canvas: np.ndarray, text: str, color: tuple[int, int, int]) -> None:
        text_scale = self._font_scale(0.42)
        text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, text_scale, self._thickness(1))
        padding_x = max(13, int(round(18 * self.scale)))
        pill_width = text_size[0] + padding_x * 2 + int(round(18 * self.scale))
        pill_height = max(34, int(round(40 * self.scale)))
        right = self.width - max(20, int(round(30 * self.scale)))
        top = (self.layout.header.height - pill_height) // 2
        bounds = Rect(right - pill_width, top, right, top + pill_height)
        _draw_rounded_rect(canvas, bounds, KioskTheme.SURFACE_SECONDARY, radius=max(5, int(round(7 * self.scale))), thickness=-1)
        dot_center = (bounds.left + padding_x, bounds.top + pill_height // 2)
        cv2.circle(canvas, dot_center, max(4, int(round(5 * self.scale))), color, -1, cv2.LINE_AA)
        self._draw_text(
            canvas,
            text,
            x=dot_center[0] + int(round(13 * self.scale)),
            y=bounds.top + int(round(26 * self.scale)),
            scale=text_scale,
            color=KioskTheme.TEXT_SECONDARY,
            thickness=self._thickness(1),
        )

    def _draw_button(
        self,
        canvas: np.ndarray,
        bounds: Rect,
        label: str,
        *,
        hovered: bool,
        pressed: bool,
        enabled: bool,
    ) -> None:
        if not enabled:
            fill = KioskTheme.PRIMARY_MUTED
        elif pressed:
            fill = KioskTheme.PRIMARY_PRESSED
        elif hovered:
            fill = KioskTheme.PRIMARY_HOVER
        else:
            fill = KioskTheme.PRIMARY
        radius = max(4, int(round(6 * self.scale)))
        _draw_rounded_rect(canvas, bounds, fill, radius=radius, thickness=-1)
        _draw_rounded_rect(canvas, bounds, KioskTheme.PRIMARY_HOVER if enabled else KioskTheme.PRIMARY_MUTED, radius=radius, thickness=max(1, int(round(self.scale))))
        self._draw_text(
            canvas,
            label,
            x=bounds.center[0],
            y=bounds.top + int(bounds.height * 0.62),
            scale=self._font_scale(0.58),
            color=KioskTheme.TEXT_PRIMARY,
            thickness=self._thickness(2),
            align="center",
            font=cv2.FONT_HERSHEY_SIMPLEX,
        )

    def _draw_spinner(self, canvas: np.ndarray, center: tuple[int, int], now: float, color: tuple[int, int, int]) -> None:
        radius = max(19, int(round(24 * self.scale)))
        dot_radius = max(2, int(round(4 * self.scale)))
        active = int((now * 7.0) % 8)
        for index in range(8):
            angle = (math.pi * 2 * index / 8.0) - math.pi / 2
            x = int(center[0] + math.cos(angle) * radius)
            y = int(center[1] + math.sin(angle) * radius)
            strength = 1.0 if index == active else max(0.22, 0.75 - ((index - active) % 8) * 0.09)
            dot_color = tuple(int(channel * strength) for channel in color)
            cv2.circle(canvas, (x, y), dot_radius, dot_color, -1, cv2.LINE_AA)

    def _draw_progress_bar(self, canvas: np.ndarray, bounds: Rect, progress: float) -> None:
        progress = min(1.0, max(0.0, float(progress)))
        _draw_rounded_rect(canvas, bounds, KioskTheme.SURFACE_SECONDARY, radius=max(2, bounds.height // 2), thickness=-1)
        if progress <= 0:
            return
        filled = Rect(bounds.left, bounds.top, bounds.left + max(bounds.height, int(bounds.width * progress)), bounds.bottom)
        _draw_rounded_rect(canvas, filled, KioskTheme.PRIMARY, radius=max(2, bounds.height // 2), thickness=-1)

    def _draw_result_icon(
        self,
        canvas: np.ndarray,
        center: tuple[int, int],
        color: tuple[int, int, int],
        *,
        success: bool,
    ) -> None:
        radius = max(24, int(round(30 * self.scale)))
        cv2.circle(canvas, center, radius, color, self._thickness(2), cv2.LINE_AA)
        if success:
            points = np.asarray(
                [
                    (center[0] - int(radius * 0.46), center[1]),
                    (center[0] - int(radius * 0.12), center[1] + int(radius * 0.34)),
                    (center[0] + int(radius * 0.52), center[1] - int(radius * 0.38)),
                ],
                dtype=np.int32,
            )
            cv2.polylines(canvas, [points], False, color, self._thickness(3), cv2.LINE_AA)
        else:
            cv2.line(
                canvas,
                (center[0], center[1] - int(radius * 0.45)),
                (center[0], center[1] + int(radius * 0.12)),
                color,
                self._thickness(3),
                cv2.LINE_AA,
            )
            cv2.circle(canvas, (center[0], center[1] + int(radius * 0.48)), max(2, self._thickness(2)), color, -1, cv2.LINE_AA)

    def _draw_badge(self, canvas: np.ndarray, content: Rect, text: str, color: tuple[int, int, int]) -> None:
        text_scale = self._font_scale(0.42)
        text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, text_scale, self._thickness(1))
        width = min(content.width, text_size[0] + int(round(30 * self.scale)))
        height = max(32, int(round(38 * self.scale)))
        top = content.bottom - height
        bounds = Rect(content.left, top, content.left + width, top + height)
        _draw_rounded_rect(canvas, bounds, KioskTheme.SURFACE_SECONDARY, radius=max(4, int(round(6 * self.scale))), thickness=-1)
        cv2.circle(canvas, (bounds.left + int(round(14 * self.scale)), bounds.center[1]), max(3, int(round(4 * self.scale))), color, -1, cv2.LINE_AA)
        self._draw_fitted_text(
            canvas,
            text,
            bounds=Rect(bounds.left + int(round(25 * self.scale)), bounds.top + 2, bounds.right - 8, bounds.bottom - 2),
            preferred_scale=text_scale,
            minimum_scale=self._font_scale(0.3),
            color=KioskTheme.TEXT_SECONDARY,
            thickness=self._thickness(1),
        )

    def _draw_small_notice(self, canvas: np.ndarray, bounds: Rect, text: str) -> None:
        _draw_rounded_rect(canvas, bounds, KioskTheme.SURFACE_SECONDARY, radius=max(4, int(round(6 * self.scale))), thickness=-1)
        cv2.circle(
            canvas,
            (bounds.left + int(round(15 * self.scale)), bounds.center[1]),
            max(3, int(round(4 * self.scale))),
            KioskTheme.SUCCESS if "correct" in text.lower() else KioskTheme.PRIMARY,
            -1,
            cv2.LINE_AA,
        )
        self._draw_fitted_text(
            canvas,
            text,
            bounds=Rect(bounds.left + int(round(28 * self.scale)), bounds.top + 4, bounds.right - 8, bounds.bottom - 4),
            preferred_scale=self._font_scale(0.36),
            minimum_scale=self._font_scale(0.27),
            color=KioskTheme.TEXT_SECONDARY,
            thickness=self._thickness(1),
        )

    def _draw_text(
        self,
        canvas: np.ndarray,
        text: str,
        *,
        x: int,
        y: int,
        scale: float,
        color: tuple[int, int, int],
        thickness: int,
        align: str = "left",
        font: int = cv2.FONT_HERSHEY_SIMPLEX,
    ) -> None:
        text = str(text)
        size, _ = cv2.getTextSize(text, font, scale, thickness)
        if align == "center":
            x -= size[0] // 2
        elif align == "right":
            x -= size[0]
        cv2.putText(canvas, text, (int(x), int(y)), font, scale, color, thickness, cv2.LINE_AA)

    def _draw_fitted_text(
        self,
        canvas: np.ndarray,
        text: str,
        *,
        bounds: Rect,
        preferred_scale: float,
        minimum_scale: float,
        color: tuple[int, int, int],
        thickness: int,
        font: int = cv2.FONT_HERSHEY_SIMPLEX,
    ) -> None:
        scale = preferred_scale
        while scale > minimum_scale:
            size, _ = cv2.getTextSize(text, font, scale, thickness)
            if size[0] <= bounds.width:
                break
            scale -= 0.03
        fitted = self._ellipsize(text, bounds.width, font, scale, thickness)
        size, _ = cv2.getTextSize(fitted, font, scale, thickness)
        y = bounds.top + max(size[1], (bounds.height + size[1]) // 2)
        self._draw_text(
            canvas,
            fitted,
            x=bounds.left,
            y=min(bounds.bottom, y),
            scale=scale,
            color=color,
            thickness=thickness,
            font=font,
        )

    def _draw_wrapped_text(
        self,
        canvas: np.ndarray,
        text: str,
        *,
        bounds: Rect,
        scale: float,
        color: tuple[int, int, int],
        thickness: int,
        align: str,
        max_lines: int,
        font: int = cv2.FONT_HERSHEY_SIMPLEX,
    ) -> None:
        lines = self._wrap_to_width(text, bounds.width, font, scale, thickness)
        lines = lines[:max_lines]
        if len(lines) == max_lines:
            lines[-1] = self._ellipsize(lines[-1], bounds.width, font, scale, thickness)
        line_height = max(18, int(round(30 * self.scale * max(0.7, scale / max(self.scale, 0.01)))))
        baseline = bounds.top + line_height
        for line in lines:
            x = bounds.left if align == "left" else bounds.center[0]
            self._draw_text(
                canvas,
                line,
                x=x,
                y=baseline,
                scale=scale,
                color=color,
                thickness=thickness,
                align=align,
                font=font,
            )
            baseline += line_height
            if baseline > bounds.bottom:
                break

    def _wrap_to_width(self, text: str, width: int, font: int, scale: float, thickness: int) -> list[str]:
        words = str(text).split()
        if not words:
            return [""]
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            size, _ = cv2.getTextSize(candidate, font, scale, thickness)
            if size[0] <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    @staticmethod
    def _ellipsize(text: str, width: int, font: int, scale: float, thickness: int) -> str:
        text = str(text)
        size, _ = cv2.getTextSize(text, font, scale, thickness)
        if size[0] <= width:
            return text
        candidate = text
        while candidate:
            candidate = candidate[:-1]
            output = candidate.rstrip() + "..."
            size, _ = cv2.getTextSize(output, font, scale, thickness)
            if size[0] <= width:
                return output
        return "..."

    def _primary_button_bounds(self, content: Rect) -> Rect:
        height = max(60, int(round(72 * self.scale)))
        return Rect(content.left, content.bottom - height, content.right, content.bottom)

    def _font_scale(self, base: float) -> float:
        return max(0.32, base * self.scale)

    def _thickness(self, base: int) -> int:
        return max(1, int(round(base * self.scale)))

    @staticmethod
    def _friendly_guidance(guidance: str | None) -> str:
        if not guidance:
            return "Position your face inside the guide."
        lowered = guidance.lower()
        if "correct" in lowered:
            return "Face position looks correct."
        if "multiple" in lowered:
            return "Keep only one person in front of the device."
        return "Move closer and keep your face centered."

    @staticmethod
    def _challenge_title(challenge: str | None, message: str) -> str:
        normalized = str(challenge or "").upper()
        if normalized == "TURN_HEAD_LEFT":
            return "Turn your head slightly left"
        if normalized == "TURN_HEAD_RIGHT":
            return "Turn your head slightly right"
        if normalized == "BLINK":
            return "Blink naturally"
        if message:
            return message
        return "Complete the live verification"

    @staticmethod
    def _system_status(state_name: str, camera_available: bool) -> tuple[str, tuple[int, int, int]]:
        if not camera_available:
            return "Camera unavailable", KioskTheme.ERROR
        if state_name == "IDLE":
            return "System Ready", KioskTheme.SUCCESS
        if state_name == "SUCCESS":
            return "Attendance recorded", KioskTheme.SUCCESS
        if state_name == "ERROR":
            return "Action required", KioskTheme.ERROR
        if state_name == "COOLDOWN":
            return "Preparing", KioskTheme.WARNING
        return "Processing", KioskTheme.WARNING

    @staticmethod
    def _attendance_status_color(status: object) -> tuple[int, int, int]:
        normalized = str(status or "").upper()
        if normalized in {"PRESENT", "ON_TIME"}:
            return KioskTheme.SUCCESS
        if normalized in {"LATE", "MISSING_CHECKOUT"}:
            return KioskTheme.WARNING
        if normalized in {"ABSENT"}:
            return KioskTheme.ERROR
        return KioskTheme.PRIMARY


def format_status(value: object) -> str:
    """Format backend enum values for employee-facing result badges."""

    if value is None or str(value).strip() == "":
        return "Attendance recorded"
    return str(value).replace("_", " ").strip().title()


def format_display_time(value: object) -> str:
    """Format an explicit API timestamp without changing its represented instant."""

    if not isinstance(value, str) or not value:
        return "--:--"
    try:
        from datetime import datetime

        return datetime.fromisoformat(value).strftime("%I:%M %p")
    except ValueError:
        return value


def _draw_rounded_rect(
    canvas: np.ndarray,
    bounds: Rect,
    color: tuple[int, int, int],
    *,
    radius: int,
    thickness: int,
) -> None:
    radius = max(0, min(radius, bounds.width // 2, bounds.height // 2))
    if radius == 0:
        cv2.rectangle(canvas, (bounds.left, bounds.top), (bounds.right, bounds.bottom), color, thickness)
        return
    if thickness < 0:
        cv2.rectangle(canvas, (bounds.left + radius, bounds.top), (bounds.right - radius, bounds.bottom), color, -1)
        cv2.rectangle(canvas, (bounds.left, bounds.top + radius), (bounds.right, bounds.bottom - radius), color, -1)
        for center in (
            (bounds.left + radius, bounds.top + radius),
            (bounds.right - radius, bounds.top + radius),
            (bounds.left + radius, bounds.bottom - radius),
            (bounds.right - radius, bounds.bottom - radius),
        ):
            cv2.circle(canvas, center, radius, color, -1, cv2.LINE_AA)
        return

    cv2.line(canvas, (bounds.left + radius, bounds.top), (bounds.right - radius, bounds.top), color, thickness, cv2.LINE_AA)
    cv2.line(canvas, (bounds.left + radius, bounds.bottom), (bounds.right - radius, bounds.bottom), color, thickness, cv2.LINE_AA)
    cv2.line(canvas, (bounds.left, bounds.top + radius), (bounds.left, bounds.bottom - radius), color, thickness, cv2.LINE_AA)
    cv2.line(canvas, (bounds.right, bounds.top + radius), (bounds.right, bounds.bottom - radius), color, thickness, cv2.LINE_AA)
    cv2.ellipse(canvas, (bounds.left + radius, bounds.top + radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(canvas, (bounds.right - radius, bounds.top + radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(canvas, (bounds.right - radius, bounds.bottom - radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(canvas, (bounds.left + radius, bounds.bottom - radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)
