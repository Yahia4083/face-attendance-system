"""Attendance correction model.

Stores administrative resolution metadata without rewriting the factual
camera-generated attendance record.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base


class AttendanceCorrectionModel(Base):
    __tablename__ = "attendance_corrections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    attendance_record_id = Column(Integer, ForeignKey("attendance_records.id"), nullable=False, index=True)
    original_status = Column(String(50), nullable=False)
    corrected_status = Column(String(50), nullable=False)
    reason = Column(Text, nullable=False)
    corrected_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    corrected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    attendance_record = relationship("AttendanceRecordModel", back_populates="corrections")
    corrected_by = relationship("UserModel", foreign_keys=[corrected_by_user_id])

    def __repr__(self) -> str:
        return (
            f"<AttendanceCorrectionModel id={self.id} "
            f"attendance_record_id={self.attendance_record_id} corrected_status={self.corrected_status}>"
        )
