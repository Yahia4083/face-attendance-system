"""Capture recognition and active head-turn experiments without changing attendance.

The tool calls the same MTCNN, FaceNet, recognition policy, and active-liveness
services used by the application.  It writes one de-identified CSV row per
attempt and never invokes an attendance use case.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import time
from typing import Any
from uuid import uuid4

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings, resolve_project_path  # noqa: E402
from app.domain.services.liveness_service import (  # noqa: E402
    LivenessFrame,
    LivenessValidationRequest,
)
from app.infrastructure.database.connection import SessionLocal  # noqa: E402
from app.infrastructure.database.repositories.sql_employee_repository import (  # noqa: E402
    SqlEmployeeRepository,
)
from app.infrastructure.database.repositories.sql_face_embedding_repository import (  # noqa: E402
    SqlFaceEmbeddingRepository,
)
from app.infrastructure.face_ai.facenet_embedder import FaceNetEmbedder  # noqa: E402
from app.infrastructure.face_ai.facenet_recognition_service import (  # noqa: E402
    FaceNetRecognitionService,
)
from app.infrastructure.face_ai.image_validator import ImageValidator  # noqa: E402
from app.infrastructure.face_ai.mtcnn_face_detector import MTCNNFaceDetector  # noqa: E402
from app.infrastructure.face_ai.simple_liveness_service import (  # noqa: E402
    SimpleLivenessService,
)
from tools.live_mobile_attendance_kiosk import (  # noqa: E402
    CameraFrameSnapshot,
    CameraFrameReader,
    _camera_recovery_seconds,
    _camera_source,
    _camera_stale_seconds,
    _flip_setting,
    _int_env,
    _open_camera,
    _rotation_setting,
)


WINDOW_NAME = "Biometric Research Experiment"
DEFAULT_OUTPUT = Path("storage/evaluation/active_experiments/attempts.csv")
DEFAULT_DATASET_ROOT = Path("storage/evaluation/active_experiments/frames")
JPEG_QUALITY = 92
UNKNOWN_IDENTITY = "UNKNOWN"

CONDITIONS = (
    "frontal",
    "pose_left",
    "pose_right",
    "different_lighting",
    "near",
    "far",
    "glasses",
    "hairstyle",
    "unknown",
)
LIVENESS_SCENARIOS = (
    "correct",
    "wrong_direction",
    "no_movement",
    "phone_photo",
)

CSV_FIELDS = (
    "attempt_id",
    "captured_at_utc",
    "session_id",
    "mode",
    "participant_id",
    "enrollment_status",
    "expected_identity",
    "condition",
    "scenario",
    "challenge",
    "performed_action",
    "expected_decision",
    "acquisition_result",
    "failure_reason",
    "liveness_pass",
    "liveness_confidence",
    "liveness_failure_reason",
    "predicted_identity",
    "best_score",
    "second_best_score",
    "accepted",
    "outcome",
    "frames_analyzed",
    "capture_ms",
    "processing_ms",
    "total_ms",
    "camera_source",
    "resolution",
    "saved_frame_directory",
    "notes",
)


class CaptureAborted(Exception):
    """Stop an interactive session without writing a partial attempt."""


class RecoveringCameraReader:
    """Keep an experiment window alive while a virtual camera reconnects.

    Camo and some Windows camera drivers can briefly stop delivering frames
    after another experiment process releases the device.  The attendance
    kiosk already recovers from that state; research capture needs the same
    behavior because each condition is intentionally run as a separate command.
    """

    def __init__(
        self,
        camera_source: int | str,
        *,
        rotate: int,
        flip: bool,
        unavailable_after: int,
        stale_after_seconds: float,
        recovery_seconds: float,
        debug: bool = False,
        open_camera=None,
    ) -> None:
        self._camera_source = camera_source
        self._rotate = rotate
        self._flip = flip
        self._unavailable_after = unavailable_after
        self._stale_after_seconds = stale_after_seconds
        self._recovery_seconds = recovery_seconds
        self._debug = debug
        self._open_camera_override = open_camera
        self._next_windows_backend = 0
        self._active_backend = "default"
        self._reader: CameraFrameReader | None = None
        self._next_recovery_at = 0.0
        self._last_frame: np.ndarray | None = None
        self._sequence_offset = 0
        self._last_inner_sequence = 0
        self._closed = False

    def start(self) -> "RecoveringCameraReader":
        self._try_reopen(now=time.monotonic())
        return self

    def snapshot(self, *, now: float | None = None) -> CameraFrameSnapshot:
        now = time.monotonic() if now is None else now
        if self._closed:
            return self._unavailable_snapshot()

        if self._reader is not None:
            snapshot = self._reader.snapshot(now=now)
            self._last_inner_sequence = snapshot.sequence
            if snapshot.frame is not None:
                self._last_frame = snapshot.frame
            if snapshot.camera_available:
                return CameraFrameSnapshot(
                    frame=snapshot.frame,
                    sequence=self._sequence_offset + snapshot.sequence,
                    camera_available=True,
                    consecutive_failures=snapshot.consecutive_failures,
                )
            self._drop_stale_reader(now=now)

        if now >= self._next_recovery_at:
            self._try_reopen(now=now)
            if self._reader is not None:
                snapshot = self._reader.snapshot(now=now)
                self._last_inner_sequence = snapshot.sequence
                if snapshot.frame is not None:
                    self._last_frame = snapshot.frame
                return CameraFrameSnapshot(
                    frame=snapshot.frame,
                    sequence=self._sequence_offset + snapshot.sequence,
                    camera_available=snapshot.camera_available,
                    consecutive_failures=snapshot.consecutive_failures,
                )

        return self._unavailable_snapshot()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader is not None:
            self._reader.close()
            self._reader = None

    def _drop_stale_reader(self, *, now: float) -> None:
        if self._reader is None:
            return
        self._reader.close()
        self._reader = None
        self._sequence_offset += self._last_inner_sequence
        self._last_inner_sequence = 0
        self._next_recovery_at = now + self._recovery_seconds
        print(
            f"[camera] Frame stream stopped; reconnecting automatically in "
            f"{self._recovery_seconds:g} second(s)."
        )

    def _try_reopen(self, *, now: float) -> None:
        capture = self._open_capture()
        if capture is None or not capture.isOpened():
            if capture is not None:
                capture.release()
            self._next_recovery_at = now + self._recovery_seconds
            if self._debug:
                print("[camera] Reconnect attempt did not open the device.")
            return

        self._reader = CameraFrameReader(
            capture,
            rotate=self._rotate,
            flip=self._flip,
            unavailable_after=self._unavailable_after,
            stale_after_seconds=self._stale_after_seconds,
            debug=self._debug,
        ).start()
        self._next_recovery_at = now + self._recovery_seconds
        print(f"[camera] Camera connection opened ({self._active_backend}).")

    def _open_capture(self):
        if self._open_camera_override is not None:
            self._active_backend = "test/custom"
            return self._open_camera_override(self._camera_source)

        if sys.platform == "win32" and isinstance(self._camera_source, int):
            backends = (
                ("DirectShow", cv2.CAP_DSHOW),
                ("Media Foundation", cv2.CAP_MSMF),
            )
            start = self._next_windows_backend
            last_capture = None
            for offset in range(len(backends)):
                index = (start + offset) % len(backends)
                backend_name, backend = backends[index]
                capture = cv2.VideoCapture(self._camera_source, backend)
                last_capture = capture
                if capture.isOpened():
                    # If this backend opens but later delivers no usable frames,
                    # the next controlled recovery starts with the other backend.
                    self._next_windows_backend = (index + 1) % len(backends)
                    self._active_backend = backend_name
                    return capture
                capture.release()
            self._next_windows_backend = (start + 1) % len(backends)
            return last_capture

        self._active_backend = "OpenCV default"
        return _open_camera(self._camera_source)

    def _unavailable_snapshot(self) -> CameraFrameSnapshot:
        return CameraFrameSnapshot(
            frame=self._last_frame,
            sequence=self._sequence_offset,
            camera_available=False,
            consecutive_failures=self._unavailable_after,
        )


def recognition_outcome(
    *,
    expected_identity: str,
    accepted: bool,
    predicted_identity: str,
    acquisition_result: str,
) -> str:
    """Classify a one-to-many recognition attempt for later metric calculation."""

    if acquisition_result != "usable":
        return "ACQUISITION_FAILURE"
    if expected_identity == UNKNOWN_IDENTITY:
        return "FALSE_ACCEPT" if accepted else "TRUE_REJECT"
    if accepted and predicted_identity == expected_identity:
        return "TRUE_ACCEPT"
    if accepted:
        return "MISIDENTIFICATION"
    return "FALSE_REJECT"


def liveness_outcome(*, expected_decision: str, passed: bool, usable: bool) -> str:
    """Classify an active challenge attempt against its predeclared test oracle."""

    if not usable:
        return "ACQUISITION_FAILURE"
    if expected_decision == "accept":
        return "CORRECT_ACCEPT" if passed else "UNEXPECTED_REJECT"
    return "UNEXPECTED_ACCEPT" if passed else "CORRECT_REJECT"


def _bool_text(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _number_text(value: float | int | None, digits: int = 6) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def _new_attempt_id(mode: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{mode[:3].upper()}-{timestamp}-{uuid4().hex[:6]}"


def _preview_canvas(frame: np.ndarray | None, message: str) -> np.ndarray:
    canvas = frame.copy() if frame is not None else np.zeros((720, 1280, 3), dtype=np.uint8)
    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 78), (15, 23, 42), -1)
    cv2.putText(
        canvas,
        message,
        (20, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.68,
        (240, 245, 255),
        2,
        cv2.LINE_AA,
    )
    return canvas


def _wait_for_space(reader: RecoveringCameraReader, message: str) -> None:
    while True:
        snapshot = reader.snapshot()
        if not snapshot.camera_available:
            status = "Camera reconnecting automatically - Q to abort"
        elif snapshot.frame is None:
            status = "Waiting for camera image - Q to abort"
        else:
            status = message
        cv2.imshow(WINDOW_NAME, _preview_canvas(snapshot.frame, status))
        key = cv2.waitKey(10) & 0xFF
        if key == ord(" ") and snapshot.camera_available and snapshot.frame is not None:
            return
        if key in {ord("q"), ord("Q")}:
            raise CaptureAborted


def _show_countdown(reader: RecoveringCameraReader, seconds: int, instruction: str) -> None:
    for remaining in range(max(0, seconds), 0, -1):
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            snapshot = reader.snapshot()
            cv2.imshow(
                WINDOW_NAME,
                _preview_canvas(snapshot.frame, f"{instruction} - starts in {remaining}"),
            )
            if cv2.waitKey(10) & 0xFF in {ord("q"), ord("Q")}:
                raise CaptureAborted


def _encode_frame(frame: np.ndarray) -> bytes:
    encoded, buffer = cv2.imencode(
        ".jpg",
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
    )
    if not encoded:
        raise RuntimeError("The camera frame could not be encoded as JPEG.")
    return buffer.tobytes()


def _capture_single_frame(reader: RecoveringCameraReader) -> tuple[list[bytes], str, float]:
    started = time.perf_counter()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        snapshot = reader.snapshot()
        cv2.imshow(WINDOW_NAME, _preview_canvas(snapshot.frame, "CAPTURING RECOGNITION PROBE"))
        if cv2.waitKey(5) & 0xFF in {ord("q"), ord("Q")}:
            raise CaptureAborted
        if snapshot.camera_available and snapshot.frame is not None:
            height, width = snapshot.frame.shape[:2]
            return [_encode_frame(snapshot.frame)], f"{width}x{height}", (time.perf_counter() - started) * 1000.0
    return [], "", (time.perf_counter() - started) * 1000.0


def _capture_sequence(
    reader: RecoveringCameraReader,
    *,
    frame_count: int,
    seconds: float,
    instruction: str,
) -> tuple[list[bytes], str, float]:
    started_perf = time.perf_counter()
    started = time.monotonic()
    next_sample = started
    last_sequence = -1
    interval = seconds / frame_count
    frames: list[bytes] = []
    resolution = ""

    while len(frames) < frame_count and time.monotonic() - started <= seconds + 2.0:
        now = time.monotonic()
        snapshot = reader.snapshot(now=now)
        cv2.imshow(
            WINDOW_NAME,
            _preview_canvas(
                snapshot.frame,
                f"{instruction} - frame {len(frames)}/{frame_count}",
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
            height, width = snapshot.frame.shape[:2]
            resolution = f"{width}x{height}"
            frames.append(_encode_frame(snapshot.frame))
            last_sequence = snapshot.sequence
            next_sample = started + len(frames) * interval

    return frames, resolution, (time.perf_counter() - started_perf) * 1000.0


def _save_attempt_frames(root: Path, attempt_id: str, frames: list[bytes], row: dict[str, str]) -> Path:
    destination = root / attempt_id
    destination.mkdir(parents=True, exist_ok=False)
    for index, content in enumerate(frames, start=1):
        (destination / f"frame_{index:03d}.jpg").write_bytes(content)
    (destination / "metadata.json").write_text(
        json.dumps(row, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return destination


def _append_row(path: Path, row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def _base_row(args: argparse.Namespace, *, mode: str, attempt_id: str) -> dict[str, str]:
    return {
        field: "" for field in CSV_FIELDS
    } | {
        "attempt_id": attempt_id,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "session_id": args.session_id,
        "mode": mode,
        "participant_id": args.participant_id,
        "camera_source": str(_camera_source()),
        "notes": args.notes or "",
    }


def _recognition_instruction(condition: str) -> str:
    instructions = {
        "frontal": "FACE FRONT - neutral expression",
        "pose_left": "SLIGHT LEFT POSE - keep both eyes visible",
        "pose_right": "SLIGHT RIGHT POSE - keep both eyes visible",
        "different_lighting": "USE THE PREPARED LIGHTING CONDITION",
        "near": "USE THE MARKED NEAR DISTANCE",
        "far": "USE THE MARKED FAR DISTANCE",
        "glasses": "WEAR THE RECORDED GLASSES CONDITION",
        "hairstyle": "USE THE RECORDED HAIRSTYLE CONDITION",
        "unknown": "UNENROLLED PARTICIPANT - face front",
    }
    return instructions[condition]


def _run_recognition_attempts(
    args: argparse.Namespace,
    *,
    reader: RecoveringCameraReader,
    output: Path,
    dataset_root: Path,
) -> int:
    database = SessionLocal()
    try:
        employee_repo = SqlEmployeeRepository(database)
        expected_identity = args.expected_employee_number.strip()
        if expected_identity.upper() == UNKNOWN_IDENTITY:
            expected_identity = UNKNOWN_IDENTITY
            enrollment_status = "unknown"
            if args.condition != "unknown":
                print("[NOTE] Unknown probes are normally recorded with --condition unknown.")
        else:
            employee = employee_repo.get_by_employee_number(expected_identity)
            if employee is None:
                raise ValueError(
                    f"No employee has employee number {expected_identity!r}. Enroll the person first."
                )
            expected_identity = str(employee.employee_number)
            enrollment_status = "enrolled"

        detector = MTCNNFaceDetector()
        recognition_service = FaceNetRecognitionService(
            image_validator=ImageValidator(),
            detector=detector,
            embedder=FaceNetEmbedder(),
            face_embedding_repo=SqlFaceEmbeddingRepository(database),
        )

        for index in range(1, args.attempts + 1):
            attempt_id = _new_attempt_id("recognition")
            print(f"\nRecognition attempt {index}/{args.attempts}: {attempt_id}")
            print("Press SPACE only when the declared condition is ready. Q aborts the session.")
            instruction = _recognition_instruction(args.condition)
            _wait_for_space(reader, f"{instruction} - SPACE to start")
            _show_countdown(reader, args.countdown, instruction)
            frames, resolution, capture_ms = _capture_single_frame(reader)
            row = _base_row(args, mode="recognition", attempt_id=attempt_id)
            row.update(
                {
                    "enrollment_status": enrollment_status,
                    "expected_identity": expected_identity,
                    "condition": args.condition,
                    "scenario": "recognition_probe",
                    "performed_action": args.condition,
                    "expected_decision": "reject" if expected_identity == UNKNOWN_IDENTITY else "accept_correct_identity",
                    "resolution": resolution,
                    "capture_ms": _number_text(capture_ms, 2),
                    "frames_analyzed": str(len(frames)),
                }
            )

            processing_started = time.perf_counter()
            accepted = False
            predicted_identity = "REJECT"
            best_score: float | None = None
            second_best_score: float | None = None
            acquisition_result = "camera_failure" if not frames else "usable"
            failure_reason = ""
            if frames:
                try:
                    result = recognition_service.recognize(
                        image_bytes=frames[0],
                        original_filename=f"{attempt_id}.jpg",
                    )
                    accepted = result.matched
                    best_score = result.similarity_score
                    second_best_score = result.second_best_score
                    failure_reason = result.failure_reason or ""
                    if result.matched and result.employee_id is not None:
                        predicted = employee_repo.get_by_id(result.employee_id)
                        predicted_identity = (
                            str(predicted.employee_number) if predicted is not None else f"EMPLOYEE_ID_{result.employee_id}"
                        )
                except ValueError as error:
                    acquisition_result = "processing_rejected"
                    failure_reason = str(error)
                except RuntimeError as error:
                    acquisition_result = "processing_error"
                    failure_reason = str(error)
            processing_ms = (time.perf_counter() - processing_started) * 1000.0
            outcome = recognition_outcome(
                expected_identity=expected_identity,
                accepted=accepted,
                predicted_identity=predicted_identity,
                acquisition_result=acquisition_result,
            )
            row.update(
                {
                    "acquisition_result": acquisition_result,
                    "failure_reason": failure_reason,
                    "predicted_identity": predicted_identity,
                    "best_score": _number_text(best_score),
                    "second_best_score": _number_text(second_best_score),
                    "accepted": _bool_text(accepted),
                    "outcome": outcome,
                    "processing_ms": _number_text(processing_ms, 2),
                    "total_ms": _number_text(capture_ms + processing_ms, 2),
                }
            )
            if args.save_frames and frames:
                destination = _save_attempt_frames(dataset_root, attempt_id, frames, row)
                row["saved_frame_directory"] = str(destination)
            _append_row(output, row)
            print(
                f"[{outcome}] expected={expected_identity} predicted={predicted_identity} "
                f"score={row['best_score'] or 'n/a'} processing_ms={row['processing_ms']}"
            )
    finally:
        database.close()
    return 0


def _challenge_value(option: str) -> str:
    if option == "left":
        return "TURN_HEAD_LEFT"
    if option == "right":
        return "TURN_HEAD_RIGHT"
    return random.SystemRandom().choice(("TURN_HEAD_LEFT", "TURN_HEAD_RIGHT"))


def _scenario_instruction(scenario: str, challenge: str) -> tuple[str, str, str]:
    requested = "LEFT" if challenge == "TURN_HEAD_LEFT" else "RIGHT"
    opposite = "RIGHT" if requested == "LEFT" else "LEFT"
    if scenario == "correct":
        return f"NOW TURN {requested}", requested.lower(), "accept"
    if scenario == "wrong_direction":
        return f"INTENTIONALLY TURN {opposite}", opposite.lower(), "reject"
    if scenario == "no_movement":
        return "KEEP YOUR HEAD STILL", "none", "reject"
    return "KEEP THE PHONE PHOTO STATIC", "phone_photo", "reject"


def _run_liveness_attempts(
    args: argparse.Namespace,
    *,
    reader: RecoveringCameraReader,
    output: Path,
    dataset_root: Path,
) -> int:
    service = SimpleLivenessService(
        detector=MTCNNFaceDetector(),
        hardened_mode=get_settings().LIVE_LIVENESS_HARDENED_MODE,
    )
    for index in range(1, args.attempts + 1):
        attempt_id = _new_attempt_id("liveness")
        challenge = _challenge_value(args.challenge)
        instruction, performed_action, expected_decision = _scenario_instruction(
            args.scenario,
            challenge,
        )
        print(f"\nActive-liveness attempt {index}/{args.attempts}: {attempt_id}")
        print(f"Generated challenge: {challenge}. Test scenario: {args.scenario}.")
        print("Start facing forward. Press SPACE when ready; perform only the declared scenario.")
        _wait_for_space(reader, f"{challenge} / {args.scenario} - SPACE to start")
        _show_countdown(reader, args.countdown, "START FROM A FRONTAL POSITION")
        frames, resolution, capture_ms = _capture_sequence(
            reader,
            frame_count=args.frames,
            seconds=args.seconds,
            instruction=instruction,
        )
        row = _base_row(args, mode="liveness", attempt_id=attempt_id)
        row.update(
            {
                "enrollment_status": args.enrollment_status,
                "condition": args.condition,
                "scenario": args.scenario,
                "challenge": challenge,
                "performed_action": performed_action,
                "expected_decision": expected_decision,
                "resolution": resolution,
                "capture_ms": _number_text(capture_ms, 2),
            }
        )

        usable = len(frames) == args.frames
        passed = False
        confidence: float | None = None
        frames_analyzed = len(frames)
        failure_reason = ""
        processing_started = time.perf_counter()
        if usable:
            result = service.validate(
                LivenessValidationRequest(
                    frames=[
                        LivenessFrame(filename=f"frame_{item_index:03d}.jpg", content=content)
                        for item_index, content in enumerate(frames, start=1)
                    ],
                    challenge_type=challenge,
                )
            )
            passed = result.passed
            confidence = result.confidence
            frames_analyzed = result.frames_analyzed
            failure_reason = result.failure_reason or ""
        else:
            failure_reason = f"Camera supplied {len(frames)}/{args.frames} frames."
        processing_ms = (time.perf_counter() - processing_started) * 1000.0
        outcome = liveness_outcome(
            expected_decision=expected_decision,
            passed=passed,
            usable=usable,
        )
        row.update(
            {
                "acquisition_result": "usable" if usable else "camera_failure",
                "failure_reason": failure_reason,
                "liveness_pass": _bool_text(passed),
                "liveness_confidence": _number_text(confidence),
                "liveness_failure_reason": failure_reason,
                "accepted": _bool_text(passed),
                "outcome": outcome,
                "frames_analyzed": str(frames_analyzed),
                "processing_ms": _number_text(processing_ms, 2),
                "total_ms": _number_text(capture_ms + processing_ms, 2),
            }
        )
        if args.save_frames and frames:
            destination = _save_attempt_frames(dataset_root, attempt_id, frames, row)
            row["saved_frame_directory"] = str(destination)
        _append_row(output, row)
        print(
            f"[{outcome}] challenge={challenge} pass={row['liveness_pass']} "
            f"confidence={row['liveness_confidence'] or 'n/a'} processing_ms={row['processing_ms']}"
        )
    return 0


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--participant-id", required=True, help="Pseudonymous code such as P01 or U01.")
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--countdown", type=int, default=3)
    parser.add_argument("--session-id", default=datetime.now(timezone.utc).strftime("S%Y%m%dT%H%M%SZ"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument(
        "--save-frames",
        action="store_true",
        help="Save private camera frames locally. Use only with documented consent.",
    )
    parser.add_argument("--notes")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    recognition = subparsers.add_parser("recognition", help="Capture independent recognition probes.")
    _add_common_arguments(recognition)
    recognition.add_argument("--expected-employee-number", required=True, help="Enrolled employee number or UNKNOWN.")
    recognition.add_argument("--condition", choices=CONDITIONS, required=True)

    liveness = subparsers.add_parser("liveness", help="Capture active head-turn challenge trials.")
    _add_common_arguments(liveness)
    liveness.set_defaults(attempts=20)
    liveness.add_argument("--scenario", choices=LIVENESS_SCENARIOS, required=True)
    liveness.add_argument("--challenge", choices=("auto", "left", "right"), default="auto")
    liveness.add_argument("--frames", type=int, default=8)
    liveness.add_argument("--seconds", type=float, default=3.0)
    liveness.add_argument("--condition", default="normal")
    liveness.add_argument("--enrollment-status", choices=("enrolled", "unknown"), default="enrolled")

    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be at least 1.")
    if args.countdown < 0:
        parser.error("--countdown cannot be negative.")
    if args.mode == "liveness":
        if args.frames < 8 or args.frames > 30:
            parser.error("--frames must be between 8 and 30 for the current liveness service.")
        if args.seconds <= 0:
            parser.error("--seconds must be greater than zero.")
    return args


def main() -> int:
    args = _parse_args()
    output = resolve_project_path(args.output)
    dataset_root = resolve_project_path(args.dataset_root)
    source = _camera_source()
    print("Biometric research capture (no attendance records will be created)")
    print(f"Mode: {args.mode}")
    print(f"Camera source: {source}")
    print(f"CSV output: {output}")
    print(f"Frames saved: {'YES - private local dataset' if args.save_frames else 'NO'}")

    reader = RecoveringCameraReader(
        source,
        rotate=_rotation_setting(),
        flip=_flip_setting(),
        unavailable_after=max(3, _int_env("LIVE_CAMERA_MAX_READ_FAILURES", 30)),
        stale_after_seconds=_camera_stale_seconds(),
        recovery_seconds=_camera_recovery_seconds(),
        debug=False,
    ).start()
    try:
        if args.mode == "recognition":
            return _run_recognition_attempts(
                args,
                reader=reader,
                output=output,
                dataset_root=dataset_root,
            )
        return _run_liveness_attempts(
            args,
            reader=reader,
            output=output,
            dataset_root=dataset_root,
        )
    except CaptureAborted:
        print("Capture aborted. The current partial attempt was not written.")
        return 1
    finally:
        reader.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
