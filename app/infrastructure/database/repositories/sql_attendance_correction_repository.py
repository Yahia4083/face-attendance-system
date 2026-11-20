"""SQLAlchemy attendance correction repository implementation."""

from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.domain.repositories.attendance_correction_repository import (
    AttendanceCorrectionRepositoryInterface,
)
from app.infrastructure.database.models.attendance_correction import AttendanceCorrectionModel


class SqlAttendanceCorrectionRepository(AttendanceCorrectionRepositoryInterface):
    """Attendance correction repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        attendance_record_id: int,
        original_status: str,
        corrected_status: str,
        reason: str,
        corrected_by_user_id: int,
        corrected_at: datetime,
        commit: bool = True,
    ) -> AttendanceCorrectionModel:
        correction = AttendanceCorrectionModel(
            attendance_record_id=attendance_record_id,
            original_status=original_status,
            corrected_status=corrected_status,
            reason=reason,
            corrected_by_user_id=corrected_by_user_id,
            corrected_at=corrected_at,
            created_at=corrected_at,
        )
        try:
            self._db.add(correction)
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(correction)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return correction

    def list_for_attendance(self, attendance_record_id: int) -> list[AttendanceCorrectionModel]:
        return (
            self._db.query(AttendanceCorrectionModel)
            .options(joinedload(AttendanceCorrectionModel.corrected_by))
            .filter(AttendanceCorrectionModel.attendance_record_id == attendance_record_id)
            .order_by(
                AttendanceCorrectionModel.corrected_at.desc(),
                AttendanceCorrectionModel.id.desc(),
            )
            .all()
        )
