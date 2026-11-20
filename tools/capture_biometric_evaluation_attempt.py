"""Capture private, independent camera attempts for local PAD calibration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import time

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings, resolve_project_path  # noqa: E402
from app.domain.services.liveness_service import LivenessFrame  # noqa: E402
from app.infrastructure.face_ai.face_anti_spoofing import (  # noqa: E402
    OnnxFaceAntiSpoofingService,
)
from app.infrastructure.face_ai.mtcnn_face_detector import MTCNNFaceDetector  # noqa: E402
from tools.live_mobile_attendance_kiosk import (  # noqa: E402
    CameraFrameReader,
    _camera_open_error,
    _camera_source,
    _camera_stale_seconds,
    _flip_setting,
    _int_env,
    _open_camera,
    _rotation_setting,
)


WINDOW_NAME = "Private PAD Calibration Capture"
DEFAULT_PAD_ROOT = Path("storage/evaluation/pad_samples")
JPEG_QUALITY = 90


class CaptureAborted(Exception):
    """Stop the local capture session without leaving a partial attempt."""


@dataclass(frozen=True)
class CaptureSummary:
    """Report how many independent attempts were usable for later evaluation."""

    captured: int
    usable: int
    rejected: int


def _next_attempt_directory(
    pad_root: Path,
    *,
    label: str,
    spoof_type: str,
) -> Path:
    """Choose the next independent attempt directory without overwriting samples."""

    parent = pad_root / label
    if label == "spoof":
        parent /= spoof_type
    used_numbers: list[int] = []
    if parent.exists():
        for directory in parent.iterdir():
            match = re.fullmatch(r"attempt_(\d+)", directory.name)
            if directory.is_dir() and match:
                used_numbers.append(int(match.group(1)))
    next_number = max(used_numbers, default=0) + 1
    return parent / f"attempt_{next_number:03d}"


def _write_attempt(output: Path, frames: list[bytes]) -> None:
    """Persist one explicitly requested and pipeline-validated camera sequence."""

    if output.exists() and any(output.iterdir()):
        raise ValueError("The output attempt directory must be new or empty.")
    output.mkdir(parents=True, exist_ok=True)
    for index, content in enumerate(frames, start=1):
        (output / f"frame_{index:03d}.jpg").write_bytes(content)


def _preview_canvas(frame: np.ndarray | None, message: str) -> np.ndarray:
    """Keep capture instructions visible while showing the latest camera frame."""

    canvas = frame.copy() if frame is not None else np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 72), (15, 23, 42), -1)
    cv2.putText(
        canvas,
        message,
        (24, 46),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (240, 245, 255),
        2,
        cv2.LINE_AA,
    )
    return canvas


def _wait_for_space(reader: CameraFrameReader, message: str) -> None:
    """Wait for an explicit operator action before collecting biometric samples."""

    while True:
        snapshot = reader.snapshot()
        status = message if snapshot.camera_available else "Camera unavailable - Q to abort"
        cv2.imshow(WINDOW_NAME, _preview_canvas(snapshot.frame, status))
        key = cv2.waitKey(10) & 0xFF
        if key == ord(" ") and snapshot.camera_available and snapshot.frame is not None:
            return
        if key in {ord("q"), ord("Q")}:
            raise CaptureAborted


def _show_countdown(reader: CameraFrameReader, seconds: int) -> None:
    """Give the operator time to establish the intended real or spoof presentation."""

    for remaining in range(max(0, seconds), 0, -1):
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            snapshot = reader.snapshot()
            cv2.imshow(
                WINDOW_NAME,
                _preview_canvas(snapshot.frame, f"Capture starts in {remaining}"),
            )
            if cv2.waitKey(10) & 0xFF in {ord("q"), ord("Q")}:
                raise CaptureAborted


def _capture_sequence(
    reader: CameraFrameReader,
    *,
    frame_count: int,
    seconds: float,
) -> list[bytes]:
    """Collect a time-spaced frame sequence comparable to a kiosk attendance attempt."""

    frames: list[bytes] = []
    started = time.monotonic()
    next_sample = started
    last_sequence = -1
    interval = seconds / frame_count
    while len(frames) < frame_count and time.monotonic() - started <= seconds + 2.0:
        now = time.monotonic()
        snapshot = reader.snapshot(now=now)
        cv2.imshow(
            WINDOW_NAME,
            _preview_canvas(
                snapshot.frame,
                f"PRIVATE PAD CAPTURE {len(frames)}/{frame_count} - Q to abort",
            ),
        )
        if cv2.waitKey(5) & 0xFF in {ord("q"), ord("Q")}:
            raise CaptureAborted

        if (
            now >= next_sample
            and snapshot.camera_available
            and snapshot.frame is not None
            and snapshot.sequence != last_sequence
        ):
            encoded, buffer = cv2.imencode(
                ".jpg",
                snapshot.frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
            )
            if encoded:
                frames.append(buffer.tobytes())
                last_sequence = snapshot.sequence
                next_sample = started + len(frames) * interval
    return frames


def _validate_sequence(service: OnnxFaceAntiSpoofingService, frames: list[bytes]):
    """Use the exact runtime detector, crop, preprocessing, model, and aggregation path."""

    payload = [
        LivenessFrame(filename=f"frame_{index:03d}.jpg", content=content)
        for index, content in enumerate(frames, start=1)
    ]
    return service.score_sequence(payload)


def _capture_attempts(
    *,
    reader: CameraFrameReader,
    service: OnnxFaceAntiSpoofingService,
    attempts: int,
    frames_per_attempt: int,
    seconds: float,
    countdown: int,
    output: Path | None,
    pad_root: Path,
    label: str,
    spoof_type: str,
) -> CaptureSummary:
    """Capture multiple independent attempts and store only runtime-usable sequences."""

    captured = usable = rejected = 0
    for attempt_index in range(1, attempts + 1):
        if label == "real":
            heading = "REAL PERSON"
        elif label == "spoof":
            heading = f"SPOOF: {spoof_type.replace('_', ' ').upper()}"
        else:
            heading = "EVALUATION ATTEMPT"
        print(f"\nPAD CALIBRATION - {heading} - attempt {attempt_index}/{attempts}")
        print("Keep exactly one face visible. Press SPACE when the presentation is ready.")
        _wait_for_space(reader, f"{heading} - Press SPACE to capture attempt {attempt_index}")
        _show_countdown(reader, countdown)
        frames = _capture_sequence(
            reader,
            frame_count=frames_per_attempt,
            seconds=seconds,
        )
        captured += 1
        if len(frames) != frames_per_attempt:
            rejected += 1
            print(
                f"[REJECTED] Camera supplied {len(frames)}/{frames_per_attempt} usable frames."
            )
            continue

        print("Validating attempt with the runtime PAD pipeline...")
        score = _validate_sequence(service, frames)
        if score.real_score is None:
            rejected += 1
            print(f"[REJECTED] {score.failure_reason or 'The sequence was not usable.'}")
            continue

        destination = output or _next_attempt_directory(
            pad_root,
            label=label,
            spoof_type=spoof_type,
        )
        _write_attempt(destination, frames)
        usable += 1
        print(f"[SAVED] {destination}")
        if get_settings().FACE_SECURITY_DEBUG:
            print(
                "[PAD DEBUG] "
                f"frames={score.frames_analyzed} median_real_score={score.real_score:.6f} "
                f"latency_ms={score.latency_ms:.2f}"
            )

    return CaptureSummary(captured=captured, usable=usable, rejected=rejected)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Backward-compatible destination for one explicit attempt.",
    )
    parser.add_argument(
        "--pad-root",
        type=Path,
        default=DEFAULT_PAD_ROOT,
        help="Private local PAD dataset root used when --output is omitted.",
    )
    parser.add_argument("--label", choices=("real", "spoof"))
    parser.add_argument("--spoof-type", default="phone_static")
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--countdown", type=int, default=3)
    args = parser.parse_args()

    if args.output is None and args.label is None:
        parser.error("Provide --label real or --label spoof when --output is omitted.")
    if args.output is not None and args.attempts != 1:
        parser.error("--output supports one attempt; use --pad-root for multiple attempts.")
    if args.frames < get_settings().FACE_ANTI_SPOOF_MIN_VALID_FRAMES:
        parser.error(
            "--frames must meet FACE_ANTI_SPOOF_MIN_VALID_FRAMES "
            f"({get_settings().FACE_ANTI_SPOOF_MIN_VALID_FRAMES})."
        )
    if args.attempts < 1:
        parser.error("--attempts must be at least 1.")
    if args.seconds <= 0:
        parser.error("--seconds must be greater than zero.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.spoof_type):
        parser.error("--spoof-type may contain letters, numbers, underscores, and hyphens only.")
    return args


def main() -> int:
    args = _parse_args()
    label = args.label or "evaluation"
    output = resolve_project_path(args.output) if args.output is not None else None
    pad_root = resolve_project_path(args.pad_root)
    if output is not None and output.exists() and any(output.iterdir()):
        raise ValueError("The output attempt directory must be new or empty.")

    source = _camera_source()
    rotate = _rotation_setting()
    flip = _flip_setting()
    print(f"Camera source: {source}")
    print(f"Private PAD root: {pad_root}")
    print(f"Frames per attempt: {args.frames}")
    print(f"Capture seconds: {args.seconds}")
    print("Captured samples stay local and are ignored by Git.")

    capture = _open_camera(source)
    if not capture.isOpened():
        raise RuntimeError(_camera_open_error(source))
    reader = CameraFrameReader(
        capture,
        rotate=rotate,
        flip=flip,
        unavailable_after=max(3, _int_env("LIVE_CAMERA_MAX_READ_FAILURES", 30)),
        stale_after_seconds=_camera_stale_seconds(),
        debug=get_settings().FACE_SECURITY_DEBUG,
    ).start()

    try:
        service = OnnxFaceAntiSpoofingService(
            detector=MTCNNFaceDetector(alignment_enabled=False),
            require_calibration=False,
        )
        summary = _capture_attempts(
            reader=reader,
            service=service,
            attempts=args.attempts,
            frames_per_attempt=args.frames,
            seconds=args.seconds,
            countdown=args.countdown,
            output=output,
            pad_root=pad_root,
            label=label,
            spoof_type=args.spoof_type,
        )
    except CaptureAborted:
        print("Capture aborted. No partial attempt was saved.")
        return 1
    finally:
        reader.close()
        cv2.destroyAllWindows()

    print("\nCapture summary")
    print(f"Attempts captured: {summary.captured}")
    print(f"Attempts usable: {summary.usable}")
    print(f"Attempts rejected: {summary.rejected}")
    return 0 if summary.usable > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
