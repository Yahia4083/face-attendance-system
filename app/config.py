"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_project_path(value: str | Path) -> Path:
    """Resolve project-owned files independently of the process working directory."""

    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (PROJECT_ROOT / path).resolve()


class Settings(BaseSettings):
    """Centralized app settings."""

    APP_NAME: str = "Attendance Face Recognition System"
    APP_VERSION: str = "1.0.0"
    APP_DEBUG: bool = False
    APP_TIMEZONE: str = "Africa/Tripoli"

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "attendance_face_system"
    DATABASE_URL: str = "mysql+pymysql://root:@localhost:3306/attendance_face_system"

    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALGORITHM: str = "HS256"
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = ""

    STORAGE_PATH: str = "./storage"
    FACE_DETECTOR_BACKEND: str = "mtcnn"
    FACE_EMBEDDER_BACKEND: str = "facenet"
    FACE_DEBUG_MODE: bool = False
    FACE_DETECTION_CONFIDENCE_THRESHOLD: float = 0.95
    FACE_MTCNN_MIN_FACE_SIZE: int = 40
    FACE_MTCNN_SCALE_FACTOR: float = 0.709
    FACE_ALIGNMENT_ENABLED: bool = False
    FACE_ENROLLMENT_QUALITY_ENABLED: bool = True
    FACE_RECOMMENDED_ENROLLMENT_IMAGES: int = 5
    FACE_ENROLLMENT_MIN_FACE_AREA_RATIO: float = 0.04
    FACE_ENROLLMENT_MIN_BLUR_SCORE: float = 45.0
    FACE_ENROLLMENT_MAX_ROLL_DEGREES: float = 20.0
    FACE_ENROLLMENT_MAX_YAW_PROXY: float = 0.35
    FACE_REQUIRE_SAME_PERSON_VALIDATION: bool = True
    FACE_MIN_ENROLLMENT_IMAGES: int = 2
    FACE_MAX_ENROLLMENT_IMAGES: int = 10
    FACE_SIMILARITY_THRESHOLD: float = 0.75
    FACE_FACENET_DEVICE: str = "cpu"
    FACE_FACENET_MODEL_PATH: str = "./storage/models/facenet/facenet.onnx"
    FACE_FACENET_MODEL_NAME: str = "facenet-onnx-512d-haikalmumtaz-v1"
    FACE_DETECTION_SCALE_FACTOR: float = 1.1
    FACE_DETECTION_MIN_NEIGHBORS: int = 7
    FACE_DETECTION_IOU_THRESHOLD: float = 0.45
    FACE_RECOGNITION_THRESHOLD: float = 0.75
    FACE_RECOGNITION_AMBIGUITY_MARGIN: float = 0.05
    FACE_RECOGNITION_AGGREGATION: str = "centroid"
    FACE_RECOGNITION_TOP_K: int = 3
    FACE_RECOGNITION_CALIBRATION_PATH: str = ""
    # Offline PAD evaluation metadata; passive PAD is not wired into live attendance.
    FACE_ANTI_SPOOF_MODEL_PATH: str = "./storage/models/anti_spoof/anti-spoof-mn3.onnx"
    FACE_ANTI_SPOOF_MODEL_NAME: str = "openvino-anti-spoof-mn3-onnx"
    FACE_ANTI_SPOOF_MODEL_SHA384: str = (
        "6de4534964b723397b3e8c995cadcf43bc007cc2f9930b95a"
        "e25f76adccece5d1d4d058d0b15117b9e4a9f758424f92a"
    )
    FACE_ANTI_SPOOF_CALIBRATION_PATH: str = (
        "./storage/models/anti_spoof/local-calibration.json"
    )
    FACE_ANTI_SPOOF_SAMPLE_FRAMES: int = 8
    FACE_ANTI_SPOOF_MIN_VALID_FRAMES: int = 4
    FACE_SECURITY_DEBUG: bool = False
    ALLOW_UNSCHEDULED_ATTENDANCE: bool = True
    ATTENDANCE_EARLY_CHECK_IN_WINDOW_MINUTES: int = 60
    ATTENDANCE_SAVE_CAPTURED_IMAGES: bool = False
    ATTENDANCE_PROCESSING_DELAY_MINUTES: int = 30
    MISSING_CHECKOUT_DELAY_MINUTES: int = 240
    ATTENDANCE_AUTO_PROCESSING_ENABLED: bool = True
    ATTENDANCE_AUTO_PROCESSING_INTERVAL_SECONDS: int = 60
    ATTENDANCE_AUTO_PROCESSING_LOOKBACK_DAYS: int = 7
    OVERTIME_MINIMUM_MINUTES: int = 30
    JUSTIFICATION_MIN_REASON_LENGTH: int = 10
    JUSTIFICATION_MAX_REASON_LENGTH: int = 1000
    JUSTIFICATION_MONTHLY_LIMIT: int = 3
    OVERTIME_MIN_REASON_LENGTH: int = 10
    OVERTIME_MAX_REASON_LENGTH: int = 1000
    REPORT_EXPORT_MAX_DATE_RANGE_DAYS: int = 366
    REPORT_EXPORT_DEFAULT_FORMAT: str = "csv"
    REPORT_EXPORT_CSV_ENCODING: str = "utf-8-sig"
    MOBILE_CAMERA_SOURCE: str = ""
    MOBILE_CAMERA_STREAM_URL: str = "http://127.0.0.1:8080/video"
    LIVE_ATTENDANCE_API_BASE_URL: str = "http://127.0.0.1:55000"
    # Safe presentation-only options shared with the standalone OpenCV kiosk worker.
    LIVE_KIOSK_WIDTH: int = 1280
    LIVE_KIOSK_HEIGHT: int = 720
    LIVE_KIOSK_FULLSCREEN: bool = False
    LIVE_KIOSK_PRESENTATION_MODE: bool = True
    LIVE_KIOSK_DEBUG: bool = False
    LIVE_KIOSK_BRAND: str = "Face Attendance"
    LIVE_ATTENDANCE_MIN_FRAMES: int = 8
    LIVE_ATTENDANCE_MAX_FRAMES: int = 30
    LIVE_ATTENDANCE_MIN_MOTION_SCORE: float = 2.0
    LIVE_ATTENDANCE_BLINK_CHANGE_THRESHOLD: float = 5.0
    LIVE_ATTENDANCE_TURN_CHANGE_THRESHOLD: float = 0.025
    LIVE_ATTENDANCE_MIN_CHALLENGE_CONFIDENCE: float = 0.55
    # Optional stricter landmark mode; disabled to preserve the proven kiosk flow.
    LIVE_LIVENESS_HARDENED_MODE: bool = False
    LIVE_LIVENESS_MAX_LANDMARK_RMS: float = 0.18
    LIVE_LIVENESS_MAX_CENTER_JUMP_RATIO: float = 0.35
    LIVE_LIVENESS_TURN_TARGET_DELTA: float = 0.10
    LIVE_LIVENESS_FRONTAL_YAW_LIMIT: float = 0.22
    LIVE_LIVENESS_TURN_DIRECTION_MULTIPLIER: float = 1.0
    LIVE_FACE_MIN_AREA_RATIO: float = 0.03
    LIVE_FACE_MAX_CENTER_DISTANCE_RATIO: float = 0.45
    LIVE_FACE_DOMINANCE_RATIO: float = 2.5

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = {
        "env_file": PROJECT_ROOT / ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
