"""
Audit Log Model
===============
Immutable log of all significant actions performed by users.
Stores before/after values for traceability.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False, comment="e.g. CREATE, UPDATE, DELETE, LOGIN")
    entity_type = Column(String(100), nullable=False, comment="e.g. Employee, Department")
    entity_id = Column(Integer, nullable=True)
    old_values = Column(Text, nullable=True, comment="JSON-serialised previous state")
    new_values = Column(Text, nullable=True, comment="JSON-serialised new state")
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    actor = relationship("UserModel", back_populates="audit_logs", foreign_keys=[actor_user_id])

    def __repr__(self) -> str:
        return (
            f"<AuditLogModel id={self.id} actor={self.actor_user_id} "
            f"action={self.action} entity={self.entity_type}>"
        )
