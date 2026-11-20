"""Verify the active live-attendance pipeline without creating attendance."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import get_settings, resolve_project_path  # noqa: E402
from app.dependencies import (  # noqa: E402
    _get_cached_face_detector,
    _get_cached_face_embedder,
)
from app.infrastructure.face_ai.face_anti_spoofing import (  # noqa: E402
    AntiSpoofCalibration,
    _sha384,
)
from app.infrastructure.face_ai.simple_liveness_service import (  # noqa: E402
    SimpleLivenessService,
)
from tools.live_mobile_attendance_kiosk import (  # noqa: E402
    CameraFrameReader,
    _camera_source,
    _camera_stale_seconds,
    _flip_setting,
    _int_env,
    _open_camera,
    _rotation_setting,
)


@dataclass(frozen=True)
class ReadinessCheck:
    """Represent one required check or optional capability notice."""

    name: str
    passed: bool
    detail: str = ""
    required: bool = True


def _check_dependencies() -> list[ReadinessCheck]:
    """Confirm libraries required by camera, MTCNN, FaceNet, and active liveness."""

    checks: list[ReadinessCheck] = []
    for module_name in ("cv2", "numpy", "onnxruntime", "mtcnn_cv2"):
        try:
            importlib.import_module(module_name)
        except Exception as error:
            checks.append(
                ReadinessCheck(
                    f"Python dependency: {module_name}",
                    False,
                    type(error).__name__,
                )
            )
        else:
            checks.append(ReadinessCheck(f"Python dependency: {module_name}", True))
    return checks


def _check_active_biometrics() -> list[ReadinessCheck]:
    """Construct the same MTCNN, FaceNet, and liveness services used by FastAPI."""

    settings = get_settings()
    checks: list[ReadinessCheck] = []
    detector = None
    if settings.FACE_DETECTOR_BACKEND.strip().lower() != "mtcnn":
        checks.append(
            ReadinessCheck(
                "MTCNN face detector",
                False,
                f"configured backend={settings.FACE_DETECTOR_BACKEND}",
            )
        )
    else:
        try:
            detector = _get_cached_face_detector()
        except Exception as error:
            checks.append(
                ReadinessCheck(
                    "MTCNN face detector",
                    False,
                    f"{type(error).__name__}: {error}",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    "MTCNN face detector",
                    True,
                    type(detector).__name__,
                )
            )

    if settings.FACE_EMBEDDER_BACKEND.strip().lower() != "facenet":
        checks.append(
            ReadinessCheck(
                "FaceNet recognition dependencies",
                False,
                f"configured backend={settings.FACE_EMBEDDER_BACKEND}",
            )
        )
    else:
        try:
            embedder = _get_cached_face_embedder()
        except Exception as error:
            checks.append(
                ReadinessCheck(
                    "FaceNet recognition dependencies",
                    False,
                    f"{type(error).__name__}: {error}",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    "FaceNet recognition dependencies",
                    True,
                    embedder.model_name,
                )
            )

    if detector is None:
        checks.append(
            ReadinessCheck(
                "Active liveness service",
                False,
                "face detector unavailable",
            )
        )
    else:
        try:
            SimpleLivenessService(
                detector=detector,
                hardened_mode=settings.LIVE_LIVENESS_HARDENED_MODE,
            )
        except Exception as error:
            checks.append(
                ReadinessCheck(
                    "Active liveness service",
                    False,
                    f"{type(error).__name__}: {error}",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    "Active liveness service",
                    True,
                    "challenge-response enabled",
                )
            )
    return checks


def _check_optional_pad() -> ReadinessCheck:
    """Report offline PAD calibration availability without gating live attendance."""

    settings = get_settings()
    model_path = resolve_project_path(settings.FACE_ANTI_SPOOF_MODEL_PATH)
    calibration_path = resolve_project_path(settings.FACE_ANTI_SPOOF_CALIBRATION_PATH)
    if not calibration_path.is_file():
        return ReadinessCheck(
            "Passive PAD",
            False,
            "calibration not configured (optional; not enforced by current runtime)",
            required=False,
        )
    if not model_path.is_file():
        return ReadinessCheck(
            "Passive PAD",
            False,
            "model unavailable (optional; not enforced by current runtime)",
            required=False,
        )

    model_hash = _sha384(model_path)
    try:
        AntiSpoofCalibration.load(
            calibration_path,
            model_name=settings.FACE_ANTI_SPOOF_MODEL_NAME,
            model_sha384=model_hash,
        )
    except RuntimeError as error:
        return ReadinessCheck(
            "Passive PAD",
            False,
            f"optional calibration invalid: {error}",
            required=False,
        )
    return ReadinessCheck(
        "Passive PAD",
        True,
        "calibration available for offline evaluation, but not enforced by current runtime",
        required=False,
    )


def _check_camera(timeout_seconds: float) -> ReadinessCheck:
    """Confirm the configured deployment camera supplies an oriented nonblank frame."""

    source = _camera_source()
    for attempt in range(2):
        capture = _open_camera(source)
        if not capture.isOpened():
            capture.release()
            if attempt == 0:
                time.sleep(0.5)
                continue
            return ReadinessCheck("Camera opens", False, f"source={source}")

        reader = CameraFrameReader(
            capture,
            rotate=_rotation_setting(),
            flip=_flip_setting(),
            unavailable_after=max(3, _int_env("LIVE_CAMERA_MAX_READ_FAILURES", 30)),
            stale_after_seconds=_camera_stale_seconds(),
            debug=False,
        ).start()
        try:
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                snapshot = reader.snapshot()
                if snapshot.camera_available and snapshot.frame is not None:
                    height, width = snapshot.frame.shape[:2]
                    recovery = ", recovered after one reopen" if attempt else ""
                    return ReadinessCheck(
                        "Camera opens and supplies frames",
                        True,
                        f"source={source}, frame={width}x{height}{recovery}",
                    )
                time.sleep(0.05)
        finally:
            reader.close()

        if attempt == 0:
            time.sleep(0.5)

    return ReadinessCheck(
        "Camera opens and supplies frames",
        False,
        f"source={source}; no valid frame after two {timeout_seconds:.1f}s attempts",
    )


def _required_checks_pass(checks: list[ReadinessCheck]) -> bool:
    """Exclude optional future capabilities from current runtime readiness."""

    return all(check.passed for check in checks if check.required)


def run_checks(*, check_camera: bool, camera_timeout: float) -> list[ReadinessCheck]:
    """Run non-mutating checks in current live-attendance dependency order."""

    checks = _check_dependencies()
    checks.extend(_check_active_biometrics())
    if check_camera:
        checks.append(_check_camera(camera_timeout))
    else:
        checks.append(
            ReadinessCheck(
                "Camera",
                True,
                "check skipped for CI",
                required=False,
            )
        )
    checks.append(_check_optional_pad())
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-camera",
        action="store_true",
        help="Skip only the physical camera check for CI.",
    )
    parser.add_argument("--camera-timeout", type=float, default=10.0)
    args = parser.parse_args()
    if args.camera_timeout <= 0:
        parser.error("--camera-timeout must be greater than zero.")

    print("Live attendance readiness check (read-only)\n")
    checks = run_checks(
        check_camera=not args.skip_camera,
        camera_timeout=args.camera_timeout,
    )
    for check in checks:
        marker = "INFO" if not check.required else ("PASS" if check.passed else "FAIL")
        suffix = f" - {check.detail}" if check.detail else ""
        print(f"[{marker}] {check.name}{suffix}")

    ready = _required_checks_pass(checks)
    print("\nPassive presentation-attack detection is not enforced by current live attendance.")
    print(f"LIVE ATTENDANCE READY: {'YES' if ready else 'NO'}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
