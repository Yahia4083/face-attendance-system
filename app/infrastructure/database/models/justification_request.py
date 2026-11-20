"""
Justification Request Model
============================
Allows employees to submit justifications for attendance
anomalies (late arrival, absence, etc.).
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base
from app.domain.enums.request_status import RequestStatus


class JustificationRequestModel(Base):
    __tablename__ = "justification_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    attendance_record_id = Column(Integer, ForeignKey("attendance_records.id"), nullable=False)
    request_type = Column(String(100), nullable=False, comment="Type of justification, e.g. SICK_LEAVE, PERSONAL")
    explanation = Column(Text, nullable=False)
    status = Column(Enum(RequestStatus), nullable=False, default=RequestStatus.PENDING)
    admin_comment = Column(Text, nullable=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    employee = relationship("EmployeeModel", back_populates="justification_requests")
    attendance_record = relationship("AttendanceRecordModel", back_populates="justification_requests")
    reviewer = relationship("UserModel", foreign_keys=[reviewed_by])

    def __repr__(self) -> str:
        return (
            f"<JustificationRequestModel id={self.id} "
            f"employee={self.employee_id} status={self.status}>"
        )
