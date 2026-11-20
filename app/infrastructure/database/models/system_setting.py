"""
System Setting Model
====================
Key-value store for application-wide configuration
that can be changed at runtime by administrators.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base


class SystemSettingModel(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(150), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    updater = relationship("UserModel", foreign_keys=[updated_by])

    def __repr__(self) -> str:
        return f"<SystemSettingModel id={self.id} key={self.key}>"
