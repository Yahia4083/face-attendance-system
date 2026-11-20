"""SQLAlchemy system setting repository implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.repositories.system_setting_repository import SystemSettingRepositoryInterface
from app.infrastructure.database.models.system_setting import SystemSettingModel


class SqlSystemSettingRepository(SystemSettingRepositoryInterface):
    """System setting override repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_override_by_key(self, key: str) -> Optional[SystemSettingModel]:
        return (
            self._db.query(SystemSettingModel)
            .filter(SystemSettingModel.key == key.strip().upper())
            .first()
        )

    def list_overrides(self) -> list[SystemSettingModel]:
        return self._db.query(SystemSettingModel).order_by(SystemSettingModel.key.asc()).all()

    def upsert_override(
        self,
        *,
        key: str,
        value: str,
        description: Optional[str],
        actor_user_id: int,
        updated_at: datetime,
        commit: bool = True,
    ) -> SystemSettingModel:
        normalized_key = key.strip().upper()
        row = self.get_override_by_key(normalized_key)
        if row is None:
            row = SystemSettingModel(
                key=normalized_key,
                value=value,
                description=description,
                updated_by=actor_user_id,
                updated_at=updated_at,
            )
            self._db.add(row)
        else:
            row.value = value
            row.description = description
            row.updated_by = actor_user_id
            row.updated_at = updated_at

        try:
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(row)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return row
