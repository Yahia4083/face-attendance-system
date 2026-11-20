"""Schemas for attendance processing endpoints."""

from datetime import date

from pydantic import BaseModel


class ProcessDailyAttendanceRequest(BaseModel):
    on_date: date


class ProcessDailyAttendanceResponse(BaseModel):
    on_date: date
    timezone: str
    processed_assignments: int
    absent_records_created: int
    missing_checkout_records_updated: int
    already_processed_or_unchanged: int
    message: str
