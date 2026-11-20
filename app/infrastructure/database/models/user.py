"""
User Model
==========
Represents system users who can authenticate.
Each user has a role (ADMIN or EMPLOYEE) and may be
linked to an Employee profile.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, Enum, DateTime,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base
from app.domain.enums.user_role import UserRole


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.EMPLOYEE)
    is_active = Column(Boolean, default=True, nullable=False)
    token_version = Column(Integer, default=0, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    employee = relationship("EmployeeModel", back_populates="user", uselist=False)
    audit_logs = relationship("AuditLogModel", back_populates="actor", foreign_keys="AuditLogModel.actor_user_id")

    def __repr__(self) -> str:
        return f"<UserModel id={self.id} email={self.email} role={self.role}>"
