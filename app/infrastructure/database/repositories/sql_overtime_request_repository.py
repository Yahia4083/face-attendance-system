"""SQLAlchemy overtime request repository implementation."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.domain.enums.overtime_status import OvertimeStatus
from app.domain.repositories.overtime_request_repository import (
    OvertimeRequestFilters,
    OvertimeRequestRepositoryInterface,
)
from app.infrastructure.database.models.overtime_request import OvertimeRequestModel


class SqlOvertimeRequestRepository(OvertimeRequestRepositoryInterface):
    """Overtime request repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        employee_id: int,
        attendance_record_id: int,
        requested_minutes: int,
        eligible_minutes_at_submission: int,
        reason: str,
        commit: bool = True,
    ) -> OvertimeRequestModel:
        record = OvertimeRequestModel(
            employee_id=employee_id,
            attendance_record_id=attendance_record_id,
            overtime_minutes=requested_minutes,
            eligible_minutes_at_submission=eligible_minutes_at_submission,
            approved_minutes=None,
            reason=reason,
            status=OvertimeStatus.PENDING,
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
        return self.get_by_id(record.id) or record

    def get_by_id(self, request_id: int) -> Optional[OvertimeRequestModel]:
        return self._base_query().filter(OvertimeRequestModel.id == request_id).first()

    def list_for_employee(
        self,
        employee_id: int,
        *,
        filters: OvertimeRequestFilters,
        page: int,
        page_size: int,
    ) -> list[OvertimeRequestModel]:
        query = self._apply_filters(self._base_query(), filters).filter(
            OvertimeRequestModel.employee_id == employee_id
        )
        return self._paginate(query, page, page_size)

    def count_for_employee(
        self,
        employee_id: int,
        *,
        filters: OvertimeRequestFilters,
    ) -> int:
        return (
            self._apply_filters(self._db.query(OvertimeRequestModel), filters)
            .filter(OvertimeRequestModel.employee_id == employee_id)
            .count()
        )

    def list_all(
        self,
        *,
        filters: OvertimeRequestFilters,
        page: int,
        page_size: int,
    ) -> list[OvertimeRequestModel]:
        return self._paginate(self._apply_filters(self._base_query(), filters), page, page_size)

    def count_all(self, *, filters: OvertimeRequestFilters) -> int:
        return self._apply_filters(self._db.query(OvertimeRequestModel), filters).count()

    def has_pending_for_attendance(self, *, attendance_record_id: int) -> bool:
        return self._has_status(attendance_record_id, OvertimeStatus.PENDING)

    def has_approved_for_attendance(self, *, attendance_record_id: int) -> bool:
        return self._has_status(attendance_record_id, OvertimeStatus.APPROVED)

    def approve(
        self,
        *,
        request_id: int,
        approved_minutes: int,
        reviewer_user_id: int,
        reviewer_note: Optional[str],
        reviewed_at: datetime,
        commit: bool = True,
    ) -> Optional[OvertimeRequestModel]:
        record = self.get_by_id(request_id)
        if record is None:
            return None
        record.status = OvertimeStatus.APPROVED
        record.approved_minutes = approved_minutes
        record.reviewed_by = reviewer_user_id
        record.reviewer_note = reviewer_note
        record.reviewed_at = reviewed_at
        try:
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return self.get_by_id(request_id)

    def reject(
        self,
        *,
        request_id: int,
        reviewer_user_id: int,
        reviewer_note: Optional[str],
        reviewed_at: datetime,
        commit: bool = True,
    ) -> Optional[OvertimeRequestModel]:
        record = self.get_by_id(request_id)
        if record is None:
            return None
        record.status = OvertimeStatus.REJECTED
        record.reviewed_by = reviewer_user_id
        record.reviewer_note = reviewer_note
        record.reviewed_at = reviewed_at
        try:
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return self.get_by_id(request_id)

    def _has_status(self, attendance_record_id: int, status: OvertimeStatus) -> bool:
        return (
            self._db.query(OvertimeRequestModel)
            .filter(
                OvertimeRequestModel.attendance_record_id == attendance_record_id,
                OvertimeRequestModel.status == status,
            )
            .first()
            is not None
        )

    def _base_query(self):
        return self._db.query(OvertimeRequestModel).options(
            joinedload(OvertimeRequestModel.employee),
            joinedload(OvertimeRequestModel.attendance_record),
        )

    @staticmethod
    def _apply_filters(query, filters: OvertimeRequestFilters):
        if filters.employee_id is not None:
            query = query.filter(OvertimeRequestModel.employee_id == filters.employee_id)
        if filters.attendance_record_id is not None:
            query = query.filter(
                OvertimeRequestModel.attendance_record_id == filters.attendance_record_id
            )
        if filters.status is not None:
            query = query.filter(OvertimeRequestModel.status == filters.status)
        if filters.date_from is not None:
            query = query.filter(
                OvertimeRequestModel.created_at >= datetime.combine(filters.date_from, time.min)
            )
        if filters.date_to is not None:
            query = query.filter(
                OvertimeRequestModel.created_at
                < datetime.combine(filters.date_to + timedelta(days=1), time.min)
            )
        return query

    @staticmethod
    def _paginate(query, page: int, page_size: int):
        return (
            query.order_by(OvertimeRequestModel.created_at.desc(), OvertimeRequestModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
