"""
Face Embedding Model
====================
Stores facial-recognition embedding vectors associated
with an employee.  Multiple embeddings per employee are
allowed to improve recognition accuracy.
"""

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, LargeBinary,
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.base import Base


class FaceEmbeddingModel(Base):
    __tablename__ = "face_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    embedding_vector = Column(LargeBinary, nullable=False, comment="Serialised numpy array")
    image_path = Column(String(500), nullable=True)
    model_name = Column(String(100), nullable=True, comment="Name of the face-recognition model used")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────
    employee = relationship("EmployeeModel", back_populates="face_embeddings")

    def __repr__(self) -> str:
        return f"<FaceEmbeddingModel id={self.id} employee={self.employee_id} model={self.model_name}>"
