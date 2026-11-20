"""
Employee Schedule Model
=======================
Associates an employee with a schedule template for a
given date range.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Date, Boolean, DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base


class EmployeeScheduleModel(Base):
    __tablename__ = "employee_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    schedule_template_id = Column(Integer, ForeignKey("schedule_templates.id"), nullable=False)
    effective_start_date = Column(Date, nullable=False)
    effective_end_date = Column(Date, nullable=True)
    working_days = Column(String(50), nullable=False, comment="Comma-separated ISO weekday numbers, 0=Mon ... 6=Sun")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    employee = relationship("EmployeeModel", back_populates="schedules")
    schedule_template = relationship("ScheduleTemplateModel", back_populates="employee_schedules")

    def __repr__(self) -> str:
        return (
            f"<EmployeeScheduleModel id={self.id} "
            f"employee={self.employee_id} template={self.schedule_template_id}>"
        )
