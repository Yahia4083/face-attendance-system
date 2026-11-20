"""SQLAlchemy employee schedule repository implementation."""

from datetime import date
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.domain.repositories.employee_schedule_repository import (
    EmployeeScheduleRepositoryInterface,
)
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.employee_schedule import EmployeeScheduleModel


class SqlEmployeeScheduleRepository(EmployeeScheduleRepositoryInterface):
    """Employee schedule assignment repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        employee_id: int,
        schedule_template_id: int,
        effective_from: date,
        effective_to: Optional[date],
        working_days: list[int],
        commit: bool = True,
    ) -> EmployeeScheduleModel:
        record = EmployeeScheduleModel(
            employee_id=employee_id,
            schedule_template_id=schedule_template_id,
            effective_start_date=effective_from,
            effective_end_date=effective_to,
            working_days=self._serialize_working_days(working_days),
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
        return self.get_by_id(record.id) or record

    def get_by_id(self, assignment_id: int) -> Optional[EmployeeScheduleModel]:
        return (
            self._db.query(EmployeeScheduleModel)
            .options(joinedload(EmployeeScheduleModel.schedule_template))
            .filter(EmployeeScheduleModel.id == assignment_id)
            .first()
        )

    def get_by_employee_and_id(
        self,
        employee_id: int,
        assignment_id: int,
    ) -> Optional[EmployeeScheduleModel]:
        return (
            self._db.query(EmployeeScheduleModel)
            .options(joinedload(EmployeeScheduleModel.schedule_template))
            .filter(
                EmployeeScheduleModel.id == assignment_id,
                EmployeeScheduleModel.employee_id == employee_id,
            )
            .first()
        )

    def list_by_employee_id(
        self,
        employee_id: int,
        *,
        is_active: Optional[bool],
        page: int,
        page_size: int,
    ) -> list[EmployeeScheduleModel]:
        query = self._db.query(EmployeeScheduleModel).options(
            joinedload(EmployeeScheduleModel.schedule_template)
        )
        query = query.filter(EmployeeScheduleModel.employee_id == employee_id)
        if is_active is not None:
            query = query.filter(EmployeeScheduleModel.is_active == is_active)
        return (
            query.order_by(EmployeeScheduleModel.effective_start_date.desc(), EmployeeScheduleModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

    def count_by_employee_id(self, employee_id: int, *, is_active: Optional[bool]) -> int:
        query = self._db.query(EmployeeScheduleModel).filter(
            EmployeeScheduleModel.employee_id == employee_id
        )
        if is_active is not None:
            query = query.filter(EmployeeScheduleModel.is_active == is_active)
        return query.count()

    def update(
        self,
        assignment_id: int,
        *,
        schedule_template_id: int,
        effective_from: date,
        effective_to: Optional[date],
        working_days: list[int],
        commit: bool = True,
    ) -> Optional[EmployeeScheduleModel]:
        record = self.get_by_id(assignment_id)
        if record is None:
            return None

        record.schedule_template_id = schedule_template_id
        record.effective_start_date = effective_from
        record.effective_end_date = effective_to
        record.working_days = self._serialize_working_days(working_days)
        try:
            self._db.flush()
            if commit:
                self._db.commit()
                self._db.refresh(record)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return self.get_by_id(assignment_id)

    def activate(
        self,
        assignment_id: int,
        *,
        commit: bool = True,
    ) -> Optional[EmployeeScheduleModel]:
        return self._set_active(assignment_id, is_active=True, commit=commit)

    def deactivate(
        self,
        assignment_id: int,
        *,
        commit: bool = True,
    ) -> Optional[EmployeeScheduleModel]:
        return self._set_active(assignment_id, is_active=False, commit=commit)

    def has_overlap(
        self,
        *,
        employee_id: int,
        effective_from: date,
        effective_to: Optional[date],
        exclude_assignment_id: Optional[int] = None,
    ) -> bool:
        query = self._db.query(EmployeeScheduleModel).filter(
            EmployeeScheduleModel.employee_id == employee_id,
            EmployeeScheduleModel.is_active.is_(True),
            EmployeeScheduleModel.effective_start_date <= (effective_to or date.max),
            or_(
                EmployeeScheduleModel.effective_end_date.is_(None),
                EmployeeScheduleModel.effective_end_date >= effective_from,
            ),
        )
        if exclude_assignment_id is not None:
            query = query.filter(EmployeeScheduleModel.id != exclude_assignment_id)
        return query.first() is not None

    def get_effective_schedule(
        self,
        *,
        employee_id: int,
        on_date: date,
    ) -> Optional[EmployeeScheduleModel]:
        return (
            self._db.query(EmployeeScheduleModel)
            .options(joinedload(EmployeeScheduleModel.schedule_template))
            .filter(
                EmployeeScheduleModel.employee_id == employee_id,
                EmployeeScheduleModel.is_active.is_(True),
                EmployeeScheduleModel.effective_start_date <= on_date,
                or_(
                    EmployeeScheduleModel.effective_end_date.is_(None),
                    EmployeeScheduleModel.effective_end_date >= on_date,
                ),
            )
            .order_by(EmployeeScheduleModel.effective_start_date.desc(), EmployeeScheduleModel.id.desc())
            .first()
        )

    def list_active_assignments_for_date(self, *, on_date: date) -> list[EmployeeScheduleModel]:
        return (
            self._db.query(EmployeeScheduleModel)
            .join(EmployeeModel, EmployeeModel.id == EmployeeScheduleModel.employee_id)
            .options(
                joinedload(EmployeeScheduleModel.employee),
                joinedload(EmployeeScheduleModel.schedule_template),
            )
            .filter(
                EmployeeScheduleModel.is_active.is_(True),
                EmployeeModel.is_active.is_(True),
                EmployeeScheduleModel.effective_start_date <= on_date,
                or_(
                    EmployeeScheduleModel.effective_end_date.is_(None),
                    EmployeeScheduleModel.effective_end_date >= on_date,
                ),
            )
            .order_by(EmployeeScheduleModel.employee_id.asc(), EmployeeScheduleModel.id.asc())
            .all()
        )

    def _set_active(
        self,
        assignment_id: int,
        *,
        is_active: bool,
        commit: bool,
    ) -> Optional[EmployeeScheduleModel]:
        record = self.get_by_id(assignment_id)
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
        return self.get_by_id(assignment_id)

    @staticmethod
    def _serialize_working_days(working_days: list[int]) -> str:
        return ",".join(str(day) for day in sorted(working_days))

    @staticmethod
    def deserialize_working_days(value: str) -> list[int]:
        if not value:
            return []
        return [int(day) for day in value.split(",") if day != ""]
