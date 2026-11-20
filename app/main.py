"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.infrastructure.services.automatic_attendance_processor import (
    AutomaticAttendanceProcessor,
    AutomaticAttendanceScheduler,
)
from app.presentation.api.attendance import router as attendance_router
from app.presentation.api.audit_logs import router as audit_logs_router
from app.presentation.api.auth import router as auth_router
from app.presentation.api.dashboard import router as dashboard_router
from app.presentation.api.departments import router as departments_router
from app.presentation.api.employee_schedules import router as employee_schedules_router
from app.presentation.api.employees import router as employees_router
from app.presentation.api.face_enrollment import router as face_enrollment_router
from app.presentation.api.health import router as health_router
from app.presentation.api.justification_requests import router as justification_requests_router
from app.presentation.api.live_attendance import router as live_attendance_router
from app.presentation.api.overtime_requests import router as overtime_requests_router
from app.presentation.api.reports import router as reports_router
from app.presentation.api.schedule_templates import router as schedule_templates_router
from app.presentation.api.system_settings import router as system_settings_router


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan hooks."""
    settings = get_settings()
    scheduler = None
    if settings.ATTENDANCE_AUTO_PROCESSING_ENABLED:
        scheduler = AutomaticAttendanceScheduler(
            processor=AutomaticAttendanceProcessor(
                lookback_days=settings.ATTENDANCE_AUTO_PROCESSING_LOOKBACK_DAYS,
            ),
            interval_seconds=settings.ATTENDANCE_AUTO_PROCESSING_INTERVAL_SECONDS,
        )
        scheduler.start()
        logger.info(
            "Automatic attendance processing enabled: every %s seconds, %s-day startup lookback.",
            settings.ATTENDANCE_AUTO_PROCESSING_INTERVAL_SECONDS,
            settings.ATTENDANCE_AUTO_PROCESSING_LOOKBACK_DAYS,
        )
    app.state.attendance_processing_scheduler = scheduler

    try:
        yield
    finally:
        if scheduler is not None:
            await scheduler.stop()


def create_app() -> FastAPI:
    """Create and configure FastAPI application instance."""
    settings = get_settings()

    # Creates the FastAPI app and its OpenAPI metadata.
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Web-based attendance management system using face recognition.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Registers CORS origins for local frontend and API clients.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registers all API routers by feature module.
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(departments_router)
    app.include_router(employees_router)
    app.include_router(face_enrollment_router)
    app.include_router(schedule_templates_router)
    app.include_router(employee_schedules_router)
    app.include_router(attendance_router)
    app.include_router(audit_logs_router)
    app.include_router(live_attendance_router)
    app.include_router(justification_requests_router)
    app.include_router(overtime_requests_router)
    app.include_router(reports_router)
    app.include_router(system_settings_router)
    app.include_router(dashboard_router)

    return app


app = create_app()
