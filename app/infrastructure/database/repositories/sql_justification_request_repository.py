"""SQLAlchemy justification request repository implementation."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.domain.enums.request_status import RequestStatus
from app.domain.repositories.justification_request_repository import (
    JustificationRequestFilters,
    JustificationRequestRepositoryInterface,
)
from app.infrastructure.database.models.justification_request import JustificationRequestModel
from app.infrastructure.database.models.attendance_record import AttendanceRecordModel


class SqlJustificationRequestRepository(JustificationRequestRepositoryInterface):
    """Justification request repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        employee_id: int,
        attendance_record_id: int,
        request_type: str,
        reason: str,
        commit: bool = True,
    ) -> JustificationRequestModel:
        record = JustificationRequestModel(
            employee_id=employee_id,
            attendance_record_id=attendance_record_id,
            request_type=request_type,
            explanation=reason,
            status=RequestStatus.PENDING,
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

    def get_by_id(self, request_id: int) -> Optional[JustificationRequestModel]:
        return (
            self._base_query()
            .filter(JustificationRequestModel.id == request_id)
            .first()
        )

    def list_for_employee(
        self,
        employee_id: int,
        *,
        filters: JustificationRequestFilters,
        page: int,
        page_size: int,
    ) -> list[JustificationRequestModel]:
        query = self._apply_filters(self._base_query(), filters).filter(
            JustificationRequestModel.employee_id == employee_id
        )
        return self._paginate(query, page, page_size)

    def count_for_employee(
        self,
        employee_id: int,
        *,
        filters: JustificationRequestFilters,
    ) -> int:
        return (
            self._apply_filters(self._db.query(JustificationRequestModel), filters)
            .filter(JustificationRequestModel.employee_id == employee_id)
            .count()
        )

    def list_all(
        self,
        *,
        filters: JustificationRequestFilters,
        page: int,
        page_size: int,
    ) -> list[JustificationRequestModel]:
        return self._paginate(self._apply_filters(self._base_query(), filters), page, page_size)

    def count_all(self, *, filters: JustificationRequestFilters) -> int:
        return self._apply_filters(self._db.query(JustificationRequestModel), filters).count()

    def has_pending_for_attendance_and_type(
        self,
        *,
        attendance_record_id: int,
        request_type: str,
    ) -> bool:
        return self._has_status(attendance_record_id, request_type, RequestStatus.PENDING)

    def has_approved_for_attendance_and_type(
        self,
        *,
        attendance_record_id: int,
        request_type: str,
    ) -> bool:
        return self._has_status(attendance_record_id, request_type, RequestStatus.APPROVED)

    def exists_for_attendance(self, *, attendance_record_id: int) -> bool:
        return (
            self._db.query(JustificationRequestModel.id)
            .filter(JustificationRequestModel.attendance_record_id == attendance_record_id)
            .first()
            is not None
        )

    def count_for_employee_attendance_month(
        self,
        *,
        employee_id: int,
        month_start,
        month_end,
    ) -> int:
        return (
            self._db.query(JustificationRequestModel)
            .join(
                AttendanceRecordModel,
                AttendanceRecordModel.id == JustificationRequestModel.attendance_record_id,
            )
            .filter(
                JustificationRequestModel.employee_id == employee_id,
                AttendanceRecordModel.attendance_date >= month_start,
                AttendanceRecordModel.attendance_date <= month_end,
            )
            .count()
        )

    def approve(
        self,
        *,
        request_id: int,
        reviewer_user_id: int,
        reviewer_note: Optional[str],
        reviewed_at: datetime,
        commit: bool = True,
    ) -> Optional[JustificationRequestModel]:
        return self._review(
            request_id=request_id,
            status=RequestStatus.APPROVED,
            reviewer_user_id=reviewer_user_id,
            reviewer_note=reviewer_note,
            reviewed_at=reviewed_at,
            commit=commit,
        )

    def reject(
        self,
        *,
        request_id: int,
        reviewer_user_id: int,
        reviewer_note: Optional[str],
        reviewed_at: datetime,
        commit: bool = True,
    ) -> Optional[JustificationRequestModel]:
        return self._review(
            request_id=request_id,
            status=RequestStatus.REJECTED,
            reviewer_user_id=reviewer_user_id,
            reviewer_note=reviewer_note,
            reviewed_at=reviewed_at,
            commit=commit,
        )

    def _review(
        self,
        *,
        request_id: int,
        status: RequestStatus,
        reviewer_user_id: int,
        reviewer_note: Optional[str],
        reviewed_at: datetime,
        commit: bool,
    ) -> Optional[JustificationRequestModel]:
        record = self.get_by_id(request_id)
        if record is None:
            return None
        record.status = status
        record.reviewed_by = reviewer_user_id
        record.admin_comment = reviewer_note
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

    def _has_status(
        self,
        attendance_record_id: int,
        request_type: str,
        status: RequestStatus,
    ) -> bool:
        return (
            self._db.query(JustificationRequestModel)
            .filter(
                JustificationRequestModel.attendance_record_id == attendance_record_id,
                JustificationRequestModel.request_type == request_type,
                JustificationRequestModel.status == status,
            )
            .first()
            is not None
        )

    def _base_query(self):
        return self._db.query(JustificationRequestModel).options(
            joinedload(JustificationRequestModel.employee),
            joinedload(JustificationRequestModel.attendance_record),
        )

    @staticmethod
    def _apply_filters(query, filters: JustificationRequestFilters):
        if filters.employee_id is not None:
            query = query.filter(JustificationRequestModel.employee_id == filters.employee_id)
        if filters.attendance_record_id is not None:
            query = query.filter(
                JustificationRequestModel.attendance_record_id == filters.attendance_record_id
            )
        if filters.request_type is not None:
            query = query.filter(JustificationRequestModel.request_type == filters.request_type)
        if filters.status is not None:
            query = query.filter(JustificationRequestModel.status == filters.status)
        if filters.date_from is not None:
            query = query.filter(
                JustificationRequestModel.created_at >= datetime.combine(filters.date_from, time.min)
            )
        if filters.date_to is not None:
            query = query.filter(
                JustificationRequestModel.created_at
                < datetime.combine(filters.date_to + timedelta(days=1), time.min)
            )
        return query

    @staticmethod
    def _paginate(query, page: int, page_size: int):
        return (
            query.order_by(JustificationRequestModel.created_at.desc(), JustificationRequestModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
