"""
Schedule Template Model
=======================
Reusable work-schedule templates that define working hours,
grace periods, and the days of the week the schedule applies to.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Time, Boolean, DateTime, Text,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base


class ScheduleTemplateModel(Base):
    __tablename__ = "schedule_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_overnight = Column(Boolean, default=False, nullable=False)
    check_in_grace_minutes = Column(Integer, default=0, nullable=False)
    early_departure_tolerance_minutes = Column(Integer, default=0, nullable=False)
    grace_period_minutes = Column(Integer, default=0, nullable=False)
    minimum_overtime_minutes = Column(Integer, default=0, nullable=False)
    working_days = Column(String(50), nullable=False, comment="Comma-separated day numbers, e.g. '0,1,2,3,4' for Mon-Fri")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    employee_schedules = relationship("EmployeeScheduleModel", back_populates="schedule_template")

    def __repr__(self) -> str:
        return f"<ScheduleTemplateModel id={self.id} name={self.name}>"
