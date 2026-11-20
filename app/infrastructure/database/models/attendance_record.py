"""
Attendance Record Model
=======================
Stores daily check-in / check-out data for employees
and computed attendance metrics.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Integer, String, Float, Date, DateTime, Enum, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base
from app.domain.enums.attendance_status import AttendanceStatus


class AttendanceRecordModel(Base):
    __tablename__ = "attendance_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    employee_schedule_id = Column(Integer, ForeignKey("employee_schedules.id"), nullable=True)
    schedule_template_id = Column(Integer, ForeignKey("schedule_templates.id"), nullable=True)
    attendance_date = Column(Date, nullable=False, index=True)
    scheduled_start_datetime = Column(DateTime, nullable=True)
    scheduled_end_datetime = Column(DateTime, nullable=True)
    check_in_time = Column(DateTime, nullable=True)
    check_out_time = Column(DateTime, nullable=True)
    working_hours = Column(Float, nullable=True)
    status = Column(Enum(AttendanceStatus), nullable=False, default=AttendanceStatus.ABSENT)
    is_late = Column(Boolean, default=False, nullable=False)
    is_early_departure = Column(Boolean, default=False, nullable=False)
    is_unscheduled = Column(Boolean, default=False, nullable=False)
    is_missing_checkout = Column(Boolean, default=False, nullable=False)
    late_minutes = Column(Integer, default=0, nullable=False)
    early_departure_minutes = Column(Integer, default=0, nullable=False)
    recognition_model_name = Column(String(100), nullable=True)
    detector_backend = Column(String(50), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    employee = relationship("EmployeeModel", back_populates="attendance_records")
    employee_schedule = relationship("EmployeeScheduleModel")
    schedule_template = relationship("ScheduleTemplateModel")
    justification_requests = relationship("JustificationRequestModel", back_populates="attendance_record")
    overtime_requests = relationship("OvertimeRequestModel", back_populates="attendance_record")
    corrections = relationship("AttendanceCorrectionModel", back_populates="attendance_record")

    def __repr__(self) -> str:
        return (
            f"<AttendanceRecordModel id={self.id} "
            f"employee={self.employee_id} date={self.attendance_date} status={self.status}>"
        )
