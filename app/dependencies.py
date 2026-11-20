"""Application dependency providers."""

from functools import lru_cache
from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.use_cases.auth.login_user import LoginUser
from app.domain.repositories.attendance_record_repository import (
    AttendanceRecordRepositoryInterface,
)
from app.domain.repositories.attendance_correction_repository import (
    AttendanceCorrectionRepositoryInterface,
)
from app.domain.repositories.audit_repository import AuditRepositoryInterface
from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.domain.repositories.dashboard_repository import DashboardRepositoryInterface
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.domain.repositories.employee_schedule_repository import EmployeeScheduleRepositoryInterface
from app.domain.repositories.face_embedding_repository import FaceEmbeddingRepositoryInterface
from app.domain.repositories.justification_request_repository import (
    JustificationRequestRepositoryInterface,
)
from app.domain.repositories.overtime_request_repository import OvertimeRequestRepositoryInterface
from app.domain.repositories.report_repository import ReportRepositoryInterface
from app.domain.repositories.schedule_template_repository import ScheduleTemplateRepositoryInterface
from app.domain.repositories.system_setting_repository import SystemSettingRepositoryInterface
from app.domain.repositories.user_repository import UserRepositoryInterface
from app.domain.services.attendance_export_service import AttendanceExportServiceInterface
from app.domain.services.face_processing_service import (
    FaceDetectorInterface,
    FaceEmbedderInterface,
    FaceEnrollmentServiceInterface,
    FaceSimilarityServiceInterface,
    FaceStorageServiceInterface,
)
from app.domain.services.clock_service import ClockInterface
from app.domain.services.face_recognition_service import FaceRecognitionServiceInterface
from app.domain.services.liveness_service import LivenessServiceInterface
from app.domain.services.system_settings_provider import SystemSettingsProviderInterface
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.repositories.sql_attendance_record_repository import (
    SqlAttendanceRecordRepository,
)
from app.infrastructure.database.repositories.sql_attendance_correction_repository import (
    SqlAttendanceCorrectionRepository,
)
from app.infrastructure.database.repositories.sql_audit_repository import SqlAuditRepository
from app.infrastructure.database.repositories.sql_dashboard_repository import SqlDashboardRepository
from app.infrastructure.database.repositories.sql_department_repository import (
    SqlDepartmentRepository,
)
from app.infrastructure.database.repositories.sql_employee_repository import (
    SqlEmployeeRepository,
)
from app.infrastructure.database.repositories.sql_employee_schedule_repository import (
    SqlEmployeeScheduleRepository,
)
from app.infrastructure.database.repositories.sql_face_embedding_repository import (
    SqlFaceEmbeddingRepository,
)
from app.infrastructure.database.repositories.sql_justification_request_repository import (
    SqlJustificationRequestRepository,
)
from app.infrastructure.database.repositories.sql_overtime_request_repository import (
    SqlOvertimeRequestRepository,
)
from app.infrastructure.database.repositories.sql_report_repository import SqlReportRepository
from app.infrastructure.database.repositories.sql_schedule_template_repository import (
    SqlScheduleTemplateRepository,
)
from app.infrastructure.database.repositories.sql_system_setting_repository import (
    SqlSystemSettingRepository,
)
from app.infrastructure.database.repositories.sql_user_repository import SqlUserRepository
from app.infrastructure.exports.attendance_export_service import AttendanceExportService
from app.infrastructure.face_ai.development_face_embedder import DevelopmentFaceEmbedder
from app.infrastructure.face_ai.facenet_embedder import FaceNetEmbedder
from app.infrastructure.face_ai.facenet_recognition_service import FaceNetRecognitionService
from app.infrastructure.face_ai.face_enrollment_service import FaceEnrollmentService
from app.infrastructure.face_ai.face_similarity_service import FaceSimilarityService
from app.infrastructure.face_ai.face_storage_service import FaceStorageService
from app.infrastructure.face_ai.image_validator import ImageValidator
from app.infrastructure.face_ai.mtcnn_face_detector import MTCNNFaceDetector
from app.infrastructure.face_ai.opencv_face_detector import OpenCVFaceDetector
from app.infrastructure.face_ai.simple_liveness_service import SimpleLivenessService
from app.infrastructure.services.system_clock import SystemClock
from app.infrastructure.settings.runtime_system_settings_provider import RuntimeSystemSettingsProvider

def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session and always close it after the request."""
    # Creates and closes one SQLAlchemy session for the current request.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Builds concrete SQLAlchemy repository implementations for route dependencies.
def get_user_repository(
    db: Session = Depends(get_db),
) -> UserRepositoryInterface:
    """Build the user repository for the current request."""
    return SqlUserRepository(db)


def get_audit_repository(
    db: Session = Depends(get_db),
) -> AuditRepositoryInterface:
    """Build the audit repository for the current request."""
    return SqlAuditRepository(db)


def get_dashboard_repository(
    db: Session = Depends(get_db),
) -> DashboardRepositoryInterface:
    """Build the dashboard repository for the current request."""
    return SqlDashboardRepository(db)


def get_attendance_record_repository(
    db: Session = Depends(get_db),
) -> AttendanceRecordRepositoryInterface:
    """Build the attendance record repository for the current request."""
    return SqlAttendanceRecordRepository(db)


def get_attendance_correction_repository(
    db: Session = Depends(get_db),
) -> AttendanceCorrectionRepositoryInterface:
    """Build the attendance correction repository for the current request."""
    return SqlAttendanceCorrectionRepository(db)


def get_department_repository(
    db: Session = Depends(get_db),
) -> DepartmentRepositoryInterface:
    """Build the department repository for the current request."""
    return SqlDepartmentRepository(db)


def get_employee_repository(
    db: Session = Depends(get_db),
) -> EmployeeRepositoryInterface:
    """Build the employee repository for the current request."""
    return SqlEmployeeRepository(db)


def get_face_embedding_repository(
    db: Session = Depends(get_db),
) -> FaceEmbeddingRepositoryInterface:
    """Build the face embedding repository for the current request."""
    return SqlFaceEmbeddingRepository(db)


def get_schedule_template_repository(
    db: Session = Depends(get_db),
) -> ScheduleTemplateRepositoryInterface:
    """Build the schedule template repository for the current request."""
    return SqlScheduleTemplateRepository(db)


def get_employee_schedule_repository(
    db: Session = Depends(get_db),
) -> EmployeeScheduleRepositoryInterface:
    """Build the employee schedule repository for the current request."""
    return SqlEmployeeScheduleRepository(db)


def get_justification_request_repository(
    db: Session = Depends(get_db),
) -> JustificationRequestRepositoryInterface:
    """Build the justification request repository for the current request."""
    return SqlJustificationRequestRepository(db)


def get_overtime_request_repository(
    db: Session = Depends(get_db),
) -> OvertimeRequestRepositoryInterface:
    """Build the overtime request repository for the current request."""
    return SqlOvertimeRequestRepository(db)


def get_report_repository(
    db: Session = Depends(get_db),
) -> ReportRepositoryInterface:
    """Build the report repository for the current request."""
    return SqlReportRepository(db)


def get_system_setting_repository(
    db: Session = Depends(get_db),
) -> SystemSettingRepositoryInterface:
    """Build the system setting repository for the current request."""
    return SqlSystemSettingRepository(db)


# Provides the shared CSV/XLSX export service instance.
@lru_cache()
def _get_cached_attendance_export_service() -> AttendanceExportServiceInterface:
    return AttendanceExportService()


def get_attendance_export_service() -> AttendanceExportServiceInterface:
    """Build attendance export service."""
    return _get_cached_attendance_export_service()


# Provides cached face AI components used by enrollment and attendance.
@lru_cache()
def _get_cached_face_detector() -> FaceDetectorInterface:
    from app.config import get_settings

    backend = get_settings().FACE_DETECTOR_BACKEND.strip().lower()
    if backend == "mtcnn":
        return MTCNNFaceDetector()
    if backend in {"haar", "opencv", "opencv_haar"}:
        return OpenCVFaceDetector()
    raise RuntimeError(
        "Unsupported FACE_DETECTOR_BACKEND value. Use 'mtcnn' for the default detector "
        "or 'haar' only for legacy debugging."
    )


def get_face_detector() -> FaceDetectorInterface:
    """Build reusable face detector adapter."""
    return _get_cached_face_detector()


@lru_cache()
def _get_cached_face_embedder() -> FaceEmbedderInterface:
    from app.config import get_settings

    backend = get_settings().FACE_EMBEDDER_BACKEND.strip().lower()
    if backend == "facenet":
        return FaceNetEmbedder()
    if backend in {"development", "dev", "development_face_embedder"}:
        return DevelopmentFaceEmbedder()
    raise RuntimeError(
        "Unsupported FACE_EMBEDDER_BACKEND value. Use 'facenet' for enrollment "
        "or 'development' only for legacy debugging."
    )


def get_face_embedder() -> FaceEmbedderInterface:
    """Build reusable face embedder adapter."""
    return _get_cached_face_embedder()


# Provides cached helper services that do not depend on request state.
@lru_cache()
def _get_cached_face_similarity_service() -> FaceSimilarityServiceInterface:
    return FaceSimilarityService()


def get_face_similarity_service() -> FaceSimilarityServiceInterface:
    """Build reusable face similarity service."""
    return _get_cached_face_similarity_service()


@lru_cache()
def _get_cached_face_storage_service() -> FaceStorageServiceInterface:
    return FaceStorageService()


def get_face_storage_service() -> FaceStorageServiceInterface:
    """Build reusable face storage service."""
    return _get_cached_face_storage_service()


# Builds the face-enrollment application service.
def get_face_enrollment_service(
    detector: FaceDetectorInterface = Depends(get_face_detector),
    embedder: FaceEmbedderInterface = Depends(get_face_embedder),
    storage_service: FaceStorageServiceInterface = Depends(get_face_storage_service),
) -> FaceEnrollmentServiceInterface:
    """Build face enrollment processing service."""
    return FaceEnrollmentService(
        image_validator=ImageValidator(),
        detector=detector,
        embedder=embedder,
        storage_service=storage_service,
    )


# Builds the face-recognition attendance service.
def get_face_recognition_service(
    detector: FaceDetectorInterface = Depends(get_face_detector),
    embedder: FaceEmbedderInterface = Depends(get_face_embedder),
    face_embedding_repo: FaceEmbeddingRepositoryInterface = Depends(
        get_face_embedding_repository,
    ),
) -> FaceRecognitionServiceInterface:
    """Build attendance face-recognition service."""
    return FaceNetRecognitionService(
        image_validator=ImageValidator(),
        detector=detector,
        embedder=embedder,
        face_embedding_repo=face_embedding_repo,
    )


# Builds the live-attendance liveness validation service.
def get_liveness_service(
    detector: FaceDetectorInterface = Depends(get_face_detector),
) -> LivenessServiceInterface:
    """Build live-attendance liveness service."""
    from app.config import get_settings

    return SimpleLivenessService(
        detector=detector,
        hardened_mode=get_settings().LIVE_LIVENESS_HARDENED_MODE,
    )


# Provides the application clock service.
@lru_cache()
def _get_cached_clock() -> ClockInterface:
    return SystemClock()


def get_clock() -> ClockInterface:
    """Build clock service."""
    return _get_cached_clock()


# Builds the runtime system-settings provider for the current request.
def get_system_settings_provider(
    settings_repo: SystemSettingRepositoryInterface = Depends(get_system_setting_repository),
    clock: ClockInterface = Depends(get_clock),
) -> SystemSettingsProviderInterface:
    """Build runtime settings provider for the current request."""
    return RuntimeSystemSettingsProvider(settings_repo=settings_repo, clock=clock)


# Builds authentication use cases and token services.
def get_login_use_case(
    user_repo: UserRepositoryInterface = Depends(get_user_repository),
    audit_repo: AuditRepositoryInterface = Depends(get_audit_repository),
) -> LoginUser:
    """Build the login use case with request-scoped repositories."""
    return LoginUser(user_repo=user_repo, audit_repo=audit_repo)
