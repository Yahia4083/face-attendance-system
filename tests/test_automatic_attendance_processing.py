"""Tests for automatic attendance processing orchestration."""

import asyncio
from datetime import date

import pytest

from app.infrastructure.services.automatic_attendance_processor import (
    AutomaticAttendanceProcessor,
    AutomaticAttendanceScheduler,
)


def test_startup_processing_dates_cover_configured_lookback_in_order():
    dates = AutomaticAttendanceProcessor.processing_dates(
        current_date=date(2026, 8, 25),
        lookback_days=7,
        startup_scan=True,
    )

    assert dates == (
        date(2026, 8, 19),
        date(2026, 8, 20),
        date(2026, 8, 21),
        date(2026, 8, 22),
        date(2026, 8, 23),
        date(2026, 8, 24),
        date(2026, 8, 25),
    )


def test_regular_processing_dates_cover_previous_and_current_business_dates():
    dates = AutomaticAttendanceProcessor.processing_dates(
        current_date=date(2026, 8, 25),
        lookback_days=7,
        startup_scan=False,
    )

    assert dates == (date(2026, 8, 24), date(2026, 8, 25))


@pytest.mark.parametrize("lookback_days", [0, 1, 32])
def test_processor_rejects_unsafe_lookback_values(lookback_days):
    with pytest.raises(ValueError, match="LOOKBACK_DAYS"):
        AutomaticAttendanceProcessor(lookback_days=lookback_days)


def test_scheduler_starts_once_and_stops_cleanly_before_first_cycle():
    class ProcessorStub:
        def __init__(self):
            self.calls = 0

        def run_once(self):
            self.calls += 1

    async def exercise_scheduler():
        processor = ProcessorStub()
        scheduler = AutomaticAttendanceScheduler(
            processor=processor,
            interval_seconds=10,
        )
        scheduler.start()
        first_task = scheduler._task
        scheduler.start()

        assert scheduler.is_running is True
        assert scheduler._task is first_task

        await scheduler.stop()

        assert scheduler.is_running is False
        assert processor.calls == 0

    asyncio.run(exercise_scheduler())
