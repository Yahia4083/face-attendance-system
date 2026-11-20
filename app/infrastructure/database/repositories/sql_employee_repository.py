"""SQLAlchemy employee repository implementation."""

from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Query, Session, joinedload

from app.domain.enums.user_role import UserRole
from app.domain.repositories.employee_repository import EmployeeRepositoryInterface
from app.infrastructure.database.models.department import DepartmentModel
from app.infrastructure.database.models.employee import EmployeeModel
from app.infrastructure.database.models.user import UserModel


class SqlEmployeeRepository(EmployeeRepositoryInterface):
    """Employee repository backed by SQLAlchemy."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_employee_with_user(
        self,
        *,
        email: str,
        password_hash: str,
        role: UserRole,
        full_name: str,
        employee_number: str,
        phone: Optional[str],
        position: Optional[str],
        department_id: int,
    ) -> EmployeeModel:
        employee_id: Optional[int] = None
        try:
            user = UserModel(
                email=email,
                password_hash=password_hash,
                role=role,
                is_active=True,
            )
            self._db.add(user)
            self._db.flush()

            employee = EmployeeModel(
                user_id=user.id,
                department_id=department_id,
                full_name=full_name,
                employee_number=employee_number,
                phone=phone,
                position=position,
                is_active=True,
            )
            self._db.add(employee)
            self._db.flush()
            employee_id = employee.id

            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise

        if employee_id is None:
            raise RuntimeError("Employee creation failed before ID assignment")
        return self.get_by_id(employee_id)

    def get_by_id(self, employee_id: int) -> Optional[EmployeeModel]:
        return (
            self._db.query(EmployeeModel)
            .options(
                joinedload(EmployeeModel.user),
                joinedload(EmployeeModel.department),
            )
            .filter(EmployeeModel.id == employee_id)
            .first()
        )

    def get_by_user_id(self, user_id: int) -> Optional[EmployeeModel]:
        return (
            self._db.query(EmployeeModel)
            .options(
                joinedload(EmployeeModel.user),
                joinedload(EmployeeModel.department),
            )
            .filter(EmployeeModel.user_id == user_id)
            .first()
        )

    def get_by_employee_number(self, employee_number: str) -> Optional[EmployeeModel]:
        normalized_number = employee_number.strip().lower()
        return (
            self._db.query(EmployeeModel)
            .filter(func.lower(EmployeeModel.employee_number) == normalized_number)
            .first()
        )

    def list(
        self,
        *,
        is_active: Optional[bool],
        department_id: Optional[int],
        search: Optional[str],
        page: int,
        page_size: int,
    ) -> list[EmployeeModel]:
        query = self._build_filtered_query(
            is_active=is_active,
            department_id=department_id,
            search=search,
        )
        return (
            query.order_by(EmployeeModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

    def count(
        self,
        *,
        is_active: Optional[bool],
        department_id: Optional[int],
        search: Optional[str],
    ) -> int:
        query = self._build_filtered_query(
            is_active=is_active,
            department_id=department_id,
            search=search,
        )
        return query.count()

    def update(
        self,
        employee_id: int,
        *,
        email: str,
        full_name: str,
        phone: Optional[str],
        position: Optional[str],
        department_id: int,
    ) -> Optional[EmployeeModel]:
        employee = (
            self._db.query(EmployeeModel)
            .options(joinedload(EmployeeModel.user))
            .filter(EmployeeModel.id == employee_id)
            .first()
        )
        if employee is None:
            return None

        if employee.user is None:
            return None
        employee.user.email = email.strip().lower()
        employee.full_name = full_name
        employee.phone = phone
        employee.position = position
        employee.department_id = department_id

        try:
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise

        return self.get_by_id(employee.id)

    def activate(self, employee_id: int) -> Optional[EmployeeModel]:
        return self._set_active(employee_id, is_active=True)

    def deactivate(self, employee_id: int) -> Optional[EmployeeModel]:
        return self._set_active(employee_id, is_active=False)

    def _set_active(self, employee_id: int, *, is_active: bool) -> Optional[EmployeeModel]:
        employee = (
            self._db.query(EmployeeModel)
            .options(joinedload(EmployeeModel.user))
            .filter(EmployeeModel.id == employee_id)
            .first()
        )
        if employee is None:
            return None

        employee.is_active = is_active
        if employee.user is not None:
            employee.user.is_active = is_active

        try:
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise

        return self.get_by_id(employee.id)

    def _build_filtered_query(
        self,
        *,
        is_active: Optional[bool],
        department_id: Optional[int],
        search: Optional[str],
    ) -> Query:
        query = (
            self._db.query(EmployeeModel)
            .join(UserModel, EmployeeModel.user_id == UserModel.id)
            .join(DepartmentModel, EmployeeModel.department_id == DepartmentModel.id)
            .options(
                joinedload(EmployeeModel.user),
                joinedload(EmployeeModel.department),
            )
        )

        if is_active is not None:
            query = query.filter(EmployeeModel.is_active == is_active)

        if department_id is not None:
            query = query.filter(EmployeeModel.department_id == department_id)

        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    EmployeeModel.full_name.ilike(pattern),
                    UserModel.email.ilike(pattern),
                    EmployeeModel.employee_number.ilike(pattern),
                )
            )

        return query
