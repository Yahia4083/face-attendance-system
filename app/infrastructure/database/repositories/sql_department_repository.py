"""SQLAlchemy department repository implementation."""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domain.repositories.department_repository import DepartmentRepositoryInterface
from app.infrastructure.database.models.department import DepartmentModel


class SqlDepartmentRepository(DepartmentRepositoryInterface):
    """Department repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, *, name: str, description: Optional[str]) -> DepartmentModel:
        department = DepartmentModel(name=name, description=description)
        self._db.add(department)
        self._db.commit()
        self._db.refresh(department)
        return department

    def get_by_id(self, department_id: int) -> Optional[DepartmentModel]:
        return (
            self._db.query(DepartmentModel)
            .filter(DepartmentModel.id == department_id)
            .first()
        )

    def get_by_name(self, name: str) -> Optional[DepartmentModel]:
        normalized_name = name.strip().lower()
        return (
            self._db.query(DepartmentModel)
            .filter(func.lower(DepartmentModel.name) == normalized_name)
            .first()
        )

    def list(
        self,
        *,
        is_active: Optional[bool],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> tuple[list[DepartmentModel], int]:
        query = self._db.query(DepartmentModel)

        if is_active is not None:
            query = query.filter(DepartmentModel.is_active == is_active)

        if search:
            pattern = f"%{search}%"
            query = query.filter(DepartmentModel.name.ilike(pattern))

        total = query.count()
        items = (
            query.order_by(DepartmentModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return items, total

    def update(
        self,
        department_id: int,
        *,
        name: str,
        description: Optional[str],
    ) -> Optional[DepartmentModel]:
        department = self.get_by_id(department_id)
        if department is None:
            return None

        department.name = name
        department.description = description

        self._db.commit()
        self._db.refresh(department)
        return department

    def set_active(
        self,
        department_id: int,
        *,
        is_active: bool,
    ) -> Optional[DepartmentModel]:
        department = self.get_by_id(department_id)
        if department is None:
            return None

        department.is_active = is_active

        self._db.commit()
        self._db.refresh(department)
        return department
