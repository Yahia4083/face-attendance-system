"""
Employee Model
==============
Core profile for each employee.  Links to a User account
and a Department.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base


class EmployeeModel(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    full_name = Column(String(255), nullable=False)
    employee_number = Column(String(50), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    position = Column(String(150), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    user = relationship("UserModel", back_populates="employee")
    department = relationship("DepartmentModel", back_populates="employees")
    schedules = relationship("EmployeeScheduleModel", back_populates="employee")
    face_embeddings = relationship("FaceEmbeddingModel", back_populates="employee")
    attendance_records = relationship("AttendanceRecordModel", back_populates="employee")
    justification_requests = relationship("JustificationRequestModel", back_populates="employee")
    overtime_requests = relationship("OvertimeRequestModel", back_populates="employee")

    def __repr__(self) -> str:
        return f"<EmployeeModel id={self.id} name={self.full_name} number={self.employee_number}>"
