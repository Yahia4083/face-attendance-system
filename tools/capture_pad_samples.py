import cv2
import sys
import time
from pathlib import Path

MODE = sys.argv[1].lower() if len(sys.argv) > 1 else "real"
ATTEMPTS = int(sys.argv[2]) if len(sys.argv) > 2 else 10

if MODE not in {"real", "spoof"}:
    raise SystemExit("Usage: python capture_pad_samples.py real|spoof [attempts]")

CAMERA_SOURCE = 0
FRAMES_PER_ATTEMPT = 12
CAPTURE_SECONDS = 4.0

root = Path("storage/evaluation/pad_calibration") / MODE
root.mkdir(parents=True, exist_ok=True)

cap = cv2.VideoCapture(CAMERA_SOURCE)

if not cap.isOpened():
    raise SystemExit("Could not open camera.")

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

print()
print(f"PAD CALIBRATION CAPTURE - {MODE.upper()}")
print(f"Attempts required: {ATTEMPTS}")
print()
print("SPACE = capture next attempt")
print("Q     = quit")
print()

attempt = 1

while attempt <= ATTEMPTS:
    ok, frame = cap.read()
    if not ok or frame is None:
        continue

    preview = frame.copy()

    cv2.putText(
        preview,
        f"{MODE.upper()} - Attempt {attempt}/{ATTEMPTS}",
        (30, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        preview,
        "Press SPACE to capture",
        (30, 95),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.imshow("PAD Calibration Capture", preview)

    key = cv2.waitKey(1) & 0xFF

    if key in (ord("q"), ord("Q")):
        break

    if key == 32:
        attempt_dir = root / f"attempt_{attempt:03d}"
        attempt_dir.mkdir(parents=True, exist_ok=True)

        print(f"Capturing attempt {attempt}/{ATTEMPTS}...")

        interval = CAPTURE_SECONDS / FRAMES_PER_ATTEMPT

        for frame_index in range(1, FRAMES_PER_ATTEMPT + 1):
            started = time.time()

            ok, captured = cap.read()
            if ok and captured is not None:
                path = attempt_dir / f"frame_{frame_index:03d}.jpg"
                cv2.imwrite(
                    str(path),
                    captured,
                    [cv2.IMWRITE_JPEG_QUALITY, 95],
                )

            elapsed = time.time() - started
            if elapsed < interval:
                time.sleep(interval - elapsed)

        print(f"Saved: {attempt_dir}")
        attempt += 1
        time.sleep(0.6)

cap.release()
cv2.destroyAllWindows()

print()
print("Capture finished.")
