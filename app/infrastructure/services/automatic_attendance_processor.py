"""Automatic attendance processing service."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.application.dto.attendance_processing_dto import ProcessDailyAttendanceRequest
from app.application.use_cases.attendance.process_daily_attendance import (
    ProcessDailyAttendance,
)
from app.application.use_cases.exceptions import BadRequestError
from app.config import get_settings
from app.domain.services.clock_service import ClockInterface
from app.infrastructure.database.connection import SessionLocal
from app.infrastructure.database.repositories.sql_attendance_record_repository import (
    SqlAttendanceRecordRepository,
)
from app.infrastructure.database.repositories.sql_audit_repository import SqlAuditRepository
from app.infrastructure.database.repositories.sql_employee_schedule_repository import (
    SqlEmployeeScheduleRepository,
)
from app.infrastructure.database.repositories.sql_system_setting_repository import (
    SqlSystemSettingRepository,
)
from app.infrastructure.services.system_clock import SystemClock
from app.infrastructure.settings.runtime_system_settings_provider import (
    RuntimeSystemSettingsProvider,
)


logger = logging.getLogger(__name__)

_MYSQL_LOCK_NAME = "attendance_auto_daily_processing"
_LOCAL_PROCESSING_LOCK = threading.Lock()


@dataclass(frozen=True)
class AutomaticProcessingRun:
    """Summary of one automatic processing cycle."""

    lock_acquired: bool
    dates_attempted: tuple[date, ...]
    absent_records_created: int = 0
    missing_checkout_records_updated: int = 0


class AutomaticAttendanceProcessor:
    """Run the existing daily-processing use case for recent business dates."""

    def __init__(
        self,
        *,
        lookback_days: int,
        clock: ClockInterface | None = None,
        session_factory: Callable[[], Session] = SessionLocal,
    ) -> None:
        if not 2 <= lookback_days <= 31:
            raise ValueError("ATTENDANCE_AUTO_PROCESSING_LOOKBACK_DAYS must be between 2 and 31.")
        self._lookback_days = lookback_days
        self._clock = clock or SystemClock()
        self._session_factory = session_factory
        self._startup_scan_pending = True

    @staticmethod
    def processing_dates(
        *,
        current_date: date,
        lookback_days: int,
        startup_scan: bool,
    ) -> tuple[date, ...]:
        """Return dates needed for startup catch-up or normal overnight coverage."""

        day_count = lookback_days if startup_scan else min(2, lookback_days)
        oldest_date = current_date - timedelta(days=day_count - 1)
        return tuple(oldest_date + timedelta(days=offset) for offset in range(day_count))

    def run_once(self) -> AutomaticProcessingRun:
        """Process eligible shifts once without requiring an administrator request."""

        settings = get_settings()
        current_date = self._clock.now_in_timezone(settings.APP_TIMEZONE).date()
        dates = self.processing_dates(
            current_date=current_date,
            lookback_days=self._lookback_days,
            startup_scan=self._startup_scan_pending,
        )
        db = self._session_factory()
        lock_acquired = False
        uses_mysql_lock = self._uses_mysql_lock(db)
        unexpected_error = False
        absent_created = 0
        missing_updated = 0

        try:
            lock_acquired = self._acquire_lock(db, uses_mysql_lock=uses_mysql_lock)
            if not lock_acquired:
                logger.debug("Automatic attendance processing skipped because another worker owns the lock.")
                return AutomaticProcessingRun(lock_acquired=False, dates_attempted=())

            attendance_repo = SqlAttendanceRecordRepository(db)
            schedule_repo = SqlEmployeeScheduleRepository(db)
            audit_repo = SqlAuditRepository(db)
            settings_provider = RuntimeSystemSettingsProvider(
                settings_repo=SqlSystemSettingRepository(db),
                clock=self._clock,
            )
            use_case = ProcessDailyAttendance(
                attendance_repo=attendance_repo,
                schedule_repo=schedule_repo,
                audit_repo=audit_repo,
                clock=self._clock,
                settings_provider=settings_provider,
            )

            for on_date in dates:
                try:
                    result = use_case.execute(
                        ProcessDailyAttendanceRequest(
                            on_date=on_date,
                            actor_user_id=None,
                            ip_address=None,
                            is_automatic=True,
                        )
                    )
                    absent_created += result.absent_records_created
                    missing_updated += result.missing_checkout_records_updated
                except BadRequestError:
                    # A date with shifts before their cutoff needs no action yet.
                    db.rollback()
                except Exception:
                    db.rollback()
                    unexpected_error = True
                    logger.exception("Automatic attendance processing failed for %s.", on_date)

            if not unexpected_error:
                self._startup_scan_pending = False

            if absent_created or missing_updated:
                logger.info(
                    "Automatic attendance processing created %s absent record(s) and marked "
                    "%s missing checkout record(s).",
                    absent_created,
                    missing_updated,
                )
            return AutomaticProcessingRun(
                lock_acquired=True,
                dates_attempted=dates,
                absent_records_created=absent_created,
                missing_checkout_records_updated=missing_updated,
            )
        finally:
            if lock_acquired:
                self._release_lock(db, uses_mysql_lock=uses_mysql_lock)
            db.close()

    @staticmethod
    def _uses_mysql_lock(db: Session) -> bool:
        bind = db.get_bind()
        return bind is not None and bind.dialect.name in {"mysql", "mariadb"}

    @staticmethod
    def _acquire_lock(db: Session, *, uses_mysql_lock: bool) -> bool:
        if uses_mysql_lock:
            result = db.execute(
                text("SELECT GET_LOCK(:lock_name, 0)"),
                {"lock_name": _MYSQL_LOCK_NAME},
            ).scalar()
            return result == 1
        return _LOCAL_PROCESSING_LOCK.acquire(blocking=False)

    @staticmethod
    def _release_lock(db: Session, *, uses_mysql_lock: bool) -> None:
        if uses_mysql_lock:
            try:
                db.execute(
                    text("SELECT RELEASE_LOCK(:lock_name)"),
                    {"lock_name": _MYSQL_LOCK_NAME},
                )
            except Exception:
                logger.exception("Could not release the automatic attendance processing lock.")
            return
        if _LOCAL_PROCESSING_LOCK.locked():
            _LOCAL_PROCESSING_LOCK.release()


class AutomaticAttendanceScheduler:
    """Run attendance processing periodically while the API process is alive."""

    def __init__(
        self,
        *,
        processor: AutomaticAttendanceProcessor,
        interval_seconds: int,
    ) -> None:
        if not 10 <= interval_seconds <= 3600:
            raise ValueError(
                "ATTENDANCE_AUTO_PROCESSING_INTERVAL_SECONDS must be between 10 and 3600."
            )
        self._processor = processor
        self._interval_seconds = interval_seconds
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the periodic task once."""

        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(
            self._run_forever(),
            name="automatic-attendance-processing",
        )

    async def stop(self) -> None:
        """Stop the periodic task and wait for a clean shutdown."""

        if self._task is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None

    async def _run_forever(self) -> None:
        while True:
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval_seconds,
                )
                return
            except asyncio.TimeoutError:
                pass

            try:
                await asyncio.to_thread(self._processor.run_once)
            except Exception:
                logger.exception("Automatic attendance processing cycle failed.")

