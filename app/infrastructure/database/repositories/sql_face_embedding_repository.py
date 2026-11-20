"""SQLAlchemy face embedding repository implementation."""

import json
from typing import Any, Optional

from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.repositories.face_embedding_repository import (
    ActiveFaceEmbeddingForRecognition,
    FaceEmbeddingRepositoryInterface,
)
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.face_embedding import FaceEmbeddingModel


class SqlFaceEmbeddingRepository(FaceEmbeddingRepositoryInterface):
    """Face embedding repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_embedding(
        self,
        *,
        employee_id: int,
        embedding_vector: list[float],
        image_path: str,
        model_name: str,
        is_active: bool = True,
        commit: bool = True,
    ) -> FaceEmbeddingModel:
        record = FaceEmbeddingModel(
            employee_id=employee_id,
            embedding_vector=self._serialize_embedding(embedding_vector),
            image_path=image_path,
            model_name=model_name,
            is_active=is_active,
        )
        try:
            self._db.add(record)
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return record

    def create_many_embeddings(
        self,
        *,
        embeddings: list[dict[str, Any]],
        commit: bool = True,
    ) -> list[FaceEmbeddingModel]:
        records: list[FaceEmbeddingModel] = []
        try:
            for item in embeddings:
                record = FaceEmbeddingModel(
                    employee_id=item["employee_id"],
                    embedding_vector=self._serialize_embedding(item["embedding_vector"]),
                    image_path=item["image_path"],
                    model_name=item["model_name"],
                    is_active=item.get("is_active", True),
                )
                records.append(record)
                self._db.add(record)

            self._db.flush()
            if commit:
                self._db.commit()
                for record in records:
                    self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return records

    def get_active_by_employee_id(self, employee_id: int) -> list[FaceEmbeddingModel]:
        return (
            self._db.query(FaceEmbeddingModel)
            .filter(
                FaceEmbeddingModel.employee_id == employee_id,
                FaceEmbeddingModel.is_active.is_(True),
            )
            .order_by(desc(FaceEmbeddingModel.created_at), desc(FaceEmbeddingModel.id))
            .all()
        )

    def get_active_embedding_vectors_by_employee_id(
        self,
        employee_id: int,
        *,
        model_name: str,
    ) -> list[list[float]]:
        records = (
            self._db.query(FaceEmbeddingModel)
            .filter(
                FaceEmbeddingModel.employee_id == employee_id,
                FaceEmbeddingModel.model_name == model_name,
                FaceEmbeddingModel.is_active.is_(True),
            )
            .order_by(desc(FaceEmbeddingModel.created_at), desc(FaceEmbeddingModel.id))
            .all()
        )
        return [self._deserialize_embedding(record.embedding_vector) for record in records]

    def get_active_model_names_by_employee_id(self, employee_id: int) -> list[str]:
        rows = (
            self._db.query(FaceEmbeddingModel.model_name)
            .filter(
                FaceEmbeddingModel.employee_id == employee_id,
                FaceEmbeddingModel.is_active.is_(True),
            )
            .distinct()
            .all()
        )
        return sorted(row[0] for row in rows if row[0])

    def get_all_by_employee_id(self, employee_id: int) -> list[FaceEmbeddingModel]:
        return (
            self._db.query(FaceEmbeddingModel)
            .filter(FaceEmbeddingModel.employee_id == employee_id)
            .order_by(desc(FaceEmbeddingModel.created_at), desc(FaceEmbeddingModel.id))
            .all()
        )

    def count_active_by_employee_id(self, employee_id: int) -> int:
        return (
            self._db.query(FaceEmbeddingModel)
            .filter(
                FaceEmbeddingModel.employee_id == employee_id,
                FaceEmbeddingModel.is_active.is_(True),
            )
            .count()
        )

    def count_inactive_by_employee_id(self, employee_id: int) -> int:
        return (
            self._db.query(FaceEmbeddingModel)
            .filter(
                FaceEmbeddingModel.employee_id == employee_id,
                FaceEmbeddingModel.is_active.is_(False),
            )
            .count()
        )

    def deactivate_active_by_employee_id(
        self,
        employee_id: int,
        *,
        commit: bool = True,
    ) -> int:
        try:
            affected_rows = (
                self._db.query(FaceEmbeddingModel)
                .filter(
                    FaceEmbeddingModel.employee_id == employee_id,
                    FaceEmbeddingModel.is_active.is_(True),
                )
                .update(
                    {FaceEmbeddingModel.is_active: False},
                    synchronize_session=False,
                )
            )
            if commit:
                self._db.commit()
            else:
                self._db.flush()
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return affected_rows

    def get_latest_by_employee_id(self, employee_id: int) -> Optional[FaceEmbeddingModel]:
        return (
            self._db.query(FaceEmbeddingModel)
            .filter(FaceEmbeddingModel.employee_id == employee_id)
            .order_by(desc(FaceEmbeddingModel.created_at), desc(FaceEmbeddingModel.id))
            .first()
        )

    def get_active_compatible_embeddings_for_recognition(
        self,
        *,
        model_name: str,
    ) -> list[ActiveFaceEmbeddingForRecognition]:
        records = (
            self._db.query(FaceEmbeddingModel)
            .join(EmployeeModel, EmployeeModel.id == FaceEmbeddingModel.employee_id)
            .filter(
                FaceEmbeddingModel.model_name == model_name,
                FaceEmbeddingModel.is_active.is_(True),
                EmployeeModel.is_active.is_(True),
            )
            .order_by(FaceEmbeddingModel.employee_id.asc(), FaceEmbeddingModel.id.asc())
            .all()
        )
        return [
            ActiveFaceEmbeddingForRecognition(
                employee_id=record.employee_id,
                embedding_vector=self._deserialize_embedding(record.embedding_vector),
                model_name=record.model_name,
            )
            for record in records
        ]

    @staticmethod
    def _serialize_embedding(embedding_vector: list[float]) -> bytes:
        return json.dumps(embedding_vector).encode("utf-8")

    @staticmethod
    def _deserialize_embedding(serialized_embedding: bytes) -> list[float]:
        if isinstance(serialized_embedding, bytes):
            payload = serialized_embedding.decode("utf-8")
        else:
            payload = str(serialized_embedding)
        values = json.loads(payload)
        return [float(value) for value in values]
