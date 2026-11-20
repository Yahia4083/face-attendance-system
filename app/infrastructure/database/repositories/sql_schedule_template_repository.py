"""SQLAlchemy schedule template repository implementation."""

from datetime import date, time
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query, Session

from app.domain.repositories.schedule_template_repository import (
    ScheduleTemplateRepositoryInterface,
)
from app.infrastructure.database.models.employee_schedule import EmployeeScheduleModel
from app.infrastructure.database.models.schedule_template import ScheduleTemplateModel


class SqlScheduleTemplateRepository(ScheduleTemplateRepositoryInterface):
    """Schedule template repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        name: str,
        description: Optional[str],
        start_time: time,
        end_time: time,
        is_overnight: bool,
        check_in_grace_minutes: int,
        early_departure_tolerance_minutes: int,
        commit: bool = True,
    ) -> ScheduleTemplateModel:
        record = ScheduleTemplateModel(
            name=name,
            description=description,
            start_time=start_time,
            end_time=end_time,
            is_overnight=is_overnight,
            check_in_grace_minutes=check_in_grace_minutes,
            early_departure_tolerance_minutes=early_departure_tolerance_minutes,
            grace_period_minutes=check_in_grace_minutes,
            minimum_overtime_minutes=0,
            working_days="0,1,2,3,4,5,6",
            is_active=True,
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

    def get_by_id(self, template_id: int) -> Optional[ScheduleTemplateModel]:
        return (
            self._db.query(ScheduleTemplateModel)
            .filter(ScheduleTemplateModel.id == template_id)
            .first()
        )

    def get_by_name(self, name: str) -> Optional[ScheduleTemplateModel]:
        return (
            self._db.query(ScheduleTemplateModel)
            .filter(func.lower(ScheduleTemplateModel.name) == name.strip().lower())
            .first()
        )

    def list(
        self,
        *,
        search: Optional[str],
        is_active: Optional[bool],
        page: int,
        page_size: int,
    ) -> list[ScheduleTemplateModel]:
        return (
            self._build_filtered_query(search=search, is_active=is_active)
            .order_by(ScheduleTemplateModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

    def count(self, *, search: Optional[str], is_active: Optional[bool]) -> int:
        return self._build_filtered_query(search=search, is_active=is_active).count()

    def update(
        self,
        template_id: int,
        *,
        name: str,
        description: Optional[str],
        start_time: time,
        end_time: time,
        is_overnight: bool,
        check_in_grace_minutes: int,
        early_departure_tolerance_minutes: int,
        commit: bool = True,
    ) -> Optional[ScheduleTemplateModel]:
        record = self.get_by_id(template_id)
        if record is None:
            return None

        record.name = name
        record.description = description
        record.start_time = start_time
        record.end_time = end_time
        record.is_overnight = is_overnight
        record.check_in_grace_minutes = check_in_grace_minutes
        record.early_departure_tolerance_minutes = early_departure_tolerance_minutes
        record.grace_period_minutes = check_in_grace_minutes

        try:
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return record

    def activate(
        self,
        template_id: int,
        *,
        commit: bool = True,
    ) -> Optional[ScheduleTemplateModel]:
        return self._set_active(template_id, is_active=True, commit=commit)

    def deactivate(
        self,
        template_id: int,
        *,
        commit: bool = True,
    ) -> Optional[ScheduleTemplateModel]:
        return self._set_active(template_id, is_active=False, commit=commit)

    def has_current_or_future_active_assignments(
        self,
        template_id: int,
        *,
        reference_date: date,
    ) -> bool:
        return (
            self._db.query(EmployeeScheduleModel)
            .filter(
                EmployeeScheduleModel.schedule_template_id == template_id,
                EmployeeScheduleModel.is_active.is_(True),
                or_(
                    EmployeeScheduleModel.effective_end_date.is_(None),
                    EmployeeScheduleModel.effective_end_date >= reference_date,
                ),
            )
            .first()
            is not None
        )

    def _set_active(
        self,
        template_id: int,
        *,
        is_active: bool,
        commit: bool,
    ) -> Optional[ScheduleTemplateModel]:
        record = self.get_by_id(template_id)
        if record is None:
            return None
        record.is_active = is_active
        try:
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return record

    def _build_filtered_query(
        self,
        *,
        search: Optional[str],
        is_active: Optional[bool],
    ) -> Query:
        query = self._db.query(ScheduleTemplateModel)
        if is_active is not None:
            query = query.filter(ScheduleTemplateModel.is_active == is_active)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    ScheduleTemplateModel.name.ilike(pattern),
                    ScheduleTemplateModel.description.ilike(pattern),
                )
            )
        return query
