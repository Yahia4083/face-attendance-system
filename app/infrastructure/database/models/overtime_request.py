"""
Overtime Request Model
======================
Tracks overtime reported by employees and its approval status.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, DateTime, Enum, ForeignKey, Text,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base
from app.domain.enums.overtime_status import OvertimeStatus


class OvertimeRequestModel(Base):
    __tablename__ = "overtime_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    attendance_record_id = Column(Integer, ForeignKey("attendance_records.id"), nullable=False)
    overtime_minutes = Column(Integer, nullable=False)
    eligible_minutes_at_submission = Column(Integer, nullable=False, default=0)
    approved_minutes = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(Enum(OvertimeStatus), nullable=False, default=OvertimeStatus.PENDING)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    employee = relationship("EmployeeModel", back_populates="overtime_requests")
    attendance_record = relationship("AttendanceRecordModel", back_populates="overtime_requests")
    reviewer = relationship("UserModel", foreign_keys=[reviewed_by])

    def __repr__(self) -> str:
        return (
            f"<OvertimeRequestModel id={self.id} "
            f"employee={self.employee_id} minutes={self.overtime_minutes} status={self.status}>"
        )
